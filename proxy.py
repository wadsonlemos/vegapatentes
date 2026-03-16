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
from socketserver import ThreadingMixIn
import urllib.request, urllib.error
import json, sys, traceback, os, time, threading

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


TARGET     = "http://pi-api-dev.ibict.br"
PORT       = 8888
TIMEOUT    = 60
BATCH      = 100
YEARS_RECENT = list(range(2021, 2026))
YEARS_HISTORIC = list(range(1990, 2021)) # 1990 to 2020
CACHE_FILE = "ibict_cache.json"

# ── Estado global do cache ─────────────────────────────────────────────────────
_cache_lock    = threading.Lock()
_cache_ready   = False      # True quando o cache está 100% gerado
_cache_progress = 0.0       # 0.0 → 1.0
_cache_message  = "Aguardando início da coleta…"
_cache_body     = None      # bytes do JSON final (quando pronto)
_prewarm_thread = None      # Referência para a thread atual


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


def _load_cache_if_exists():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                return json.loads(f.read().decode("utf-8"))
        except Exception as e:
            print(f"[cache] Erro ao ler cache existente: {e}")
    return {"total": 0, "results": []}


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
def _prewarm_cache(years_to_fetch, is_history=False):
    """Roda em background thread para buscar anos específicos."""
    print(f"[cache] Iniciando coleta para os anos: {years_to_fetch[0]} a {years_to_fetch[-1]}…")
    
    # Carrega dados existentes para append, se for histórico.
    # Se não for history, tentamos ler do disco primeiro para skip.
    existing_data = {"total": 0, "results": []}
    
    if is_history:
        existing_data = _load_cache_if_exists()
    else:
        # Se for prewarm inicial (recentes), e o arquivo já existe e tem o mesmo tamanho de anos?
        # Para ser seguro, se o arquivo existe e o is_history for falso, apenas retorna o cache existente.
        if os.path.exists(CACHE_FILE):
            data = _load_cache_if_exists()
            if data and data.get("total", 0) > 0:
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                set_cache_state(True, 1.0, "✅ Cache carregado do disco.", body)
                print(f"[cache] Cache existente carregado ({data['total']} registros).")
                return

    all_records = existing_data.get("results", [])
    total_years = len(years_to_fetch)

    for idx, year in enumerate(years_to_fetch):
        progress = idx / total_years
        msg_prefix = "Histórico: " if is_history else "Recente: "
        msg = f"{msg_prefix}Coletando ano {year}… ({idx + 1}/{total_years} anos)"
        set_cache_state(False, progress, msg)
        print(f"  [{msg_prefix}ano={year}] ", end="", flush=True)

        offset     = 0
        year_count = 0
        last_batch_str = None
        while True:
            path = f"/api/v1/patente?limit={BATCH}&offset={offset}&deposit_year={year}"
            data = fetch_json(path)
            time.sleep(0.5)
            if not data:
                break
            batch = data.get("results") or data.get("data") or []
            if not batch:
                break
                
            # Anti-infinite loop
            current_batch_str = json.dumps(batch, sort_keys=True)
            if current_batch_str == last_batch_str:
                print(f"  [{year}] API duplicou offset {offset}. Fim deste ano.")
                break
            last_batch_str = current_batch_str

            all_records.extend(batch)
            year_count += len(batch)
            offset     += len(batch)
            if len(batch) < BATCH:
                break
        print(f"{year_count} registros")

    total      = len(all_records)
    result     = {"total": total, "results": all_records}
    body_bytes = json.dumps(result, ensure_ascii=False).encode("utf-8")

    # Salva/Sobrescreve no disco
    try:
        with open(CACHE_FILE, "wb") as f:
            f.write(body_bytes)
        print(f"[cache] ✅ Pronto! {total} registros totais salvos.")
    except Exception as e:
        print(f"[cache] Erro ao salvar cache: {e}")

    set_cache_state(True, 1.0, f"✅ Coleta concluída! {total:,} registros.", body_bytes)


def start_prewarm(force_years=None, is_history=False):
    global _prewarm_thread
    if _prewarm_thread and _prewarm_thread.is_alive():
        print("[cache] O pré-aquecimento já está em andamento. Ignorando.")
        return
        
    years = force_years if force_years else YEARS_RECENT
    _prewarm_thread = threading.Thread(target=_prewarm_cache, args=(years, is_history), daemon=True, name="CachePrewarm")
    _prewarm_thread.start()


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
        # ── Bloqueia bots da AWS procurando credenciais (evita sujar o log) ──
        if "169.254.169.254" in self.path or "meta-data" in self.path:
            self.send_response(404)
            self.end_headers()
            return

        if self.path == "/cache-status":
            self._handle_cache_status()
        elif self.path.startswith("/full-data"):
            self._handle_full_data()
        elif self.path.startswith("/fetch-history"):
            self._handle_fetch_history()
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
            if os.path.exists(CACHE_FILE):
                try:
                    os.remove(CACHE_FILE)
                except Exception:
                    pass
            set_cache_state(False, 0.0, "Reiniciando pesquisa recente (2021-2025)…")
            start_prewarm(force_years=YEARS_RECENT, is_history=False)

        # Aguarda até cache pronto
        wait_msg_printed = False
        while True:
            ready, progress, message, body = get_cache_state()
            if ready and body:
                break
            if not wait_msg_printed:
                print("[full-data] Aguardando cache principal...")
                wait_msg_printed = True
            time.sleep(2)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── GET /fetch-history ──────────────────────────────────────────────────────
    def _handle_fetch_history(self):
        # Dispara a busca do histórico (ex: 1990-2020) em background.
        set_cache_state(False, 0.0, "Iniciando carga histórica (1990-2020)…")
        start_prewarm(force_years=YEARS_HISTORIC, is_history=True)

        payload = json.dumps({"status": "started"}).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


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

    server = ThreadedHTTPServer(("", PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy encerrado.")
        sys.exit(0)
