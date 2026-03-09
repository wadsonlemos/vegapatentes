import streamlit as st
import pandas as pd
import altair as alt
import json
import requests
from collections import Counter

st.set_page_config(
    page_title="Dashboard de Patentes BR",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: Lens.org — Jurisdição: BR")

# ── Carrega o JSON do GitHub ───────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Carregando dados de patentes...")
def load_data():
    url = "https://raw.githubusercontent.com/wadsonlemos/vegapatentes/main/patentes.json"
    resp = requests.get(url, timeout=60)
    data = resp.json()
    docs = data.get("results", {}).get("docs", [])
    total = data.get("results", {}).get("docsMatched", len(docs))

    records = []
    for d in docs:
        pub_date = d.get("publicationDate", "")
        year = pub_date[:4] if pub_date else "Desconhecido"

        records.append({
            "ano":           year,
            "titulo":        d.get("title", "Sem título"),
            "jurisdicao":    d.get("jurisdiction", "Desconhecido"),
            "docType":       d.get("docType", "Desconhecido"),
            "applicants":    d.get("applicants", []),
            "inventors":     d.get("inventors", []),
            "owners":        d.get("owners", []),
            "cpc":           d.get("cpcClassifications", []),
            "ipcr":          d.get("ipcrClassifications", []),
            "citedBy":       d.get("citedByPatentCount", 0),
            "familySize":    d.get("simpleFamilySize", 0),
            "url":           d.get("url", ""),
            "filingDate":    d.get("filingDate", ""),
            "publicationDate": pub_date,
        })

    return pd.DataFrame(records), total

if st.button("🔄 Atualizar dados"):
    st.cache_data.clear()
    st.rerun()

df, total_matched = load_data()

# ── Métricas ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total de Patentes BR", f"{total_matched:,}".replace(",", "."))
c2.metric("Registros carregados", f"{len(df):,}".replace(",", "."))
c3.metric("Anos cobertos", df[df["ano"] != "Desconhecido"]["ano"].nunique())
c4.metric("Tipos de documento", df["docType"].nunique())

st.divider()

# ── Gráfico 1: Patentes ao longo do tempo por tipo ────────────────────────────
st.subheader("📅 Documentos de Patente ao Longo do Tempo")

df_tempo = (
    df[df["ano"] != "Desconhecido"]
    .groupby(["ano", "docType"])
    .size()
    .reset_index(name="count")
    .sort_values("ano")
)

chart_tempo = (
    alt.Chart(df_tempo)
    .mark_bar()
    .encode(
        x=alt.X("ano:O", title="Ano de Publicação"),
        y=alt.Y("count:Q", title="Contagem de Documentos"),
        color=alt.Color("docType:N", title="Tipo de Documento"),
        tooltip=["ano", "docType", "count"]
    )
    .properties(height=350)
    .interactive()
)
st.altair_chart(chart_tempo, use_container_width=True)

st.divider()

# ── Gráficos 2: Pizza por tipo + Jurisdição ───────────────────────────────────
col_pizza, col_jur = st.columns(2)

with col_pizza:
    st.subheader("🥧 Patentes por Tipo")
    df_tipo = df.groupby("docType").size().reset_index(name="count")
    chart_pizza = (
        alt.Chart(df_tipo)
        .mark_arc(innerRadius=60)
        .encode(
            theta=alt.Theta("count:Q"),
            color=alt.Color("docType:N", title="Tipo"),
            tooltip=["docType", "count"]
        )
        .properties(height=320)
    )
    st.altair_chart(chart_pizza, use_container_width=True)

with col_jur:
    st.subheader("🌎 Patentes por Jurisdição")
    df_jur = df.groupby("jurisdicao").size().reset_index(name="count").sort_values("count", ascending=False).head(20)
    chart_jur = (
        alt.Chart(df_jur)
        .mark_bar(color="#4c78a8")
        .encode(
            x=alt.X("jurisdicao:N", sort="-y", title="Jurisdição"),
            y=alt.Y("count:Q", title="Patentes"),
            tooltip=["jurisdicao", "count"]
        )
        .properties(height=320)
    )
    st.altair_chart(chart_jur, use_container_width=True)

st.divider()

# ── Gráficos 3: Top Inventores + Top Requerentes ──────────────────────────────
col_inv, col_app = st.columns(2)

with col_inv:
    st.subheader("👤 Principais Inventores")
    inv_list = [n for sub in df["inventors"] for n in sub if n]
    if inv_list:
        df_inv = pd.DataFrame(Counter(inv_list).most_common(20), columns=["Inventor", "Patentes"])
        df_inv = df_inv.sort_values("Patentes")
        chart_inv = (
            alt.Chart(df_inv)
            .mark_bar(color="#54a24b")
            .encode(
                x=alt.X("Patentes:Q"),
                y=alt.Y("Inventor:N", sort="-x", title=""),
                tooltip=["Inventor", "Patentes"]
            )
            .properties(height=500)
        )
        st.altair_chart(chart_inv, use_container_width=True)
    else:
        st.info("Sem dados de inventores.")

with col_app:
    st.subheader("🏢 Principais Candidatos (Requerentes)")
    app_list = [n for sub in df["applicants"] for n in sub if n]
    if app_list:
        df_app = pd.DataFrame(Counter(app_list).most_common(20), columns=["Requerente", "Patentes"])
        df_app = df_app.sort_values("Patentes")
        chart_app = (
            alt.Chart(df_app)
            .mark_bar(color="#f58518")
            .encode(
                x=alt.X("Patentes:Q"),
                y=alt.Y("Requerente:N", sort="-x", title=""),
                tooltip=["Requerente", "Patentes"]
            )
            .properties(height=500)
        )
        st.altair_chart(chart_app, use_container_width=True)
    else:
        st.info("Sem dados de requerentes.")

st.divider()

# ── Gráfico 4: Top Proprietários ──────────────────────────────────────────────
st.subheader("🏛️ Principais Proprietários")
own_list = [n for sub in df["owners"] for n in sub if n]
if own_list:
    df_own = pd.DataFrame(Counter(own_list).most_common(20), columns=["Proprietário", "Patentes"])
    df_own = df_own.sort_values("Patentes")
    chart_own = (
        alt.Chart(df_own)
        .mark_bar(color="#9467bd")
        .encode(
            x=alt.X("Patentes:Q"),
            y=alt.Y("Proprietário:N", sort="-x", title=""),
            tooltip=["Proprietário", "Patentes"]
        )
        .properties(height=400)
    )
    st.altair_chart(chart_own, use_container_width=True)
else:
    st.info("Sem dados de proprietários nesta amostra.")

st.divider()

# ── Gráfico 5: Top Classificações CPC ────────────────────────────────────────
col_cpc, col_ipcr = st.columns(2)

with col_cpc:
    st.subheader("🗂️ Top Classificações CPC")
    cpc_list = [c[:7] for sub in df["cpc"] for c in sub if c]
    if cpc_list:
        df_cpc = pd.DataFrame(Counter(cpc_list).most_common(15), columns=["CPC", "count"])
        df_cpc = df_cpc.sort_values("count")
        chart_cpc = (
            alt.Chart(df_cpc)
            .mark_bar(color="#e45756")
            .encode(
                x=alt.X("count:Q", title="Patentes"),
                y=alt.Y("CPC:N", sort="-x", title=""),
                tooltip=["CPC", "count"]
            )
            .properties(height=420)
        )
        st.altair_chart(chart_cpc, use_container_width=True)
    else:
        st.info("Sem dados CPC.")

with col_ipcr:
    st.subheader("🗂️ Top Classificações IPCR")
    ipcr_list = [c[:7] for sub in df["ipcr"] for c in sub if c]
    if ipcr_list:
        df_ipcr = pd.DataFrame(Counter(ipcr_list).most_common(15), columns=["IPCR", "count"])
        df_ipcr = df_ipcr.sort_values("count")
        chart_ipcr = (
            alt.Chart(df_ipcr)
            .mark_bar(color="#72b7b2")
            .encode(
                x=alt.X("count:Q", title="Patentes"),
                y=alt.Y("IPCR:N", sort="-x", title=""),
                tooltip=["IPCR", "count"]
            )
            .properties(height=420)
        )
        st.altair_chart(chart_ipcr, use_container_width=True)
    else:
        st.info("Sem dados IPCR.")

st.divider()

# ── Gráfico 6: Bubble chart — Patentes mais citadas ───────────────────────────
st.subheader("🫧 Patentes Mais Citadas")
df_bubble = df[df["citedBy"] > 0].copy()
df_bubble["ano_num"] = pd.to_numeric(df_bubble["ano"], errors="coerce")

if not df_bubble.empty:
    chart_bubble = (
        alt.Chart(df_bubble)
        .mark_circle(opacity=0.6)
        .encode(
            x=alt.X("ano_num:Q", title="Ano de Publicação", scale=alt.Scale(zero=False)),
            y=alt.Y("citedBy:Q", title="Citado por (Patentes)"),
            size=alt.Size("familySize:Q", title="Tamanho da Família", scale=alt.Scale(range=[20, 800])),
            color=alt.Color("docType:N", title="Tipo"),
            tooltip=["titulo", "ano", "citedBy", "familySize", "docType"]
        )
        .properties(height=400)
        .interactive()
    )
    st.altair_chart(chart_bubble, use_container_width=True)
else:
    st.info("Sem dados de citações nesta amostra.")

st.divider()

# ── Tabela ────────────────────────────────────────────────────────────────────
st.subheader("📋 Lista de Patentes")
df_tabela = df[["ano", "titulo", "docType", "jurisdicao", "citedBy"]].copy()
df_tabela.columns = ["Ano", "Título", "Tipo", "Jurisdição", "Citações"]
st.dataframe(df_tabela, use_container_width=True, hide_index=True)

st.caption("Dashboard desenvolvido com Streamlit + Altair | Dados: Lens.org")