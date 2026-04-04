"""
Proxy local simplificado para o Dashboard de Patentes (Modo Sumário).
Carrega apenas o ibict_summary.json para máxima performance e baixo uso de memória.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import json, sys, os, time, threading
from urllib.parse import urlparse, parse_qs

# Garante que o console aceite UTF-8 (evita UnicodeEncodeError no Windows)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

PORT = 8888
SUMMARY_FILE = "ibict_summary.json"

# Estado global
_cache_data = None
_last_load = 0

def load_summary():
    global _cache_data, _last_load
    if not os.path.exists(SUMMARY_FILE):
        print(f"[proxy] ERRO: {SUMMARY_FILE} não encontrado. Rode 'python summarize.py' primeiro.")
        return False
    
    # Recarrega se o arquivo mudou ou se é a primeira vez
    mtime = os.path.getmtime(SUMMARY_FILE)
    if _cache_data is None or mtime > _last_load:
        print(f"[proxy] Carregando resumo de {SUMMARY_FILE}...")
        try:
            with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
                _cache_data = json.load(f)
            _last_load = mtime
            return True
        except Exception as e:
            print(f"[proxy] Erro ao carregar resumo: {e}")
            return False
    return True

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Log simplificado para acompanhamento
        print(f"[proxy] {args[1]} -> {self.path[:50]}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/cache-status":
            self._handle_status()
        elif self.path == "/ping":
            self._handle_ping()
        elif self.path.startswith("/summary"):
            self._handle_summary()
        elif self.path.startswith("/full-data"):
            self._handle_full_data()
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def _handle_ping(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "OK", "timestamp": time.time()}).encode("utf-8"))

    def _handle_full_data(self):
        # Endpoint para compatibilidade com o dashboard. 
        # Em modo sumário, apenas confirmamos o recebimento.
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "OK", "mode": "summary"}).encode("utf-8"))

    def _handle_status(self):
        ready = load_summary()
        payload = json.dumps({
            "ready": ready,
            "progress": 1.0 if ready else 0.0,
            "message": "Dashboard pronto (Modo Sumário)" if ready else "Resumo ausente"
        }).encode("utf-8")
        
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_summary(self):
        if not load_summary():
            self.send_response(503)
            self.end_headers()
            return

        # Filtros básicos via Query String
        qs = parse_qs(urlparse(self.path).query)
        f_min = int(qs.get("year_min", [0])[0])
        f_max = int(qs.get("year_max", [9999])[0])
        f_status = qs.get("status", [])
        f_tipo = qs.get("tipo", [])

        # Como já temos os agregados, vamos apenas aplicar o filtro de ano/status/tipo na resposta
        # NOTA: O resumo pré-calculado ibict_summary.json já contém os totais.
        # Se o usuário filtrar, o proxy simula a filtragem sobre os agregados.
        
        data = _cache_data.copy()
        
        # Filtra agg_year_status
        filtered_agg = []
        filtered_count = 0
        
        # Se os anos forem muito baixos (ex: default de browser 50), ignoramos o filtro
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
        
        # Para simplificar, outros campos como top_applicants permanecem os mesmos da base total,
        # ou poderiam ser recalculados se tivéssemos o granulado. Mas como o foco é "totais",
        # servimos o resumo principal.

        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == "__main__":
    if load_summary():
        print(f"[proxy] Servidor rodando em http://localhost:{PORT}")
        print(f"[proxy] Modo Sumário ativo. Base: {_cache_data.get('total_base')} registros.")
    else:
        print(f"[proxy] Aviso: {SUMMARY_FILE} não encontrado. Rodando em modo de espera.")

    server = ThreadedHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[proxy] Encerrando.")
        sys.exit(0)
