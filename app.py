import streamlit as st
import requests
import pandas as pd
import altair as alt

st.set_page_config(
    page_title="Dashboard de Patentes BR - Lens.org",
    page_icon="📊",
    layout="wide"
)

# ── Token ──────────────────────────────────────────────────────────────────────
TOKEN = st.secrets.get("LENS_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

API_URL = "https://api.lens.org/patent/search"

# ── Funções de busca ───────────────────────────────────────────────────────────

def fetch_patents(size=100, scroll=None):
    """Busca patentes com jurisdição BR."""
    body = {
        "query": {
            "term": {"jurisdiction": "BR"}
        },
        "size": size,
        "include": [
            "date_published", "jurisdiction",
            "applicant", "inventor", "biblio"
        ],
        "sort": [{"date_published": "asc"}]
    }
    if scroll:
        body["scroll_id"] = scroll

    resp = requests.post(API_URL, headers=HEADERS, json=body, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    else:
        st.error(f"Erro na API: {resp.status_code} — {resp.text}")
        return None


def fetch_aggregations():
    """Busca agregações para os gráficos."""
    body = {
        "query": {"term": {"jurisdiction": "BR"}},
        "size": 0,
        "aggregations": {
            "por_ano": {
                "date_histogram": {
                    "field": "date_published",
                    "calendar_interval": "year",
                    "format": "yyyy"
                }
            },
            "por_pais": {
                "terms": {"field": "jurisdiction", "size": 30}
            },
            "top_inventores": {
                "terms": {"field": "inventor.name", "size": 15}
            },
            "top_empresas": {
                "terms": {"field": "applicant.name", "size": 15}
            }
        }
    }
    resp = requests.post(API_URL, headers=HEADERS, json=body, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    else:
        st.error(f"Erro na API: {resp.status_code} — {resp.text}")
        return None


# ── Interface ──────────────────────────────────────────────────────────────────

st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: Lens.org Patent API — Jurisdição: BR")

if not TOKEN:
    st.error("Token não encontrado! Adicione LENS_TOKEN em .streamlit/secrets.toml")
    st.stop()

# Botão de atualizar
if st.button("🔄 Carregar / Atualizar dados"):
    st.cache_data.clear()

@st.cache_data(ttl=3600, show_spinner="Buscando dados na API do Lens.org...")
def get_data():
    return fetch_aggregations()

data = get_data()

if not data:
    st.stop()

aggs = data.get("aggregations", {})

# ── Métricas rápidas ───────────────────────────────────────────────────────────
total = data.get("total", {}).get("value", 0)
col1, col2, col3 = st.columns(3)
col1.metric("Total de Patentes BR", f"{total:,}".replace(",", "."))

anos_buckets = aggs.get("por_ano", {}).get("buckets", [])
if anos_buckets:
    ultimo_ano = anos_buckets[-1]
    col2.metric("Último ano disponível", ultimo_ano.get("key_as_string", "—"))
    col3.metric("Patentes no último ano", f"{ultimo_ano.get('doc_count', 0):,}".replace(",", "."))

st.divider()

# ── Gráfico 1: Patentes por Ano ────────────────────────────────────────────────
st.subheader("📅 Patentes por Ano")

if anos_buckets:
    df_anos = pd.DataFrame([
        {"Ano": b["key_as_string"], "Patentes": b["doc_count"]}
        for b in anos_buckets
    ])
    chart_anos = (
        alt.Chart(df_anos)
        .mark_line(point=True, color="#1f77b4")
        .encode(
            x=alt.X("Ano:O", title="Ano"),
            y=alt.Y("Patentes:Q", title="Número de Patentes"),
            tooltip=["Ano", "Patentes"]
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(chart_anos, use_container_width=True)
else:
    st.info("Sem dados de ano disponíveis.")

st.divider()

# ── Gráficos 2 e 3 lado a lado ─────────────────────────────────────────────────
col_inv, col_emp = st.columns(2)

# Ranking de Inventores
with col_inv:
    st.subheader("👤 Top Inventores")
    inv_buckets = aggs.get("top_inventores", {}).get("buckets", [])
    if inv_buckets:
        df_inv = pd.DataFrame([
            {"Inventor": b["key"], "Patentes": b["doc_count"]}
            for b in inv_buckets
        ]).sort_values("Patentes")

        chart_inv = (
            alt.Chart(df_inv)
            .mark_bar(color="#2ca02c")
            .encode(
                x=alt.X("Patentes:Q", title="Número de Patentes"),
                y=alt.Y("Inventor:N", sort="-x", title=""),
                tooltip=["Inventor", "Patentes"]
            )
            .properties(height=400)
        )
        st.altair_chart(chart_inv, use_container_width=True)
    else:
        st.info("Sem dados de inventores disponíveis.")

# Ranking de Empresas
with col_emp:
    st.subheader("🏢 Top Empresas / Requerentes")
    emp_buckets = aggs.get("top_empresas", {}).get("buckets", [])
    if emp_buckets:
        df_emp = pd.DataFrame([
            {"Empresa": b["key"], "Patentes": b["doc_count"]}
            for b in emp_buckets
        ]).sort_values("Patentes")

        chart_emp = (
            alt.Chart(df_emp)
            .mark_bar(color="#ff7f0e")
            .encode(
                x=alt.X("Patentes:Q", title="Número de Patentes"),
                y=alt.Y("Empresa:N", sort="-x", title=""),
                tooltip=["Empresa", "Patentes"]
            )
            .properties(height=400)
        )
        st.altair_chart(chart_emp, use_container_width=True)
    else:
        st.info("Sem dados de empresas disponíveis.")

st.divider()

# ── Gráfico 4: Patentes por País/Jurisdição ────────────────────────────────────
st.subheader("🌎 Patentes por Jurisdição")
pais_buckets = aggs.get("por_pais", {}).get("buckets", [])
if pais_buckets:
    df_pais = pd.DataFrame([
        {"Jurisdição": b["key"], "Patentes": b["doc_count"]}
        for b in pais_buckets
    ]).sort_values("Patentes", ascending=False)

    chart_pais = (
        alt.Chart(df_pais)
        .mark_bar(color="#9467bd")
        .encode(
            x=alt.X("Jurisdição:N", sort="-y", title="Jurisdição"),
            y=alt.Y("Patentes:Q", title="Número de Patentes"),
            tooltip=["Jurisdição", "Patentes"]
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(chart_pais, use_container_width=True)
else:
    st.info("Sem dados de jurisdição disponíveis.")

st.caption("Dashboard desenvolvido com Streamlit + Altair (Vega-Lite) | Dados: Lens.org")
