import streamlit as st
import requests
import pandas as pd
import altair as alt
from collections import Counter

st.set_page_config(
    page_title="Dashboard de Patentes BR - IBICT",
    page_icon="📊",
    layout="wide"
)

JSON_URL = "https://raw.githubusercontent.com/wadsonlemos/vegapatentes/main/ibict_slim.json"

# ── Carrega dados ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Carregando dados do IBICT...")
def load_data():
    resp = requests.get(JSON_URL, timeout=60)
    data = resp.json()
    docs = data.get("results", [])

    records = []
    for d in docs:
        records.append({
            "titulo":       d.get("title", "Sem título"),
            "ano_deposito": str(d.get("deposit_year", "")) or "Desconhecido",
            "ano_concessao":str(d.get("concession_year", "")) if d.get("concession_year") else "Pendente",
            "pais":         d.get("country_code", "BR"),
            "status":       d.get("status", "Desconhecido"),
            "tipo":         d.get("patent_type", "Desconhecido") or "Não informado",
            "applicants":   d.get("applicants", []),
            "inventors":    d.get("inventors", []),
            "cpc":          [c[:7] for c in d.get("cpc", []) if c],
            "ipc":          [c[:7] for c in d.get("ipc", []) if c],
        })
    return pd.DataFrame(records), data.get("total", len(docs))

# ── Interface ──────────────────────────────────────────────────────────────────
st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: IBICT — pi-api-dev.ibict.br | 10.000 registros")

if st.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

df, total = load_data()

if df.empty:
    st.error("Não foi possível carregar os dados.")
    st.stop()

# ── Filtros na sidebar ─────────────────────────────────────────────────────────
st.sidebar.header("🔎 Filtros")

anos = sorted([a for a in df["ano_deposito"].unique() if a != "Desconhecido"])
ano_sel = st.sidebar.multiselect("Ano de Depósito", anos, default=[])

status_opts = sorted(df["status"].unique())
status_sel = st.sidebar.multiselect("Status", status_opts, default=[])

tipo_opts = sorted(df["tipo"].unique())
tipo_sel = st.sidebar.multiselect("Tipo de Patente", tipo_opts, default=[])

# Aplica filtros
dff = df.copy()
if ano_sel:
    dff = dff[dff["ano_deposito"].isin(ano_sel)]
if status_sel:
    dff = dff[dff["status"].isin(status_sel)]
if tipo_sel:
    dff = dff[dff["tipo"].isin(tipo_sel)]

# ── Métricas ───────────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total na base IBICT", f"{total:,}".replace(",", "."))
m2.metric("Registros filtrados", f"{len(dff):,}".replace(",", "."))
m3.metric("Anos cobertos", dff[dff["ano_deposito"] != "Desconhecido"]["ano_deposito"].nunique())
m4.metric("Status distintos", dff["status"].nunique())

st.divider()

# ── Gráfico 1: Patentes ao longo do tempo por status ──────────────────────────
st.subheader("📅 Documentos de Patente ao Longo do Tempo")
df_tempo = (
    dff[dff["ano_deposito"] != "Desconhecido"]
    .groupby(["ano_deposito", "status"]).size()
    .reset_index(name="count")
    .sort_values("ano_deposito")
)
if not df_tempo.empty:
    st.altair_chart(
        alt.Chart(df_tempo).mark_bar().encode(
            x=alt.X("ano_deposito:O", title="Ano de Depósito"),
            y=alt.Y("count:Q", title="Contagem"),
            color=alt.Color("status:N", title="Status"),
            tooltip=["ano_deposito", "status", "count"]
        ).properties(height=350).interactive(),
        use_container_width=True
    )

st.divider()

# ── Gráfico 2: Pizza por status + Pizza por tipo ───────────────────────────────
col_s, col_t = st.columns(2)

with col_s:
    st.subheader("🥧 Patentes por Status")
    df_status = dff.groupby("status").size().reset_index(name="count")
    st.altair_chart(
        alt.Chart(df_status).mark_arc(innerRadius=60).encode(
            theta="count:Q",
            color=alt.Color("status:N", title="Status"),
            tooltip=["status", "count"]
        ).properties(height=300),
        use_container_width=True
    )

with col_t:
    st.subheader("🥧 Patentes por Tipo")
    df_tipo = dff.groupby("tipo").size().reset_index(name="count")
    st.altair_chart(
        alt.Chart(df_tipo).mark_arc(innerRadius=60).encode(
            theta="count:Q",
            color=alt.Color("tipo:N", title="Tipo"),
            tooltip=["tipo", "count"]
        ).properties(height=300),
        use_container_width=True
    )

st.divider()

# ── Gráfico 3 e 4: Requerentes e Inventores ───────────────────────────────────
col_app, col_inv = st.columns(2)

with col_app:
    st.subheader("🏢 Principais Candidatos (Requerentes)")
    app_list = [str(n) for sub in dff["applicants"] for n in sub if n]
    if app_list:
        df_app = pd.DataFrame(Counter(app_list).most_common(15), columns=["Requerente", "Patentes"]).sort_values("Patentes")
        st.altair_chart(
            alt.Chart(df_app).mark_bar(color="#f58518").encode(
                x="Patentes:Q",
                y=alt.Y("Requerente:N", sort="-x", title=""),
                tooltip=["Requerente", "Patentes"]
            ).properties(height=450),
            use_container_width=True
        )
    else:
        st.info("Sem dados de requerentes.")

with col_inv:
    st.subheader("👤 Principais Inventores")
    inv_list = [str(n) for sub in dff["inventors"] for n in sub if n]
    if inv_list:
        df_inv = pd.DataFrame(Counter(inv_list).most_common(15), columns=["Inventor", "Patentes"]).sort_values("Patentes")
        st.altair_chart(
            alt.Chart(df_inv).mark_bar(color="#54a24b").encode(
                x="Patentes:Q",
                y=alt.Y("Inventor:N", sort="-x", title=""),
                tooltip=["Inventor", "Patentes"]
            ).properties(height=450),
            use_container_width=True
        )
    else:
        st.info("Sem dados de inventores.")

st.divider()

# ── Gráfico 5 e 6: CPC e IPC ──────────────────────────────────────────────────
col_cpc, col_ipc = st.columns(2)

with col_cpc:
    st.subheader("🗂️ Principais Classificações CPC")
    cpc_list = [str(x) for sub in dff["cpc"] for x in sub if x]
    if cpc_list:
        df_cpc = pd.DataFrame(Counter(cpc_list).most_common(15), columns=["CPC", "count"]).sort_values("count")
        st.altair_chart(
            alt.Chart(df_cpc).mark_bar(color="#e45756").encode(
                x=alt.X("count:Q", title="Patentes"),
                y=alt.Y("CPC:N", sort="-x", title=""),
                tooltip=["CPC", "count"]
            ).properties(height=420),
            use_container_width=True
        )
    else:
        st.info("Sem dados CPC.")

with col_ipc:
    st.subheader("🗂️ Principais Classificações IPC")
    ipc_list = [str(x) for sub in dff["ipc"] for x in sub if x]
    if ipc_list:
        df_ipc = pd.DataFrame(Counter(ipc_list).most_common(15), columns=["IPC", "count"]).sort_values("count")
        st.altair_chart(
            alt.Chart(df_ipc).mark_bar(color="#72b7b2").encode(
                x=alt.X("count:Q", title="Patentes"),
                y=alt.Y("IPC:N", sort="-x", title=""),
                tooltip=["IPC", "count"]
            ).properties(height=420),
            use_container_width=True
        )
    else:
        st.info("Sem dados IPC.")

st.divider()

# ── Gráfico 7: Ano de depósito vs concessão ───────────────────────────────────
st.subheader("⏱️ Tempo entre Depósito e Concessão")
df_tempo2 = dff[(dff["ano_deposito"] != "Desconhecido") & (dff["ano_concessao"] != "Pendente")].copy()
df_tempo2["deposito_num"] = pd.to_numeric(df_tempo2["ano_deposito"], errors="coerce")
df_tempo2["concessao_num"] = pd.to_numeric(df_tempo2["ano_concessao"], errors="coerce")
df_tempo2["tempo_anos"] = df_tempo2["concessao_num"] - df_tempo2["deposito_num"]
df_tempo2 = df_tempo2[(df_tempo2["tempo_anos"] >= 0) & (df_tempo2["tempo_anos"] <= 30)]

if not df_tempo2.empty:
    df_hist = df_tempo2.groupby("tempo_anos").size().reset_index(name="count")
    st.altair_chart(
        alt.Chart(df_hist).mark_bar(color="#4c78a8").encode(
            x=alt.X("tempo_anos:O", title="Anos até Concessão"),
            y=alt.Y("count:Q", title="Número de Patentes"),
            tooltip=["tempo_anos", "count"]
        ).properties(height=280).interactive(),
        use_container_width=True
    )
else:
    st.info("Sem dados suficientes para este gráfico.")

st.divider()

# ── Tabela ─────────────────────────────────────────────────────────────────────
st.subheader("📋 Lista de Patentes")
df_tab = dff[["ano_deposito", "titulo", "status", "tipo", "pais"]].copy()
df_tab.columns = ["Ano Depósito", "Título", "Status", "Tipo", "País"]
st.dataframe(df_tab, use_container_width=True, hide_index=True)

st.caption("Dashboard com Altair (Vega-Lite) | Dados: IBICT")