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
        "include": [
            "date_published",
            "jurisdiction",
            "inventor",
            "applicant",
            "biblio.invention_title"
        ],
        "sort": [{"date_published": "desc"}]
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

if st.button("🔄 Carregar / Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

data = fetch_patents(size=100)

if not data:
    st.stop()

hits = data.get("data", [])
total_api = data.get("total", {}).get("value", 0)

if not hits:
    st.warning("Nenhuma patente encontrada.")
    st.stop()

# ── Processar dados ────────────────────────────────────────────────────────────

records = []
for h in hits:
    date = h.get("date_published", "")
    year = date[:4] if date else "Desconhecido"
    jurisdiction = h.get("jurisdiction", "Desconhecido")
    inventors = h.get("inventor", [])
    inventor_names = [i.get("name", "") for i in inventors if i.get("name")]
    applicants = h.get("applicant", [])
    applicant_names = [a.get("name", "") for a in applicants if a.get("name")]
    titles = h.get("biblio", {}).get("invention_title", [])
    title = titles[0].get("text", "Sem título") if titles else "Sem título"

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
col1.metric("Total de patentes (API)", f"{total_api:,}".replace(",", "."))
col2.metric("Registros carregados", len(df))
col3.metric("Anos cobertos", df["ano"].nunique())

st.divider()

# ── Gráfico 1: Patentes por Ano ───────────────────────────────────────────────
st.subheader("📅 Patentes por Ano")
df_anos = df.groupby("ano").size().reset_index(name="Patentes")
df_anos = df_anos[df_anos["ano"] != "Desconhecido"].sort_values("ano")

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

st.divider()

# ── Gráficos 2 e 3: Inventores e Empresas ────────────────────────────────────
col_inv, col_emp = st.columns(2)

with col_inv:
    st.subheader("👤 Top Inventores")
    inv_list = [nome for sublist in df["inventores"] for nome in sublist if nome]
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
    emp_list = [nome for sublist in df["empresas"] for nome in sublist if nome]
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

# ── Gráfico 4: Patentes por Jurisdição ───────────────────────────────────────
st.subheader("🌎 Patentes por Jurisdição")
df_jur = df.groupby("jurisdicao").size().reset_index(name="Patentes").sort_values("Patentes", ascending=False)

chart_jur = (
    alt.Chart(df_jur)
    .mark_bar(color="#9467bd")
    .encode(
        x=alt.X("jurisdicao:N", sort="-y", title="Jurisdição"),
        y=alt.Y("Patentes:Q", title="Número de Patentes"),
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