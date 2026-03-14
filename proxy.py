"""
Proxy local para a API do IBICT.
Portas:
  8080 → http.server (index.html)
  8888 → este proxy

Endpoints:
  GET /api/v1/patente?...   → repassa direto para pi-api-dev.ibict.br (com CORS)
  GET /full-data            → retorna o cache JSON completo (aguarda se ainda coletando)
  GET /cache-status         → {"ready": bool, "progress": 0.0-1.0, "message": "..."}
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request, urllib.error
import json, sys, traceback, os, time, threading

TARGET     = "http://pi-api-dev.ibict.br"
PORT       = 8888
TIMEOUT    = 60
BATCH      = 100
YEARS      = list(range(1990, 2026))
CACHE_FILE = "ibict_cache.json"
TOTAL_YEARS = len(YEARS)

# ── Estado global do cache ─────────────────────────────────────────────────────
_cache_lock    = threading.Lock()
_cache_ready   = False      # True quando o cache está 100% gerado
_cache_progress = 0.0       # 0.0 → 1.0
_cache_message  = "Aguardando início da coleta…"
_cache_body     = None      # bytes do JSON final (quando pronto)


def set_cache_state(ready, progress, message, body=None):
    global _cache_ready, _cache_progress, _cache_message, _cache_body
    with _cache_lock:
        _cache_ready    = ready
        _cache_progress = progress
        _cache_message  = message
        if body is not None:
            _cache_body = body


def get_cache_state():
    with _cache_lock:
        return _cache_ready, _cache_progress, _cache_message, _cache_body


# ── Fetch helper ───────────────────────────────────────────────────────────────
def fetch_json(path, retries=3):
    """Faz GET com retentativas e delay."""
    url = TARGET + path
    req = urllib.request.Request(url, headers={
        "Accept":     "application/json",
        "User-Agent": "ibict-dashboard-proxy/5.0",
    })
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            if e.code == 500:
                print(f"  [fetch] Erro 500 em {url[:50]}… (Tentativa {i+1}/{retries})")
            else:
                print(f"  [fetch] HTTP {e.code} -> {url[:50]}")
                break
        except Exception as e:
            print(f"  [fetch] Erro: {e} (Tentativa {i+1}/{retries})")
        time.sleep(2 * (i + 1))
    return None


# ── Background: pré-aquece o cache ────────────────────────────────────────────
def _prewarm_cache():
    """Roda em background thread ao iniciar o proxy."""
    # Se já existe cache salvo, carrega direto
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                body = f.read()
            set_cache_state(True, 1.0, "✅ Cache carregado do disco.", body)
            print(f"[cache] Cache existente carregado ({len(body):,} bytes).")
            return
        except Exception as e:
            print(f"[cache] Erro ao ler cache existente: {e}. Reconstruindo…")

    print("[cache] Iniciando coleta completa em background…")
    all_records = []

    for idx, year in enumerate(YEARS):
        progress = idx / TOTAL_YEARS
        msg = f"Coletando ano {year}… ({idx + 1}/{TOTAL_YEARS} anos)"
        set_cache_state(False, progress, msg)
        print(f"  [ano={year}] ", end="", flush=True)

        offset     = 0
        year_count = 0
        while True:
            path = f"/api/v1/patente?limit={BATCH}&offset={offset}&deposit_year={year}"
            data = fetch_json(path)
            time.sleep(0.5)
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

    total      = len(all_records)
    result     = {"total": total, "results": all_records}
    body_bytes = json.dumps(result, ensure_ascii=False).encode("utf-8")

    # Salva em disco
    try:
        with open(CACHE_FILE, "wb") as f:
            f.write(body_bytes)
        print(f"[cache] ✅ Pronto! {total} registros salvos em {CACHE_FILE}.")
    except Exception as e:
        print(f"[cache] Erro ao salvar cache: {e}")

    set_cache_state(True, 1.0, f"✅ Coleta concluída! {total:,} patentes.", body_bytes)


def start_prewarm():
    t = threading.Thread(target=_prewarm_cache, daemon=True, name="CachePrewarm")
    t.start()


# ── HTTP Handler ───────────────────────────────────────────────────────────────
class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else "?"
        print(f"[proxy] {self.path[:80]}  →  {status}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/cache-status":
            self._handle_cache_status()
        elif self.path.startswith("/full-data"):
            self._handle_full_data()
        else:
            self._proxy_pass()

    # ── GET /cache-status ──────────────────────────────────────────────────────
    def _handle_cache_status(self):
        ready, progress, message, _ = get_cache_state()
        payload = json.dumps({
            "ready":    ready,
            "progress": round(progress, 4),
            "message":  message,
        }, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # ── GET /full-data ─────────────────────────────────────────────────────────
    def _handle_full_data(self):
        from urllib.parse import urlparse, parse_qs
        qs            = parse_qs(urlparse(self.path).query)
        force_refresh = "true" in qs.get("refresh", [])

        if force_refresh:
            # Apaga cache e reinicia a coleta em background
            if os.path.exists(CACHE_FILE):
                try:
                    os.remove(CACHE_FILE)
                except Exception:
                    pass
            set_cache_state(False, 0.0, "Reiniciando coleta…")
            start_prewarm()

        # Aguarda até o cache estar pronto (polling interno)
        wait_msg_printed = False
        while True:
            ready, progress, message, body = get_cache_state()
            if ready and body:
                break
            if not wait_msg_printed:
                print("[full-data] Cache ainda sendo gerado, aguardando…")
                wait_msg_printed = True
            time.sleep(2)

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
            "User-Agent":      "ibict-dashboard-proxy/5.0",
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


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"✅ Proxy rodando em  http://localhost:{PORT}")
    print(f"   Repassa para      {TARGET}")
    print(f"   /full-data        retorna cache completo (aguarda geração se necessário)")
    print(f"   /cache-status     retorna progresso da coleta")
    print(f"   Timeout:          {TIMEOUT}s / requisição")
    print("   Iniciando pré-aquecimento do cache em background…\n")

    # Inicia coleta em background ANTES de aceitar conexões
    start_prewarm()

    server = HTTPServer(("", PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy encerrado.")
        sys.exit(0)
