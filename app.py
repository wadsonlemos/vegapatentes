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
    st.error("Token não encontrado! Adicione LENS_TOKEN em .streamlit/secrets.toml")
    st.stop()

# ── Busca de dados ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner="Buscando patentes na API do Lens.org...")
def fetch_patents(size=100):
    body = {
        "query": {
            "term": {"country": "BR"}
        },
        "size": size,
        "include": [
            "date_publ",
            "country",
            "biblio.invention_title",
            "biblio.parties"
        ],
        "sort": [{"date_publ": "desc"}]
    }
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=body, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"{resp.status_code}", "message": resp.text}
    except Exception as e:
        return {"error": "exception", "message": str(e)}

# ── Interface ──────────────────────────────────────────────────────────────────

st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: Lens.org Patent API — País: BR")

if st.button("🔄 Carregar / Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

data = fetch_patents(size=100)

# Tratamento de erro robusto
if data is None:
    st.error("A API não retornou dados. Verifique o token e tente novamente.")
    st.stop()

if "error" in data:
    st.error(f"Erro na API: {data['error']} — {data.get('message', '')}")
    st.stop()

# Mostra estrutura da resposta para debug (remova depois)
with st.expander("🔍 Debug: estrutura da resposta da API"):
    keys = list(data.keys())
    st.write("Chaves na resposta:", keys)
    if "data" in data and len(data["data"]) > 0:
        st.write("Chaves do primeiro registro:", list(data["data"][0].keys()))
        st.json(data["data"][0])

hits = data.get("data", [])
total_raw = data.get("total", 0)

# total pode ser int ou dict dependendo da versão da API
if isinstance(total_raw, dict):
    total_api = total_raw.get("value", 0)
else:
    total_api = int(total_raw) if total_raw else 0

if not hits:
    st.warning("Nenhuma patente encontrada.")
    st.stop()

# ── Processar dados ────────────────────────────────────────────────────────────

records = []
for h in hits:
    date = h.get("date_publ", "")
    year = str(date)[:4] if date else "Desconhecido"
    country = h.get("country", "Desconhecido")

    biblio = h.get("biblio", {})

    # Título
    titles = biblio.get("invention_title", [])
    if isinstance(titles, list) and titles:
        title = titles[0].get("text", "Sem título")
    else:
        title = "Sem título"

    # Inventores
    parties = biblio.get("parties", {})
    inventors_raw = parties.get("inventors", [])
    inventor_names = []
    for inv in inventors_raw:
        inv_name = inv.get("inventor_name", {})
        name = inv_name.get("name", "") or inv_name.get("last_name", "")
        if name:
            inventor_names.append(name.strip())

    # Requerentes
    applicants_raw = parties.get("applicants", [])
    applicant_names = []
    for app in applicants_raw:
        app_name = app.get("applicant_name", {})
        name = app_name.get("name", "") or app_name.get("last_name", "")
        if name:
            applicant_names.append(name.strip())

    records.append({
        "ano": year,
        "pais": country,
        "inventores": inventor_names,
        "empresas": applicant_names,
        "titulo": title
    })

df = pd.DataFrame(records)

# ── Métricas rápidas ───────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.metric("Total de patentes (API)", f"{total_api:,}".replace(",", "."))
col2.metric("Registros carregados", len(df))
col3.metric("Anos cobertos", df["ano"].nunique())

st.divider()

# ── Gráfico 1: Patentes por Ano ───────────────────────────────────────────────
st.subheader("📅 Patentes por Ano")
df_anos = df.groupby("ano").size().reset_index(name="Patentes")
df_anos = df_anos[df_anos["ano"] != "Desconhecido"].sort_values("ano")

if not df_anos.empty:
    chart_anos = (
        alt.Chart(df_anos)
        .mark_line(point=True, color="#1f77b4")
        .encode(
            x=alt.X("ano:O", title="Ano"),
            y=alt.Y("Patentes:Q", title="Número de Patentes"),
            tooltip=["ano", "Patentes"]
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(chart_anos, use_container_width=True)
else:
    st.info("Sem dados de ano disponíveis.")

st.divider()

# ── Gráficos 2 e 3: Inventores e Empresas ────────────────────────────────────
col_inv, col_emp = st.columns(2)

with col_inv:
    st.subheader("👤 Top Inventores")
    inv_list = [n for sub in df["inventores"] for n in sub if n]
    if inv_list:
        df_inv = pd.Series(inv_list).value_counts().head(15).reset_index()
        df_inv.columns = ["Inventor", "Patentes"]
        df_inv = df_inv.sort_values("Patentes")
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

with col_emp:
    st.subheader("🏢 Top Empresas / Requerentes")
    emp_list = [n for sub in df["empresas"] for n in sub if n]
    if emp_list:
        df_emp = pd.Series(emp_list).value_counts().head(15).reset_index()
        df_emp.columns = ["Empresa", "Patentes"]
        df_emp = df_emp.sort_values("Patentes")
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

# ── Gráfico 4: Patentes por País ─────────────────────────────────────────────
st.subheader("🌎 Patentes por País")
df_pais = df.groupby("pais").size().reset_index(name="Patentes").sort_values("Patentes", ascending=False)

if not df_pais.empty:
    chart_pais = (
        alt.Chart(df_pais)
        .mark_bar(color="#9467bd")
        .encode(
            x=alt.X("pais:N", sort="-y", title="País"),
            y=alt.Y("Patentes:Q", title="Número de Patentes"),
            tooltip=["pais", "Patentes"]
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(chart_pais, use_container_width=True)

st.divider()

# ── Tabela ────────────────────────────────────────────────────────────────────
st.subheader("📋 Lista de Patentes")
df_tabela = df[["ano", "titulo", "pais"]].copy()
df_tabela.columns = ["Ano", "Título", "País"]
st.dataframe(df_tabela, use_container_width=True, hide_index=True)

st.caption("Dashboard desenvolvido com Streamlit + Altair (Vega-Lite) | Dados: Lens.org")