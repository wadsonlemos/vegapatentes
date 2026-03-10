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

# Tema claro para todos os gráficos
alt.themes.enable("default")

JSON_URL = "https://raw.githubusercontent.com/wadsonlemos/vegapatentes/main/ibict_slim.json"

# ── Carrega dados ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Carregando dados do IBICT...")
def load_data():
    resp = requests.get(JSON_URL, timeout=60)
    data = resp.json()
    docs = data.get("results", [])
    records = []
    for d in docs:
        dep = d.get("deposit_year")
        con = d.get("concession_year")
        records.append({
            "titulo":        d.get("title", "Sem título"),
            "ano_deposito":  int(dep) if dep else None,
            "ano_concessao": int(con) if con else None,
            "pais":          d.get("country_code", "BR"),
            "status":        d.get("status", "Desconhecido") or "Desconhecido",
            "tipo":          d.get("patent_type", "Não informado") or "Não informado",
            "applicants":    d.get("applicants", []),
            "inventors":     d.get("inventors", []),
            "cpc":           [c[:7] for c in d.get("cpc", []) if c],
            "ipc":           [c[:7] for c in d.get("ipc", []) if c],
        })
    return pd.DataFrame(records), data.get("total", len(docs))

if st.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

df, total = load_data()

if df.empty:
    st.error("Não foi possível carregar os dados.")
    st.stop()

# ── Filtros sidebar ────────────────────────────────────────────────────────────
st.sidebar.header("🔎 Filtros")
anos_disp = sorted([int(a) for a in df["ano_deposito"].dropna().unique()])
ano_range = st.sidebar.select_slider("Ano de Depósito", options=anos_disp, value=(min(anos_disp), max(anos_disp)))
status_opts = sorted(df["status"].unique())
status_sel = st.sidebar.multiselect("Status", status_opts, default=[])
tipo_opts = sorted(df["tipo"].unique())
tipo_sel = st.sidebar.multiselect("Tipo", tipo_opts, default=[])

dff = df[df["ano_deposito"].between(ano_range[0], ano_range[1])]
if status_sel:
    dff = dff[dff["status"].isin(status_sel)]
if tipo_sel:
    dff = dff[dff["tipo"].isin(tipo_sel)]

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("📊 Dashboard de Patentes Brasileiras")
st.caption(f"Fonte: IBICT — pi-api-dev.ibict.br | {total:,} registros na base".replace(",", "."))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total na base", f"{total:,}".replace(",", "."))
m2.metric("Registros filtrados", f"{len(dff):,}".replace(",", "."))
m3.metric("Anos cobertos", dff["ano_deposito"].nunique())
m4.metric("Status distintos", dff["status"].nunique())

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 1 — STACKED BAR CHART: Patentes por ano empilhadas por status
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("📅 Patentes por Ano — Stacked Bar Chart")
st.caption("Contagem de patentes depositadas por ano, empilhadas por status")

df_stacked = (
    dff.dropna(subset=["ano_deposito"])
    .groupby(["ano_deposito", "status"]).size()
    .reset_index(name="count")
)

chart_stacked = (
    alt.Chart(df_stacked)
    .mark_bar()
    .encode(
        x=alt.X("ano_deposito:O", title="Ano de Depósito", axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("count:Q", title="Número de Patentes"),
        color=alt.Color("status:N", title="Status",
            scale=alt.Scale(scheme="tableau10")),
        tooltip=["ano_deposito", "status", "count"]
    )
    .properties(height=380)
    .configure_axis(grid=False)
    .configure_view(strokeWidth=0)
    .interactive()
)
st.altair_chart(chart_stacked, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 2 — GROUPED BAR CHART: CPC vs IPC comparados por ano
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("📊 Top Classificações — Grouped Bar Chart")
st.caption("Comparação entre as principais classificações CPC e IPC")

cpc_counter = Counter([x for sub in dff["cpc"] for x in sub if x])
ipc_counter = Counter([x for sub in dff["ipc"] for x in sub if x])

top_cpc = pd.DataFrame(cpc_counter.most_common(10), columns=["codigo", "count"])
top_cpc["tipo"] = "CPC"
top_ipc = pd.DataFrame(ipc_counter.most_common(10), columns=["codigo", "count"])
top_ipc["tipo"] = "IPC"
df_grouped = pd.concat([top_cpc, top_ipc])

chart_grouped = (
    alt.Chart(df_grouped)
    .mark_bar()
    .encode(
        x=alt.X("count:Q", title="Número de Patentes"),
        y=alt.Y("codigo:N", sort="-x", title="Classificação"),
        color=alt.Color("tipo:N", title="Sistema",
            scale=alt.Scale(domain=["CPC", "IPC"], range=["#4c78a8", "#f58518"])),
        yOffset="tipo:N",
        tooltip=["codigo", "tipo", "count"]
    )
    .properties(height=420)
    .configure_axis(grid=False)
    .configure_view(strokeWidth=0)
)
st.altair_chart(chart_grouped, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 3 — NORMALIZED 100% STACKED BAR: Distribuição de status por ano
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("📈 Distribuição de Status por Ano — Normalized 100% Stacked Bar")
st.caption("Proporção de cada status ao longo dos anos (100%)")

df_norm = (
    dff.dropna(subset=["ano_deposito"])
    .groupby(["ano_deposito", "status"]).size()
    .reset_index(name="count")
)

chart_norm = (
    alt.Chart(df_norm)
    .mark_bar()
    .encode(
        x=alt.X("ano_deposito:O", title="Ano de Depósito", axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("count:Q", stack="normalize", title="Proporção (%)",
                axis=alt.Axis(format="%")),
        color=alt.Color("status:N", title="Status",
            scale=alt.Scale(scheme="tableau10")),
        tooltip=["ano_deposito", "status", "count"]
    )
    .properties(height=350)
    .configure_axis(grid=False)
    .configure_view(strokeWidth=0)
    .interactive()
)
st.altair_chart(chart_norm, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 4 — GANTT CHART: Tempo entre depósito e concessão por requerente
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("⏱️ Tempo de Concessão por Requerente — Gantt Chart")
st.caption("Linha do tempo entre ano de depósito e concessão dos principais requerentes")

df_gantt = dff.dropna(subset=["ano_deposito", "ano_concessao"]).copy()
df_gantt = df_gantt[df_gantt["ano_concessao"] >= df_gantt["ano_deposito"]]
df_gantt["requerente"] = df_gantt["applicants"].apply(lambda x: x[0] if x else "Desconhecido")

top_req = df_gantt["requerente"].value_counts().head(15).index.tolist()
df_gantt_top = df_gantt[df_gantt["requerente"].isin(top_req)]

df_gantt_agg = (
    df_gantt_top.groupby("requerente")
    .agg(inicio=("ano_deposito", "min"), fim=("ano_concessao", "max"), total=("titulo", "count"))
    .reset_index()
    .sort_values("inicio")
)

chart_gantt = (
    alt.Chart(df_gantt_agg)
    .mark_bar(height=18, cornerRadiusEnd=4)
    .encode(
        x=alt.X("inicio:Q", title="Ano", scale=alt.Scale(zero=False)),
        x2="fim:Q",
        y=alt.Y("requerente:N", sort="-x", title=""),
        color=alt.Color("total:Q", title="Total de patentes",
            scale=alt.Scale(scheme="blues")),
        tooltip=["requerente", "inicio", "fim", "total"]
    )
    .properties(height=420)
    .configure_axis(grid=False)
    .configure_view(strokeWidth=0)
    .interactive()
)
st.altair_chart(chart_gantt, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 5 — TOP INVENTORES E REQUERENTES
# ══════════════════════════════════════════════════════════════════════════════
col_app, col_inv = st.columns(2)

with col_app:
    st.subheader("🏢 Principais Requerentes")
    app_list = [str(n) for sub in dff["applicants"] for n in sub if n]
    if app_list:
        df_app = pd.DataFrame(Counter(app_list).most_common(15), columns=["Requerente", "Patentes"]).sort_values("Patentes")
        st.altair_chart(
            alt.Chart(df_app).mark_bar(color="#4c78a8", cornerRadiusEnd=4).encode(
                x="Patentes:Q",
                y=alt.Y("Requerente:N", sort="-x", title=""),
                tooltip=["Requerente", "Patentes"]
            ).properties(height=420)
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0),
            use_container_width=True
        )

with col_inv:
    st.subheader("👤 Principais Inventores")
    inv_list = [str(n) for sub in dff["inventors"] for n in sub if n]
    if inv_list:
        df_inv = pd.DataFrame(Counter(inv_list).most_common(15), columns=["Inventor", "Patentes"]).sort_values("Patentes")
        st.altair_chart(
            alt.Chart(df_inv).mark_bar(color="#54a24b", cornerRadiusEnd=4).encode(
                x="Patentes:Q",
                y=alt.Y("Inventor:N", sort="-x", title=""),
                tooltip=["Inventor", "Patentes"]
            ).properties(height=420)
            .configure_axis(grid=False)
            .configure_view(strokeWidth=0),
            use_container_width=True
        )

st.divider()

# ── Tabela ─────────────────────────────────────────────────────────────────────
st.subheader("📋 Lista de Patentes")
df_tab = dff[["ano_deposito", "titulo", "status", "tipo", "pais"]].copy()
df_tab.columns = ["Ano Depósito", "Título", "Status", "Tipo", "País"]
st.dataframe(df_tab, use_container_width=True, hide_index=True)

st.caption("Dashboard com Altair (Vega-Lite) | Dados: IBICT")