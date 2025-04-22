# bbbot.py
import os
import json
import smtplib
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote_plus
from dotenv import load_dotenv
from openai import OpenAI
from email.utils import formataddr
import certifi

# .env vars
load_dotenv()
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
except ValueError:
    raise ValueError("⚠️ El secret SMTP_PORT está mal configurado o vacío. Debe ser un número.")

SMTP_PASS = os.getenv("SMTP_PASS")
OPENAI_KEY = os.getenv("OPENAI_KEY")
client = OpenAI(api_key=OPENAI_KEY)
STATE_FILE = "state.json"
KEYWORDS = ["natural", "cruelty-free", "serum", "acne", "spf", "cleanser", "toner", "hydrating", "retinol"]
EXCLUDED_KEYWORDS = ["revista", "editorial", "celebridad", "evento", "caras", "glamour"]

# Utils
def log(msg): print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
def load_state(): return json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {"history": []}
def save_state(state): json.dump(state, open(STATE_FILE, "w"), indent=4)
def is_duplicate(product, state): return product.lower() in (p.lower() for p in state["history"])
def is_valid_entry(title): 
    title = title.lower()
    return any(k in title for k in KEYWORDS) and not any(x in title for x in EXCLUDED_KEYWORDS)

# Google News
def scrape_google_news_rss():
    log("🟢 Google News")
    url = f"https://news.google.com/rss/search?q={quote_plus('skincare OR cruelty-free OR serum')}&hl=en&gl=US&ceid=US:en"
    entries = feedparser.parse(url).entries
    return [{
        "source": "Google News", "product": e.title.strip(), "brand": "Fuente de noticias",
        "url": e.link, "type": "todo tipo de piel"
    } for e in entries if is_valid_entry(e.title.strip())]

# Sephora Best Sellers
def scrape_sephora_best_sellers():
    log("🟣 Sephora")
    try:
        url = "https://www.sephora.com/shop/best-selling-skin-care"
        soup = BeautifulSoup(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=certifi.where()).text, "html.parser")
        items = soup.find_all("div", class_="css-1w8vjjz")
        return [{
            "source": "Sephora", "product": p.find("span", class_="css-0").text.strip(),
            "brand": "Sephora", "url": url, "type": "todo tipo de piel"
        } for p in items[:10] if p.find("span", class_="css-0") and is_valid_entry(p.find("span", class_="css-0").text.strip())]
    except Exception as e:
        log(f"Error en Sephora: {e}")
        return []

# Allure
def scrape_allure():
    log("💄 Allure")
    try:
        url = "https://www.allure.com/topic/skin-care"
        soup = BeautifulSoup(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text, "html.parser")
        return [{
            "source": "Allure", "product": a.text.strip(),
            "brand": "Allure", "url": "https://www.allure.com" + a['href'], "type": "todo tipo de piel"
        } for a in soup.find_all("a", class_="link-for-card")[:10] if is_valid_entry(a.text.strip())]
    except Exception as e:
        log(f"Error en Allure: {e}")
        return []

# Byrdie
def scrape_byrdie():
    log("🌿 Byrdie")
    try:
        url = "https://www.byrdie.com/skin-care-4691945"
        soup = BeautifulSoup(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text, "html.parser")
        return [{
            "source": "Byrdie", "product": a.get("title", "").strip(),
            "brand": "Byrdie", "url": a.get("href", "#"), "type": "todo tipo de piel"
        } for a in soup.select("a.comp.mntl-card-list-items.mntl-document-card")[:10] if is_valid_entry(a.get("title", ""))]
    except Exception as e:
        log(f"Error en Byrdie: {e}")
        return []

# Glossy
def scrape_glossy():
    log("📰 Glossy")
    try:
        url = "https://www.glossy.co/beauty/"
        soup = BeautifulSoup(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text, "html.parser")
        return [{
            "source": "Glossy", "product": a.text.strip(),
            "brand": "Glossy", "url": a.get("href", "#"), "type": "todo tipo de piel"
        } for a in soup.select("article a")[:10] if is_valid_entry(a.text.strip()) and a.get("href", "").startswith("https")]
    except Exception as e:
        log(f"Error en Glossy: {e}")
        return []

# Generador de texto
def generate_newsletter(p):
    prompt = (
    f"Eres BB Bot, un asistente experto en skincare. Redacta un mensaje en texto plano para un newsletter diario.\n\n"
    f"Formato:\n"
    f"👋 Saludo inicial cálido\n"
    f"🧴 Presenta el producto '{p['product']}' de la marca '{p['brand']}'\n"
    f"💡 Menciona para qué tipo de piel es ideal: {p['type']}\n"
    f"📝 Explica cómo usarlo paso a paso (3-4 líneas)\n"
    f"✅ Da 3 tips útiles con emojis (1 por tip)\n"
    f"🔗 Sugiere al lector que puede conocer más en el sitio oficial de la marca, sin dar la URL\n"
    f"🎓 Cierra con un mensaje final atractivo, profesional y firme como: "
    f"'Somos BB Bot, tu newsletter inteligente impulsado por IA 🧠✨'\n\n"
    f"Estilo: empático, claro, visual, no exagerado. Máximo 1000 palabras."
)

    r = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "Redactor para BB Bot"}, {"role": "user", "content": prompt}],
        temperature=0.3, max_tokens=1500
    )
    return r.choices[0].message.content.strip()

# Email
def send_email(subject, body):
    # Agregamos una nota anti-spam al final del contenido
    body += "\n\n📩 Consejo BB Bot: Para que nuestras recomendaciones no terminen en spam, agréganos a tus contactos."

    # Convertir múltiples correos separados por coma en lista
    to_list = [email.strip() for email in EMAIL_RECEIVER.split(",")]

    msg = MIMEMultipart()
    msg["From"] = formataddr(("Skincare Bot", EMAIL_SENDER))
    msg["To"] = ", ".join(to_list)  # Para que aparezcan todos en el header
    msg["Subject"] = subject
    msg["Reply-To"] = EMAIL_SENDER
    msg["X-Priority"] = "3"
    msg["X-Mailer"] = "BB Bot IA 1.0"
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, SMTP_PASS)
        server.sendmail(EMAIL_SENDER, to_list, msg.as_string())

    log("📬 Correo enviado a: " + ", ".join(to_list))

# MAIN
def main():
    log("🚀 BB Bot inicia")
    state = load_state()
    sources = (
        scrape_google_news_rss() +
        scrape_sephora_best_sellers() +
        scrape_allure() +
        scrape_byrdie() +
        scrape_glossy()
    )
    fresh = [x for x in sources if not is_duplicate(x["product"], state)]
    log(f"🎯 {len(fresh)} productos nuevos")

    if not fresh:
        log("❌ Nada nuevo hoy.")
        return

    pick = fresh[0]
    body = generate_newsletter(pick)
    send_email("✨ Tu producto natural de skincare del día", body)

    state["history"].append(pick["product"])
    save_state(state)
    log("✅ Todo listo.")

if __name__ == "__main__":
    main()
