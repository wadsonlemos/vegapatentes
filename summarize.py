import json
import os
import sys
from collections import Counter

# Configurações
CACHE_FILE = 'ibict_cache.json'
SUMMARY_FILE = 'ibict_summary.json'

def summarize():
    if not os.path.exists(CACHE_FILE):
        print(f"Erro: Arquivo {CACHE_FILE} não encontrado.")
        return

    print(f"Lendo {CACHE_FILE} ({os.path.getsize(CACHE_FILE) / 1024 / 1024:.1f} MB)...")
    
    # Estrutura para os agregados
    # Usamos conjuntos e contadores para minimizar memória
    available_years = set()
    available_statuses = set()
    available_tipos = set()
    agg_year_status = Counter()
    applicant_counter = Counter()
    inventor_counter = Counter()
    cpc_counter = Counter()
    ipc_counter = Counter()
    gantt_raw = {} # {req: {min, max, count}}
    recent_table = [] # Pequena amostra para a tabela
    total_base = [0] # List for mutability in closure

    def process_record(d):
        # Ignora objetos que não pareçam uma patente (como o root "total")
        if not isinstance(d, dict) or ("title" not in d and "status" not in d):
            return

        total_base[0] += 1
        
        ano = d.get("deposit_year")
        try:
            if ano: ano = int(ano)
            else: ano = 0
        except: ano = 0

        status = d.get("status") or "Desconhecido"
        tipo = d.get("patent_type") or "Não informado"
        
        if ano > 0:
            available_years.add(ano)
            agg_year_status[(str(ano), status)] += 1
        
        available_statuses.add(status)
        available_tipos.add(tipo)

        # Requerentes e Inventores
        apps = d.get("applicants") or []
        for a in apps:
            name = a.get("name") if isinstance(a, dict) else str(a)
            if name: applicant_counter[name] += 1
            
        invs = d.get("inventors") or []
        for i in invs:
            name = i.get("name") if isinstance(i, dict) else str(i)
            if name: inventor_counter[name] += 1
            
        # Classificações
        cls = d.get("classification") or {}
        for c in (cls.get("cpc") or []):
            code = (c.get("text") or "")[:7]
            if code: cpc_counter[code] += 1
        for c in (cls.get("ipc") or []):
            code = (c.get("text") or "")[:7]
            if code: ipc_counter[code] += 1

        # Gantt Data (ano_concessao)
        conc_yr = d.get("concession_year")
        try:
            if conc_yr: conc_yr = int(conc_yr)
            else: conc_yr = 0
        except: conc_yr = 0

        if ano > 0 and conc_yr > 0 and conc_yr >= ano:
            req = (apps[0].get("name") if apps and isinstance(apps[0], dict) else str(apps[0])) if apps else "Desconhecido"
            if req not in gantt_raw: gantt_raw[req] = {"min": 9999, "max": 0, "count": 0}
            gantt_raw[req]["min"] = min(gantt_raw[req]["min"], ano)
            gantt_raw[req]["max"] = max(gantt_raw[req]["max"], conc_yr)
            gantt_raw[req]["count"] += 1

        # Guarda registro recente para a tabela (amostra de 100)
        if total_base[0] <= 100:
            recent_table.append({
                "deposit_year": d.get("deposit_year"),
                "title": d.get("title"),
                "status": d.get("status"),
                "patent_type": d.get("patent_type"),
                "country": d.get("country")
            })

    def object_hook(obj):
        process_record(obj)
        # Retorna o dict se for um sub-objeto pequeno, mas patentes são grandes.
        # Infelizmente, json.load ainda constrói a lista superior.
        # No entanto, se retornarmos o próprio objeto, ele fica na lista. 
        # Se retornarmos None, a lista terá Nones.
        # Como o root é um dict com "results", "results" terá uma lista de Nones se retornarmos None para as patentes.
        # Mas patentes são dicionários. Se retornarmos None, o ijson.load continuará.
        if "title" in obj or "status" in obj:
            return None 
        return obj

    print("Iniciando processamento...")
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            json.load(f, object_hook=object_hook)
    except Exception as e:
        print(f"Erro no processamento: {e}")

    print("Gerando JSON final de resumo...")
    summary = {
        "ready": True,
        "total_base": total_base[0],
        "filtered_count": total_base[0],
        "available_years": sorted([y for y in available_years if y > 0]),
        "available_statuses": sorted(list(available_statuses)),
        "available_tipos": sorted(list(available_tipos)),
        
        "agg_year_status": [{"ano": k[0], "status": k[1], "count": v} for k, v in agg_year_status.items()],
        "top_applicants": [{"name": k, "count": v} for k, v in applicant_counter.most_common(15)],
        "top_inventors": [{"name": k, "count": v} for k, v in inventor_counter.most_common(15)],
        "top_cpc": [{"codigo": k, "sistema": "CPC", "count": v} for k, v in cpc_counter.most_common(10)],
        "top_ipc": [{"codigo": k, "sistema": "IPC", "count": v} for k, v in ipc_counter.most_common(10)],
        
        "gantt_data": sorted([
            {"requerente": k, "inicio": v["min"], "fim": v["max"], "total": v["count"]} 
            for k, v in gantt_raw.items()
        ], key=lambda x: x["total"], reverse=True)[:15],
        
        "recent_table": recent_table
    }

    with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Sucesso! Resumo gerado em {SUMMARY_FILE} ({os.path.getsize(SUMMARY_FILE)/1024:.1f} KB)")

if __name__ == "__main__":
    summarize()
