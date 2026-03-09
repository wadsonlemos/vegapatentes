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
            "term": {"jurisdiction": "BR"}
        },
        "size": size,
        "sort": [{"date_published": "desc"}]
    }
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=body, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"_error": f"{resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"_error": str(e)}

# ── Interface ──────────────────────────────────────────────────────────────────

st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: Lens.org Patent API — Jurisdição: BR | 1.088.978 patentes")

if st.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

data = fetch_patents(size=100)

if "_error" in data:
    st.error(f"Erro na API: {data['_error']}")
    st.stop()

hits = data.get("data", [])
total_raw = data.get("total", 0)
total_api = total_raw.get("value", total_raw) if isinstance(total_raw, dict) else int(total_raw or 0)

if not hits:
    st.warning("Nenhuma patente encontrada.")
    st.stop()

# ── Processar dados ────────────────────────────────────────────────────────────

records = []
for h in hits:
    # Ano — tenta vários campos possíveis
    year = "Desconhecido"
    for campo in ["date_published", "date_publ", "year_published"]:
        val = h.get(campo, "")
        if val:
            year = str(val)[:4]
            break

    # Jurisdição
    jurisdiction = h.get("jurisdiction", h.get("country", "Desconhecido"))

    # Biblio
    biblio = h.get("biblio", {})

    # Título
    titles = biblio.get("invention_title", [])
    if isinstance(titles, list) and titles:
        title = titles[0].get("text", "Sem título")
    elif isinstance(titles, str):
        title = titles
    else:
        title = "Sem título"

    # Inventores
    parties = biblio.get("parties", {})
    inventors_raw = parties.get("inventors", [])
    inventor_names = []
    for inv in inventors_raw:
        inv_name = inv.get("inventor_name", {})
        name = inv_name.get("name", "") or inv_name.get("last_name", "")
        if not name:
            name = inv.get("name", "")
        if name:
            inventor_names.append(name.strip())

    # Requerentes
    applicants_raw = parties.get("applicants", [])
    applicant_names = []
    for app in applicants_raw:
        app_name = app.get("applicant_name", {})
        name = app_name.get("name", "") or app_name.get("last_name", "")
        if not name:
            name = app.get("name", "")
        if name:
            applicant_names.append(name.strip())

    records.append({
        "ano": year,
        "jurisdicao": jurisdiction,
        "inventores": inventor_names,
        "empresas": applicant_names,
        "titulo": title
    })

df = pd.DataFrame(records)

# ── Métricas rápidas ───────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.metric("Total de patentes BR", f"{total_api:,}".replace(",", "."))
col2.metric("Registros nesta amostra", len(df))
col3.metric("Anos cobertos", df[df["ano"] != "Desconhecido"]["ano"].nunique())

st.divider()

# ── Gráfico 1: Patentes por Ano ───────────────────────────────────────────────
st.subheader("📅 Patentes por Ano (amostra)")
df_anos = df[df["ano"] != "Desconhecido"].groupby("ano").size().reset_index(name="Patentes").sort_values("ano")

if not df_anos.empty:
    chart_anos = (
        alt.Chart(df_anos)
        .mark_line(point=True, color="#1f77b4", strokeWidth=2)
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

# ── Gráficos 2 e 3 lado a lado ────────────────────────────────────────────────
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
                x=alt.X("Patentes:Q", title="Patentes"),
                y=alt.Y("Inventor:N", sort="-x", title=""),
                tooltip=["Inventor", "Patentes"]
            )
            .properties(height=420)
        )
        st.altair_chart(chart_inv, use_container_width=True)
    else:
        st.info("Sem dados de inventores nesta amostra.")

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
                x=alt.X("Patentes:Q", title="Patentes"),
                y=alt.Y("Empresa:N", sort="-x", title=""),
                tooltip=["Empresa", "Patentes"]
            )
            .properties(height=420)
        )
        st.altair_chart(chart_emp, use_container_width=True)
    else:
        st.info("Sem dados de empresas nesta amostra.")

st.divider()

# ── Gráfico 4: Jurisdição ─────────────────────────────────────────────────────
st.subheader("🌎 Patentes por Jurisdição")
df_jur = df.groupby("jurisdicao").size().reset_index(name="Patentes").sort_values("Patentes", ascending=False)

if not df_jur.empty:
    chart_jur = (
        alt.Chart(df_jur)
        .mark_bar(color="#9467bd")
        .encode(
            x=alt.X("jurisdicao:N", sort="-y", title="Jurisdição"),
            y=alt.Y("Patentes:Q", title="Patentes"),
            tooltip=["jurisdicao", "Patentes"]
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(chart_jur, use_container_width=True)

st.divider()

# ── Tabela ────────────────────────────────────────────────────────────────────
st.subheader("📋 Lista de Patentes")
df_tabela = df[["ano", "titulo", "jurisdicao"]].copy()
df_tabela.columns = ["Ano", "Título", "Jurisdição"]
st.dataframe(df_tabela, use_container_width=True, hide_index=True)

st.caption("Dashboard desenvolvido com Streamlit + Altair (Vega-Lite) | Dados: Lens.org")