from flask import Flask, jsonify, request
import os
import time
import requests
import zipfile
import io
import csv
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

API_TOKEN = "<TOKEN>"
GTFS_URL = "https://www.arcgis.com/sharing/rest/content/items/aba12fd2cbac4843bc7406151bc66106/data"
CACHE_FILE = "/tmp/gtfs_cache.zip"

PARSED_CACHE = {
    "timestamp": 0,
    "stop_times": [],
    "last_error": None
}

def get_local_now():
    # UTC+2 pre Bratislavu (letný čas)
    return datetime.now(timezone.utc) + timedelta(hours=2)

def load_and_parse_gtfs():
    now_ts = time.time()
    
    if PARSED_CACHE["timestamp"] > 0 and (now_ts - PARSED_CACHE["timestamp"] < 43200):
        return

    content = None
    
    if os.path.exists(CACHE_FILE) and (now_ts - os.path.getmtime(CACHE_FILE) < 43200):
        try:
            with open(CACHE_FILE, "rb") as f:
                content = f.read()
        except Exception as e:
            PARSED_CACHE["last_error"] = f"Cache read error: {e}"

    if not content or len(content) < 1000:
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            res = requests.get(GTFS_URL, headers=headers, timeout=30, verify=False)
            if res.status_code == 200 and len(res.content) > 1000:
                content = res.content
                with open(CACHE_FILE, "wb") as f:
                    f.write(content)
            else:
                PARSED_CACHE["last_error"] = f"ArcGIS HTTP status: {res.status_code}"
        except Exception as e:
            PARSED_CACHE["last_error"] = f"Download error: {e}"

    if not content and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                content = f.read()
        except Exception:
            pass

    if not content:
        return

    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        now = get_local_now()
        today_str = now.strftime("%Y%m%d")
        weekday_name = now.strftime("%A").lower()

        valid_services = set()
        if 'calendar.txt' in z.namelist():
            with io.TextIOWrapper(z.open('calendar.txt'), encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('start_date', '') <= today_str <= row.get('end_date', ''):
                        if row.get(weekday_name) == '1':
                            valid_services.add(row['service_id'])

        if 'calendar_dates.txt' in z.namelist():
            with io.TextIOWrapper(z.open('calendar_dates.txt'), encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    if row.get('date') == today_str:
                        if row.get('exception_type') == '1':
                            valid_services.add(row['service_id'])
                        elif row.get('exception_type') == '2':
                            valid_services.discard(row['service_id'])

        routes = {}
        with io.TextIOWrapper(z.open('routes.txt'), encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                routes[row['route_id']] = row.get('route_short_name', '')

        valid_trips = {}
        with io.TextIOWrapper(z.open('trips.txt'), encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row['service_id'] in valid_services:
                    valid_trips[row['trip_id']] = {
                        'route': routes.get(row['route_id'], ''),
                        'headsign': row.get('trip_headsign', 'Mesto')
                    }

        stop_times = []
        with io.TextIOWrapper(z.open('stop_times.txt'), encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                trip_id = row['trip_id']
                if trip_id in valid_trips:
                    stop_times.append({
                        'stop_id': row['stop_id'],
                        'dep_time': row['departure_time'],
                        'route': valid_trips[trip_id]['route'],
                        'headsign': valid_trips[trip_id]['headsign']
                    })

        PARSED_CACHE["stop_times"] = stop_times
        PARSED_CACHE["timestamp"] = now_ts
        PARSED_CACHE["last_error"] = None

    except Exception as e:
        PARSED_CACHE["last_error"] = f"Parse error: {e}"

def get_departures_fast(stop_id, limit=7, offset=5):
    load_and_parse_gtfs()
    
    if not PARSED_CACHE["stop_times"]:
        err_msg = PARSED_CACHE["last_error"] or "GTFS not loaded"
        return {"status": "error", "message": err_msg, "departures": []}

    now = get_local_now()
    
    # Prirátame offset k aktuálnemu času, aby sme preskočili spoje, ktoré už nestíhame
    threshold_time = now + timedelta(minutes=offset)
    threshold_time_str = threshold_time.strftime("%H:%M:%S")

    raw_departures = []
    for st in PARSED_CACHE["stop_times"]:
        if st['stop_id'] == stop_id and st['dep_time'] >= threshold_time_str:
            raw_departures.append((st['dep_time'], st['route'], st['headsign']))

    raw_departures = sorted(list(set(raw_departures)), key=lambda x: x[0])

    departures_list = []
    for dep_time, route, headsign in raw_departures:
        dep_hours, dep_mins, dep_secs = map(int, dep_time.split(':'))
        dep_dt = now.replace(hour=dep_hours % 24, minute=dep_mins, second=dep_secs)
        if dep_hours >= 24:
            dep_dt += timedelta(days=1)

        diff_minutes = int((dep_dt - now).total_seconds() // 60)
        
        if diff_minutes >= offset:
            departures_list.append({
                "line": route,
                "destination": headsign,
                "time": dep_time[:5],
                "in_minutes": diff_minutes,
                "text": f"El. {route} -> {headsign}: {dep_time[:5]} ({diff_minutes} min)"
            })

        if len(departures_list) >= limit:
            break

    return {
        "status": "success",
        "stop_id": stop_id,
        "limit": limit,
        "offset_minutes": offset,
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "departures": departures_list
    }

@app.route('/mhd')
def mhd_endpoint():
    user_token = request.args.get('token')
    if not user_token or user_token != API_TOKEN:
        return jsonify({"status": "error", "message": "Neautorizovaný prístup"}), 401

    stop_id = request.args.get('stop_id', '000000035300001')
    
    try:
        limit = int(request.args.get('limit', 7))
    except ValueError:
        limit = 7

    try:
        offset = int(request.args.get('offset', 5))
    except ValueError:
        offset = 5

    data = get_departures_fast(stop_id, limit=limit, offset=offset)
    
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
