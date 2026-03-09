import streamlit as st
import requests
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Dashboard de Patentes BR - Lens.org",
    page_icon="📊",
    layout="wide"
)

TOKEN = st.secrets.get("LENS_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}
API_URL = "https://api.lens.org/patent/search"

if not TOKEN:
    st.error("Token não encontrado!")
    st.stop()

st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: Lens.org Patent API")

if st.button("🔄 Carregar / Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

# ── Testa múltiplas queries para descobrir qual funciona ──────────────────────

@st.cache_data(ttl=600)
def test_query(body):
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=body, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return 0, {"error": str(e)}

queries = {
    "match_phrase jurisdiction:BR": {
        "query": {"match_phrase": {"jurisdiction": "BR"}},
        "size": 5
    },
    "term jurisdiction:BR": {
        "query": {"term": {"jurisdiction": "BR"}},
        "size": 5
    },
    "match country:BR": {
        "query": {"match": {"country": "BR"}},
        "size": 5
    },
    "query_string BR": {
        "query": "BR",
        "size": 5
    },
    "sem filtro (primeiros 5)": {
        "size": 5
    },
    "match_phrase biblio.publication_reference.country:BR": {
        "query": {"match_phrase": {"biblio.publication_reference.country": "BR"}},
        "size": 5
    },
}

st.subheader("🔍 Testando queries na API")

for label, body in queries.items():
    status, result = test_query(str(body))  # cache key como string
    # faz a chamada real
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=body, timeout=30)
        status = resp.status_code
        result = resp.json()
    except Exception as e:
        status = 0
        result = {"error": str(e)}

    total = result.get("total", 0)
    hits = result.get("data", [])

    if status == 200 and hits:
        st.success(f"✅ **{label}** → status {status}, total={total}, registros={len(hits)}")
        with st.expander(f"Ver primeiro registro de '{label}'"):
            st.json(hits[0])
    elif status == 200:
        st.warning(f"⚠️ **{label}** → status {status}, total={total}, registros=0 (vazio)")
    else:
        msg = result.get("message", result.get("error", ""))
        st.error(f"❌ **{label}** → status {status}: {msg[:120]}")