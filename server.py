import json
import os
import ssl
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen

def analyze(lat, lon):
    lat = float(lat)
    lon = float(lon)
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relativehumidity_2m,precipitation_probability,windspeed_10m"
        f"&current_weather=true&timezone=auto"
    )
    with urlopen(url) as r:
        d = json.loads(r.read().decode("utf-8"))
    h = d.get("hourly", {})
    temps = h.get("temperature_2m", [])[:24]
    hums = h.get("relativehumidity_2m", [])[:24]
    rains = h.get("precipitation_probability", [])[:24]
    winds = h.get("windspeed_10m", [])[:24]
    if not temps:
        return {"protection_index": 50, "rain_risk": 0, "heat_index": 0, "wind_risk": 0, "status": "SAFE", "advice": "No data"}
    t = sum(temps) / len(temps)
    rh = sum(hums) / len(hums) if hums else 50
    rain = max(rains) if rains else 0
    wind = sum(winds) / len(winds) if winds else 0
    hi = (
        -8.784695 + 1.61139411*t + 2.338549*rh - 0.14611605*t*rh
        - 0.012308094*(t**2) - 0.016424828*(rh**2) + 0.002211732*(t**2)*rh
        + 0.00072546*t*(rh**2) - 0.000003582*(t**2)*(rh**2)
    )
    heat = max(0, min(100, (hi-27)*6))
    wind_risk = max(0, min(100, (wind-20)*4))
    rain_risk = max(0, min(100, rain))
    risk = max(rain_risk*0.45, heat*0.35, wind_risk*0.4)
    protection = int(max(10, 100 - risk))
    if rain_risk > 70:
        status = "RAINY"; advice = "Heavy rain expected. Use waterproof gear."
    elif heat > 60:
        status = "HEATWAVE"; advice = "High heat stress. Hydrate, limit sun exposure."
    elif wind_risk > 60:
        status = "WINDY"; advice = "Strong winds. Secure outdoor items."
    elif risk > 85:
        status = "DANGER"; advice = "Severe conditions. Stay indoors."
    else:
        status = "SAFE"; advice = "Conditions are acceptable."
    return {
        "protection_index": protection,
        "rain_risk": int(rain_risk),
        "heat_index": int(heat),
        "wind_risk": int(wind_risk),
        "status": status,
        "advice": advice,
    }

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", "default-src 'self' https:; script-src 'self' https: 'unsafe-inline'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https: data:; font-src 'self' https:; connect-src 'self' https:")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8000")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()
    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()
    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/analyze":
            q = parse_qs(p.query)
            lat = q.get("lat", [None])[0]
            lon = q.get("lon", [None])[0]
            try:
                float(lat); float(lon)
            except Exception:
                self.send_response(400); self.end_headers(); self.wfile.write(b"{}"); return
            res = analyze(lat, lon)
            kb = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(kb)))
            self.end_headers()
            self.wfile.write(kb)
        else:
            super().do_GET()

if __name__ == "__main__":
    httpd = HTTPServer(("127.0.0.1", 8000), Handler)
    if os.path.exists("server.pem"):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain("server.pem")
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    httpd.serve_forever()
