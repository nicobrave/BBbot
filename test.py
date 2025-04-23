import os
import requests
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
client = OpenAI(api_key=OPENAI_KEY)

def extract_query(text):
    lines = text.strip().splitlines()
    for line in lines:
        if "site:" in line or any(site in line for site in [
            "sephora.com", "byrdie.com", "allure.com", "sokoglam.com", "ultabeauty.com", "cultbeauty.com"
        ]):
            return line.strip()
    return lines[-1].strip()

def generate_query():
    prompt = (
        "Redacta solo una línea de consulta para buscador. Sin explicación. "
        "Debe buscar productos de skincare específicos, nuevos o en tendencia en 2024, naturales y cruelty-free. "
        "Limita la búsqueda a:\n"
        "site:sephora.com OR site:byrdie.com/skin-4628389 OR site:allure.com OR site:sokoglam.com OR site:ultabeauty.com OR site:cultbeauty.com"
    )
    res = client.chat.completions.create(
        model="gpt-4.1-2025-04-14",
        messages=[{"role": "system", "content": "Query generator experto."},
                  {"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=150
    )
    return extract_query(res.choices[0].message.content)

def brave_search(query):
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": 10,
        "safesearch": "moderate",
        "freshness": "day"
    }
    r = requests.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("web", {}).get("results", [])

def run():
    print("🔧 Generando query...")
    query = generate_query()
    print(f"\n✅ QUERY USADA:\n{query}")

    print("\n🔍 Consultando Brave Search...")
    results = brave_search(query)

    if not results:
        print("\n❌ No se encontraron resultados.")
        return

    print(f"\n🎯 {len(results)} resultados:")
    for r in results:
        print("—" * 40)
        print("🧴", r.get("title", "").strip())
        print(r.get("description", "").strip())
        print(r.get("url", ""))
        print()

if __name__ == "__main__":
    run()
