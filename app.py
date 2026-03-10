import streamlit as st
import requests
import re
import xml.etree.ElementTree as ET
import pandas as pd
import altair as alt
from collections import Counter

st.set_page_config(
    page_title="Dashboard de Patentes BR - IBICT",
    page_icon="📊",
    layout="wide"
)

# ── Namespaces WIPO ST96 ───────────────────────────────────────────────────────
PAT = "http://www.wipo.int/standards/XMLSchema/ST96/Patent"
COM = "http://www.wipo.int/standards/XMLSchema/ST96/Common"
def p(tag): return f"{{{PAT}}}{tag}"
def c(tag): return f"{{{COM}}}{tag}"

API_BASE = "https://pi-api-dev.ibict.br/api/v1/patente/"

# ── Busca e parse ──────────────────────────────────────────────────────────────

def parse_xml(xml_text):
    """Parseia XML WIPO ST96 e retorna lista de registros."""
    start = xml_text.find("<pat:PatentBag")
    if start == -1:
        return []
    xml_clean = re.sub(r"&(?!(amp|lt|gt|quot|apos);)", "&amp;", xml_text[start:])
    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError:
        return []

    records = []
    for b in root:
        pub_date = b.findtext(f"{p('PatentPublicationIdentification')}/{c('PublicationDate')}") or ""
        year = pub_date[:4] if pub_date else "Desconhecido"

        title = b.findtext(p("InventionTitle")) or "Sem título"

        office = b.findtext(f"{p('PatentPublicationIdentification')}/{c('IPOfficeCode')}") or "BR"

        applicants = [
            el.text for el in b.findall(f".//{p('ApplicantBag')}//{c('OrganizationStandardName')}")
            if el.text
        ]
        if not applicants:
            applicants = [
                el.text for el in b.findall(f".//{p('ApplicantBag')}//{c('FreeFormatName')}")
                if el.text
            ]

        inventors = [
            el.text for el in b.findall(f".//{p('InventorBag')}//{c('FreeFormatName')}")
            if el.text
        ]

        ipc_main = b.findtext(f".//{p('IPCClassification')}/{p('MainClassification')}") or ""
        ipc_further = [
            el.text for el in b.findall(f".//{p('IPCClassification')}/{p('FurtherClassification')}")
            if el.text
        ]
        all_ipc = ([ipc_main] if ipc_main else []) + ipc_further

        cpc_section = b.findtext(f".//{p('MainCPC')}//{p('CPCSection')}") or ""
        cpc_class   = b.findtext(f".//{p('MainCPC')}//{p('Class')}") or ""
        cpc_sub     = b.findtext(f".//{p('MainCPC')}//{p('Subclass')}") or ""
        cpc_mg      = b.findtext(f".//{p('MainCPC')}//{p('MainGroup')}") or ""
        cpc_main_str = f"{cpc_section}{cpc_class}{cpc_sub} {cpc_mg}".strip() if cpc_section else ""

        further_cpcs = []
        for fc in b.findall(f".//{p('FurtherCPC')}"):
            s = fc.findtext(f".//{p('CPCSection')}") or ""
            cl = fc.findtext(f".//{p('Class')}") or ""
            sb = fc.findtext(f".//{p('Subclass')}") or ""
            mg = fc.findtext(f".//{p('MainGroup')}") or ""
            if s:
                further_cpcs.append(f"{s}{cl}{sb} {mg}".strip())
        all_cpc = ([cpc_main_str] if cpc_main_str else []) + further_cpcs

        records.append({
            "ano":        year,
            "titulo":     title,
            "pais":       office,
            "applicants": applicants,
            "inventors":  inventors,
            "ipc":        all_ipc,
            "cpc":        all_cpc,
            "pub_date":   pub_date,
        })
    return records

@st.cache_data(ttl=3600, show_spinner="Buscando patentes na API do IBICT...")
def load_data(pages=5):
    """Carrega múltiplas páginas da API."""
    all_records = []
    limit = 100
    for page in range(pages):
        offset = page * limit
        url = f"{API_BASE}?limit={limit}&offset={offset}"
        try:
            resp = requests.get(url, timeout=30, verify=False)
            if resp.status_code == 200:
                records = parse_xml(resp.text)
                if not records:
                    break
                all_records.extend(records)
            else:
                break
        except Exception as e:
            st.warning(f"Erro na página {page}: {e}")
            break
    return pd.DataFrame(all_records)

# ── Suprime warning de SSL ─────────────────────────────────────────────────────
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Interface ──────────────────────────────────────────────────────────────────
st.title("📊 Dashboard de Patentes Brasileiras")
st.caption("Fonte: IBICT — API pi-api-dev.ibict.br | Padrão WIPO ST96")

col_ctrl1, col_ctrl2 = st.columns([1, 3])
with col_ctrl1:
    pages = st.slider("Páginas a carregar (100 por página)", 1, 20, 5)
with col_ctrl2:
    if st.button("🔄 Carregar / Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

df = load_data(pages=pages)

if df.empty:
    st.error("Não foi possível carregar dados da API do IBICT.")
    st.stop()

# ── Métricas ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Registros carregados", f"{len(df):,}".replace(",", "."))
c2.metric("Anos cobertos", df[df["ano"] != "Desconhecido"]["ano"].nunique())
c3.metric("Países/Jurisdições", df["pais"].nunique())
total_inv = sum(len(x) for x in df["inventors"])
c4.metric("Total de inventores", f"{total_inv:,}".replace(",", "."))

st.divider()

# ── Gráfico 1: Patentes por Ano ───────────────────────────────────────────────
st.subheader("📅 Documentos de Patente ao Longo do Tempo")
df_anos = (
    df[df["ano"] != "Desconhecido"]
    .groupby("ano").size()
    .reset_index(name="Patentes")
    .sort_values("ano")
)
if not df_anos.empty:
    chart_anos = (
        alt.Chart(df_anos)
        .mark_bar(color="#2d8a4e")
        .encode(
            x=alt.X("ano:O", title="Ano de Publicação"),
            y=alt.Y("Patentes:Q", title="Contagem"),
            tooltip=["ano", "Patentes"]
        )
        .properties(height=320)
        .interactive()
    )
    st.altair_chart(chart_anos, use_container_width=True)

st.divider()

# ── Gráfico 2 e 3: Requerentes e Inventores ───────────────────────────────────
col_app, col_inv = st.columns(2)

with col_app:
    st.subheader("🏢 Principais Candidatos (Requerentes)")
    app_list = [str(n) for sub in df["applicants"] for n in sub if n]
    if app_list:
        df_app = pd.DataFrame(Counter(app_list).most_common(15), columns=["Requerente", "Patentes"])
        df_app = df_app.sort_values("Patentes")
        st.altair_chart(
            alt.Chart(df_app).mark_bar(color="#f58518")
            .encode(
                x=alt.X("Patentes:Q"),
                y=alt.Y("Requerente:N", sort="-x", title=""),
                tooltip=["Requerente", "Patentes"]
            ).properties(height=450),
            use_container_width=True
        )
    else:
        st.info("Sem dados de requerentes.")

with col_inv:
    st.subheader("👤 Principais Inventores")
    inv_list = [str(n) for sub in df["inventors"] for n in sub if n]
    if inv_list:
        df_inv = pd.DataFrame(Counter(inv_list).most_common(15), columns=["Inventor", "Patentes"])
        df_inv = df_inv.sort_values("Patentes")
        st.altair_chart(
            alt.Chart(df_inv).mark_bar(color="#54a24b")
            .encode(
                x=alt.X("Patentes:Q"),
                y=alt.Y("Inventor:N", sort="-x", title=""),
                tooltip=["Inventor", "Patentes"]
            ).properties(height=450),
            use_container_width=True
        )
    else:
        st.info("Sem dados de inventores.")

st.divider()

# ── Gráfico 4 e 5: CPC e IPC ──────────────────────────────────────────────────
col_cpc, col_ipc = st.columns(2)

with col_cpc:
    st.subheader("🗂️ Principais Classificações CPC")
    cpc_list = [str(c)[:7] for sub in df["cpc"] for c in sub if c]
    if cpc_list:
        df_cpc = pd.DataFrame(Counter(cpc_list).most_common(15), columns=["CPC", "count"])
        df_cpc = df_cpc.sort_values("count")
        st.altair_chart(
            alt.Chart(df_cpc).mark_bar(color="#e45756")
            .encode(
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
    ipc_list = [str(i)[:7] for sub in df["ipc"] for i in sub if i]
    if ipc_list:
        df_ipc = pd.DataFrame(Counter(ipc_list).most_common(15), columns=["IPC", "count"])
        df_ipc = df_ipc.sort_values("count")
        st.altair_chart(
            alt.Chart(df_ipc).mark_bar(color="#72b7b2")
            .encode(
                x=alt.X("count:Q", title="Patentes"),
                y=alt.Y("IPC:N", sort="-x", title=""),
                tooltip=["IPC", "count"]
            ).properties(height=420),
            use_container_width=True
        )
    else:
        st.info("Sem dados IPC.")

st.divider()

# ── Gráfico 6: Países ─────────────────────────────────────────────────────────
st.subheader("🌎 Documentos por País/Jurisdição")
df_pais = df.groupby("pais").size().reset_index(name="Patentes").sort_values("Patentes", ascending=False)
if not df_pais.empty:
    st.altair_chart(
        alt.Chart(df_pais).mark_bar(color="#4c78a8")
        .encode(
            x=alt.X("pais:N", sort="-y", title="País"),
            y=alt.Y("Patentes:Q"),
            tooltip=["pais", "Patentes"]
        ).properties(height=280).interactive(),
        use_container_width=True
    )

st.divider()

# ── Tabela ─────────────────────────────────────────────────────────────────────
st.subheader("📋 Lista de Patentes")
df_tab = df[["ano", "titulo", "pais", "pub_date"]].copy()
df_tab.columns = ["Ano", "Título", "País", "Data Publicação"]
st.dataframe(df_tab, use_container_width=True, hide_index=True)

st.caption("Dashboard Altair (Vega-Lite) | Dados: IBICT — WIPO ST96")