import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

_cache_data = None

def load_summary():
    global _cache_data
    if _cache_data is not None:
        return True
    # Na Vercel, o api/summary.py acessa o ibict_summary.json na raiz do projeto (..)
    path = os.path.join(os.path.dirname(__file__), '..', 'ibict_summary.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            _cache_data = json.load(f)
        return True
    except Exception as e:
        print("Erro ao carregar summary:", e)
        return False

def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "X-Requested-With, Content-Type"
    }

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in get_cors_headers().items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        # Trata o CORS e verifica o carregamento
        for k, v in get_cors_headers().items():
            self.send_header(k, v)

        if not load_summary():
            self.send_response(503)
            self.end_headers()
            return

        # Parsing dos filtros
        qs = parse_qs(urlparse(self.path).query)
        f_min = int(qs.get("year_min", [0])[0])
        f_max = int(qs.get("year_max", [9999])[0])
        f_status = qs.get("status", [])
        f_tipo = qs.get("tipo", [])

        data = _cache_data.copy()
        filtered_agg = []
        filtered_count = 0

        if f_min < 1900: f_min = 0
        if f_max < 1900: f_max = 9999

        for item in _cache_data.get("agg_year_status", []):
            ano = int(item["ano"])
            status = item["status"]
            if f_min <= ano <= f_max:
                if not f_status or status in f_status:
                    filtered_agg.append(item)
                    filtered_count += item["count"]
        
        data["agg_year_status"] = filtered_agg
        data["filtered_count"] = filtered_count

        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        
        self.send_response(200)
        for k, v in get_cors_headers().items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
