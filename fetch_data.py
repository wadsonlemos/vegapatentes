import requests
import json
import os
import time
import urllib3

# Suppress insecure request warnings if verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE = "https://pi-api-dev.ibict.br/api/v1/patentes/"
CACHE_FILE = "ibict_cache.json"

def fetch_year(year, limit=2000):
    all_results = []
    offset = 0
    print(f"--- Fetching Year: {year} ---")
    
    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "deposit_year": year
        }
        
        try:
            resp = requests.get(API_BASE, params=params, timeout=30, verify=False)
            if not resp.ok:
                # Se der erro com limite grande, reduz internamente e tenta de novo
                print(f"  Error {resp.status_code}: {resp.text[:100]}")
                if limit > 500:
                    print("  Reducing limit to 500 and retrying...")
                    limit = 500
                    continue
                break
            
            data = resp.json()
            results = data.get("results", [])
            total = data.get("total_result_count", data.get("total", 0))
            
            if not results:
                break
                
            all_results.extend(results)
            if total > 0:
                print(f"  Progress: {len(all_results)} / {total}")
            else:
                print(f"  Fetched: {len(all_results)}")

            if total > 0 and len(all_results) >= total:
                break
            if len(results) < limit:
                break
            
            offset += limit
            
        except Exception as e:
            print(f"  Failed: {e}")
            break
            
    return all_results

def run():
    consolidated = {"total": 0, "results": []}
    
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            try:
                consolidated = json.load(f)
                print(f"Loaded {len(consolidated.get('results', []))} existing records.")
            except:
                pass

    existing_years = set()
    for row in consolidated.get("results", []):
        try:
            val = row.get("deposit_year")
            if val: existing_years.add(int(val))
        except: pass

    for y in range(1990, 2026):
        if y in existing_years and y >= 2021:
            print(f"Skipping year {y} to preserve existing cache and save time.")
            continue
            
        results = fetch_year(y)
        consolidated["results"].extend(results)
        
        # Incremental save
        consolidated["total"] = len(consolidated["results"])
        
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(consolidated, f, ensure_ascii=False)
        print(f"Updated cache with year {y}. Total records: {consolidated['total']}")

if __name__ == "__main__":
    run()

