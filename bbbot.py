import os
import json
import smtplib
import requests
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from openai import OpenAI
from dotenv import load_dotenv

# --- Configuración
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_PASS = os.getenv("SMTP_PASS")
OPENAI_KEY = os.getenv("OPENAI_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
client = OpenAI(api_key=OPENAI_KEY)
STATE_FILE = "state.json"

# --- Utilidades
def log(msg): print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
def load_state(): return json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {"history": []}
def save_state(state): json.dump(state, open(STATE_FILE, "w"), indent=4)
def normalize(text): return text.lower().strip()
def is_duplicate(title, state): return normalize(title) in [normalize(p) for p in state["history"]]

def extract_query(text):
    lines = text.strip().splitlines()
    for line in lines:
        if "site:" in line:
            return line.strip()
    return lines[-1].strip()

# --- Agente 1: Brave Search
def search_agent():
    prompt = (
        "Redacta una consulta clara y corta para Brave Search que busque productos de skincare naturales y cruelty-free, nuevos o en tendencia en 2025. "
        "Debe limitarse a los siguientes sitios: sephora.com, byrdie.com, allure.com, sokoglam.com, ultabeauty.com, cultbeauty.com."
        " Devuelve solo la línea con la consulta web usando 'site:' sin explicaciones."
    )
    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[{"role": "system", "content": "Eres un generador experto de queries web para Brave Search."},
                  {"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=150
    )
    query = extract_query(response.choices[0].message.content)
    log(f"🔍 Consulta limpia: {query}")

    headers = {"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY}
    params = {"q": query, "count": 10, "safesearch": "moderate", "freshness": "day"}
    r = requests.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("web", {}).get("results", [])

# --- Agente 2: Middleware
def middleware_select_best_product(results, state):
    if not results:
        return None
    bloques = []
    for r in results:
        title = r.get("title", "")
        desc = r.get("description", "")
        url = r.get("url", "")
        if not title or not desc or is_duplicate(title, state):
            continue
        bloques.append(f"TÍTULO: {title}\nDESCRIPCIÓN: {desc}\nURL: {url}")
    if not bloques:
        return None
    prompt = (
        "De los siguientes artículos, elige solo uno que mencione un producto individual."
        " Si todos son listados, selecciona uno y extrae el producto más destacado."
        " Devuelve un JSON con: { 'title': ..., 'description': ..., 'url': ..., 'brand': ..., 'type': 'todo tipo de piel' }\n\n"
        "ARTÍCULOS:\n" + "\n---\n".join(bloques)
    )
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "Middleware para selección de producto en BB Bot"},
                  {"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=800
    )
    try:
        return json.loads(response.choices[0].message.content.strip())
    except json.JSONDecodeError:
        log("⚠️ Error al parsear JSON del middleware.")
        return None

# --- Agente 2.5: Context Enricher
def context_enricher_agent(product):
    query = f"\"{product['title']}\" site:sephora.com OR site:byrdie.com OR site:allure.com OR site:sokoglam.com OR site:ultabeauty.com OR site:cultbeauty.com"
    headers = {"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY}
    params = {"q": query, "count": 5, "safesearch": "moderate"}
    r = requests.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
    r.raise_for_status()
    results = r.json().get("web", {}).get("results", [])
    context = "\n\n".join([f"{r['title']}\n{r['description']}" for r in results if r.get("title") and r.get("description")])
    product['context'] = context
    return product

# --- Agente 3: Redactor
def writer_agent(product_info):
    prompt = (
        "Eres BB Bot, un redactor experto en skincare. Redacta un newsletter diario en TEXTO PLANO, con estilo profesional, emocional y claro. No uses encabezados visibles como 'INTRO EMOCIONAL' o 'PRODUCTO DESTACADO'. El contenido debe fluir naturalmente, respetando esta estructura interna:\n\n"
        "1. Una introducción emocional que conecte con una preocupación común sobre la piel.\n"
        "2. Una recomendación de producto individual o listado destacado, mencionando marca, fuente de autoridad (como Byrdie, Allure, Sephora, etc.), beneficios clave y tipo de piel sugerido.\n"
        "3. Un bloque paso a paso con instrucciones claras para usarlo.\n"
        "4. Tres tips con emojis.\n"
        "5. Una minihistoria de transformación o testimonio que inspire confianza.\n"
        "6. Un cierre con el mensaje: 'Somos BB Bot, tu newsletter inteligente impulsado por IA. ¡Tu piel, nuestra pasión!'\n\n"
        f"Este es el producto para trabajar:\n{json.dumps(product_info, indent=2)}"
    )
    r = client.chat.completions.create(
        model="gpt-4o-2024-05-13",
        messages=[{"role": "system", "content": "Redactor TLDR de BB Bot"}, {"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1000
    )
    return r.choices[0].message.content.strip()

# --- Agente 4: Email
def email_agent(subject, body):
    recipients = [email.strip() for email in EMAIL_RECEIVER.split(",")]
    body += "\n\n📩 Consejo BB Bot: Agréganos a tus contactos para no perder ninguna edición."
    msg = MIMEMultipart()
    msg["From"] = formataddr(("Skincare Bot", EMAIL_SENDER))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_SENDER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())
            log("📬 Correo enviado a: " + ", ".join(recipients))
    except Exception as ex:
        log(f"❌ Error al enviar correo: {ex}")

# --- Main
def main():
    log("🤖 BB Bot - Agentic TLDR")
    state = load_state()
    raw_results = search_agent()
    triaged_data = middleware_select_best_product(raw_results, state)
    if not triaged_data:
        log("❌ No se encontró contenido nuevo relevante.")
        return

    enriched = context_enricher_agent(triaged_data)
    newsletter = writer_agent(enriched)
    state["history"].append(normalize(triaged_data["title"]))
    save_state(state)
    email_agent("✨ BB Bot - Producto natural del día", newsletter)
    log("✅ Todo enviado con éxito")

if __name__ == "__main__":
    main()
