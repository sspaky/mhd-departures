# 🚏 IDS BK Departure API for ePaper

A lightweight, high-performance Python Flask microservice wrapped in Docker to fetch, process, and serve real-time Bratislava public transport (IDS BK) departure data in JSON format. 

Optimized specifically for low-power **ePaper displays** (such as [zivyobraz.eu](https://zivyobraz.eu/)) with ultra-fast responses (in-memory GTFS caching), walk-time offset calculations, and token authentication.

---

## 🌟 Key Features

- **⚡ Sub-millisecond Responses**: Parses and holds official ArcGIS GTFS schedules in RAM for instant endpoint delivery, bypassing severe ePaper HTTP timeout restrictions.
- **⏱️️ Walk-time Offset Support**: Ignores impossible-to-catch connections with a dynamic offset buffer (e.g., skip trams departing in under 5 minutes so you don't run needlessly).
- **🔐 Token Authentication**: Protected via a configurable `token` query parameter.
- **🎛️ Dynamic Limits & Stops**: Query parameters allow overriding the stop ID and the number of returned departure lines.
- **🐳 Docker Ready**: Plug-and-play setup for QNAP Container Station, Synology Container Manager, or standard Docker Compose.

---

## 🚀 Project Structure

```text
mhd-epaper/
├── app.py
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🛠️ Configuration & Installation
1. Set your secret token (app.py)
Open app.py and replace the placeholder token with your own custom string:

```Python
API_TOKEN = "<YOUR_SECRET_TOKEN>"  # Replace with your secure token
```

2. Dockerfile setup
Create a Dockerfile in the root folder:
```Dockerfile
FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir flask requests

COPY app.py /app/app.py

EXPOSE 5000

CMD ["python", "app.py"]
```

3. Docker Compose (docker-compose.yml)

```YAML
version: '3.8'

services:
  mhd-app:
    build: .
    container_name: mhd_departures
    restart: always
    ports:
      - "5000:5000"
    volumes:
      - ./app.py:/app/app.py
```

4. Build & Run
```Bash
docker compose up -d --build
```

📡 API ReferenceGET /mhdReturns upcoming departures for a given stop.
Query Parameters
Parameter,Type,Default,Description
token,string,Required,Access token (<YOUR_SECRET_TOKEN>).
stop_id,string,000000035300001,GTFS Stop ID (Default: Segnerova A).
limit,integer,7,Maximum number of upcoming departures to return.
offset,integer,5,Ignore departures in the next N minutes (walking distance buffer).

Example Request
```HTTP
GET /mhd?token=<YOUR_SECRET_TOKEN>&stop_id=000000035300001&limit=5&offset=3
```

Example Response (200 OK)
```JSON
{
  "status": "success",
  "stop_id": "000000035300001",
  "limit": 5,
  "offset_minutes": 3,
  "updated_at": "2026-10-05 17:15:00",
  "departures": [
    {
      "line": "4",
      "destination": "Zlaté piesky",
      "time": "17:18",
      "in_minutes": 3,
      "text": "El. 4 -> Zlaté piesky: 17:18 (3 min)"
    },
    {
      "line": "9",
      "destination": "Astronomická",
      "time": "17:22",
      "in_minutes": 7,
      "text": "El. 9 -> Astronomická: 17:22 (7 min)"
    }
  ]
}
```

🖼 Integration with zivyobraz.eu
Open your zivyobraz.eu scene editor.

Add a Text / Custom Data element.

Configure the source URL:
```HTTP
http://<YOUR_SERVER_IP>:5000/mhd?token=<YOUR_SECRET_TOKEN>
```
Set the refresh interval between 3 and 15 minutes (recommended to conserve ePaper battery).

Map specific JSON attributes (line, destination, in_minutes) or render the formatted "text" field directly on screen.