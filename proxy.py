"""
Proxy local para a API do IBICT.
Portas:
  8080 → http.server (index.html)
  8888 → este proxy

Endpoints:
  GET /api/v1/patente?...   → repassa direto para pi-api-dev.ibict.br (com CORS)
  GET /full-data            → agrega TODOS os registros paginando por ano (1990–2025)
                              e retorna um único JSON: {"total": N, "results": [...]}
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request, urllib.error
import json, sys, traceback, os, time

TARGET  = "http://pi-api-dev.ibict.br"
PORT    = 8888
TIMEOUT = 60
BATCH   = 100 # Reduzido para ser mais estável
YEARS   = range(1990, 2026)   # anos de depósito a varrer


def fetch_json(path, retries=3):
    """Faz GET com retentativas e delay."""
    url = TARGET + path
    req = urllib.request.Request(url, headers={
        "Accept":          "application/json",
        "User-Agent":      "ibict-dashboard-proxy/4.0",
    })
    
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            if e.code == 500:
                print(f"  [fetch] Erro 500 em {url[:50]}... (Tentativa {i+1}/{retries})")
            else:
                print(f"  [fetch] HTTP {e.code} -> {url[:50]}")
                break
        except Exception as e:
            print(f"  [fetch] Erro: {e} (Tentativa {i+1}/{retries})")
        
        time.sleep(2 * (i + 1)) # Delay incremental
    return None


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else "?"
        print(f"[proxy] {self.path[:80]}  →  {status}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/full-data":
            self._handle_full_data()
        else:
            self._proxy_pass()

# ── /full-data ─────────────────────────────────────────────────────────────
    def _handle_full_data(self):
        # Verifica se o cliente quer ignorar o cache (?refresh=true)
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        force_refresh = "true" in qs.get("refresh", [])
        
        CACHE_FILE = "ibict_cache.json"

        if not force_refresh and os.path.exists(CACHE_FILE):
            print(f"\n[cache] Carregando dados do arquivo local: {CACHE_FILE}")
            try:
                with open(CACHE_FILE, "rb") as f:
                    body = f.read()
                print(f"[cache] Pronto! {len(body)} bytes enviados.\n")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type",   "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as e:
                print(f"[cache] Erro ao ler cache, tentando API... {e}")

        print("\n[full-data] Iniciando coleta via API IBICT (pode demorar)…")
        all_records = []

        for year in YEARS:
            offset = 0
            year_count = 0
            print(f"  [ano={year}] ", end="", flush=True)
            while True:
                path = f"/api/v1/patente?limit={BATCH}&offset={offset}&deposit_year={year}"
                data = fetch_json(path)
                time.sleep(0.5) # Pausa amigável para a API
                if not data:
                    break
                batch = data.get("results") or data.get("data") or []
                if not batch:
                    break
                all_records.extend(batch)
                year_count += len(batch)
                offset     += len(batch)
                if len(batch) < BATCH:
                    break
            print(f"{year_count} registros")

        total = len(all_records)
        result_dict = {"total": total, "results": all_records}
        body = json.dumps(result_dict, ensure_ascii=False).encode("utf-8")
        
        print(f"\n[full-data] Total: {total} registros. Salvando cache e enviando…\n")
        
        # Salva em cache para as próximas vezes
        try:
            with open(CACHE_FILE, "wb") as f:
                f.write(body)
        except Exception as e:
            print(f"[cache] Erro ao salvar cache: {e}")

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── passthrough ────────────────────────────────────────────────────────────
    def _proxy_pass(self):
        url = TARGET + self.path
        req = urllib.request.Request(url, headers={
            "Accept":          "application/json",
            "User-Agent":      "ibict-dashboard-proxy/3.0",
            "Accept-Language": "pt-BR,pt;q=0.9",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read()
                ct   = r.headers.get("Content-Type", "application/json")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type",   ct)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self._cors()
            self.send_header("Content-Type",   "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            msg = json.dumps({"error": str(e)}).encode()
            print(f"[proxy] ERRO: {e}")
            self.send_response(502)
            self._cors()
            self.send_header("Content-Type",   "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")


if __name__ == "__main__":
    server = HTTPServer(("", PORT), ProxyHandler)
    print(f"✅ Proxy rodando em  http://localhost:{PORT}")
    print(f"   Repassa para      {TARGET}")
    print(f"   /full-data        agrega todos os anos {YEARS.start}–{YEARS.stop-1}")
    print(f"   Timeout:          {TIMEOUT}s / requisição")
    print("   Pressione Ctrl+C para parar.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy encerrado.")
        sys.exit(0)
