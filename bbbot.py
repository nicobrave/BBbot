import os
import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List, Dict, Optional
import gspread
from google.oauth2.service_account import Credentials

# --- Configuración ---
load_dotenv()

# API Keys y Credenciales
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
# EMAIL_RECEIVER se obtiene ahora de Google Sheets
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_PASS = os.getenv("SMTP_PASS")

# Configurar el cliente de Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Archivos y Configuración de Google Sheets
WEEKLY_PRODUCTS_FILE = "weekly_products.json"
GOOGLE_SHEET_NAME = "Suscriptores BB Beauty Bot"
CREDENTIALS_FILE = "credentials.json"

# --- Utilidades ---
def log(msg: str, level: str = "info"):
    """Función de logging simple que imprime en consola."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level.upper()}] {msg}")

# --- Lector de Google Sheets ---
def get_subscribers_from_sheet() -> List[str]:
    """
    Se conecta a Google Sheets y obtiene la lista de correos de los suscriptores.
    Retorna una lista de strings con los correos.
    """
    log("Accediendo a Google Sheets para obtener suscriptores...", "info")
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.sheet1 # Accede a la primera hoja
        
        # Asume que los correos están en la columna 2 (B). Omite la primera fila (encabezado).
        emails = worksheet.col_values(2)[1:]
        
        valid_emails = [email for email in emails if '@' in email]
        log(f"Se encontraron {len(valid_emails)} correos válidos en la hoja de cálculo.", "info")
        return valid_emails
    except FileNotFoundError:
        log(f"Error: El archivo de credenciales '{CREDENTIALS_FILE}' no fue encontrado.", "error")
        return []
    except Exception as e:
        log(f"Error al conectar con Google Sheets: {e}", "error")
        return []

# --- Agente de Búsqueda con Gemini ---
def find_products_with_gemini() -> bool:
    """
    Usa Gemini para encontrar 5 productos de skincare innovadores y los guarda en un archivo JSON.
    Retorna True si la operación fue exitosa, False en caso contrario.
    """
    if not GEMINI_API_KEY:
        log("GEMINI_API_KEY no está configurada. No se puede realizar la búsqueda.", "error")
        return False

    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = """
    Eres un experto en investigación de mercado de skincare de lujo.
    Realiza una investigación profunda y encuentra los 5 productos de skincare más innovadores y prometedores del último año (2024-2025).
    Prioriza productos con ingredientes patentados, tecnología novedosa o resultados clínicos demostrables.

    Para cada producto, proporciona la información en un objeto JSON con esta estructura exacta:
    {
      "nombre": "string",
      "marca": "string",
      "descripcion": "string (descripción técnica detallada de 100-150 palabras)",
      "ingredientes": ["string", "string", "string"],
      "tecnologia": "string (innovación principal)",
      "beneficios": ["string", "string", "string"],
      "precio": "string (ej. USD 80-95)",
      "url": "string (URL oficial del producto)",
      "tipo_piel": "string",
      "estudios_clinicos": "string (resumen breve si aplica)",
      "sostenibilidad": "string (detalles sobre empaque o ingredientes si aplica)"
    }
    Devuelve SÓLO un array JSON que contenga 5 de estos objetos. No incluyas "```json" ni nada más que el array.
    """
    
    log("Iniciando búsqueda de productos con Gemini...", "info")
    try:
        response = model.generate_content(prompt)
        # Limpiar la respuesta para asegurar que sea un JSON válido
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        products = json.loads(cleaned_response)

        if isinstance(products, list) and len(products) > 0:
            with open(WEEKLY_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(products, f, indent=4, ensure_ascii=False)
            log(f"Búsqueda exitosa. Se guardaron {len(products)} productos.", "info")
            return True
        else:
            log("La respuesta de Gemini no contenía una lista de productos válida.", "error")
            return False

    except Exception as e:
        log(f"Error durante la búsqueda con Gemini: {e}", "error")
        return False

# --- Agente de Contenido con Gemini ---
def generate_newsletter_with_gemini(product: Dict) -> str:
    """Genera el contenido del newsletter con un enfoque educativo y accesible."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no está configurada.")

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Construcción dinámica de la lista de ingredientes para el prompt
    ingredients_list_html = ""
    for ing in product.get('ingredientes', []):
        ingredients_list_html += f"<li><b>{ing}:</b> [Explica de forma sencilla y directa qué hace este ingrediente por la piel. Evita la jerga técnica.]</li>"

    prompt = f"""
    Eres un divulgador experto en cuidado de la piel. Tu misión es educar de forma clara, sencilla y confiable.
    No uses lenguaje publicitario ni demasiado técnico. El tono debe ser como el de un amigo experto que da buenos consejos.
    Crea un análisis del siguiente producto usando únicamente etiquetas HTML para el formato. No uses Markdown (#, *, etc.).

    **Producto a analizar:**
    - Nombre: {product.get('nombre', 'N/A')}
    - Marca: {product.get('marca', 'N/A')}

    **Estructura HTML requerida:**
    <h1>{product.get('marca', 'Marca')} - {product.get('nombre', 'Nombre del Producto')}</h1>
    
    <h2>💡 ¿Qué es y qué lo hace especial?</h2>
    <p>{product.get('descripcion', 'Descripción no disponible.')}</p>
    
    <hr style="border: 1px solid #f0eafc; margin: 30px 0;">

    <h2>🔬 Análisis de Ingredientes y Beneficios</h2>
    <p>Estos son los ingredientes clave y lo que realmente hacen por tu piel:</p>
    <ul>
        {ingredients_list_html}
    </ul>

    <hr style="border: 1px solid #f0eafc; margin: 30px 0;">

    <h2>⚠️ Consejos de Uso: Cómo y Cuándo</h2>
    <p>Para sacarle el máximo provecho y mantener tu piel segura, sigue estos consejos:</p>
    <ul>
        <li><b>Combinaciones recomendadas (Sinergia):</b> [Menciona con qué tipo de productos o ingredientes funciona bien. Ej: "Úsalo junto a un limpiador suave para mejores resultados"].</li>
        <li><b>Combinaciones a evitar (Antagonismo):</b> [Menciona qué no mezclar para evitar irritación. Ej: "Evita usarlo al mismo tiempo que exfoliantes fuertes como el ácido glicólico"].</li>
        <li><b>Momento ideal de aplicación:</b> [Mañana, noche, o ambos].</li>
    </ul>

    <hr style="border: 1px solid #f0eafc; margin: 30px 0;">

    <h2>✅ Resumen Clave y Tip Experto</h2>
    <p><b>En pocas palabras:</b> [Resume el producto en una frase: para quién es ideal y cuál es su mayor fortaleza.]</p>
    <p><b>Tip Experto:</b> [Ofrece un dato práctico o poco conocido sobre el producto o su uso que no se haya mencionado antes.]</p>
    """
    
    log(f"Generando newsletter para '{product.get('nombre')}'...", "info")
    try:
        response = model.generate_content(prompt)
        # Limpieza final para eliminar cualquier bloque de código Markdown
        cleaned_html = response.text.strip()
        if cleaned_html.startswith("```html"):
            cleaned_html = cleaned_html[7:]
        if cleaned_html.endswith("```"):
            cleaned_html = cleaned_html[:-3]
        
        return cleaned_html.strip()
    except Exception as e:
        log(f"Error generando contenido con Gemini: {e}", "error")
        raise

# --- Agente de Email ---
def send_email(subject: str, body_html: str, product_url: str, recipients: List[str]):
    """Envía el newsletter con un diseño visualmente mágico a una lista de destinatarios."""
    if not all([EMAIL_SENDER, SMTP_SERVER, SMTP_PORT, SMTP_PASS]):
        log("Credenciales de email incompletas. No se puede enviar.", "error")
        raise ValueError("Credenciales de email incompletas.")

    if not recipients:
        log("No hay destinatarios a los que enviar el correo.", "warning")
        return

    # Paleta de colores "mágica"
    color_bg = "#f0eafc" # Lavanda pálido
    color_header_bg = "#3c1053" # Morado oscuro
    color_header_text = "#ffffff" # Blanco
    color_title = "#6a1b9a" # Morado
    color_subtitle = "#8e24aa" # Púrpura
    color_text = "#4a4a4a" # Gris oscuro
    color_accent = "#d1c4e9" # Lavanda más oscuro

    html_content = f"""
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Roboto', sans-serif; margin: 0; padding: 0; background-color: {color_bg}; }}
            .container {{ max-width: 680px; margin: 0 auto; background-color: #ffffff; }}
            .header {{ background-color: {color_header_bg}; color: {color_header_text}; padding: 30px 20px; text-align: center; }}
            .header h1 {{ font-family: 'Playfair Display', serif; font-size: 32px; margin: 0; }}
            .content {{ padding: 30px; color: {color_text}; }}
            .content h1 {{ font-family: 'Playfair Display', serif; color: {color_title}; font-size: 28px; }}
            .content h2 {{ font-family: 'Playfair Display', serif; color: {color_subtitle}; font-size: 22px; border-bottom: 2px solid {color_accent}; padding-bottom: 5px; margin-top: 30px; }}
            .content p {{ line-height: 1.7; }}
            .content ul {{ list-style: none; padding-left: 0; }}
            .content li {{ padding-left: 20px; position: relative; margin-bottom: 10px; }}
            .content li:before {{ content: '✦'; color: {color_subtitle}; position: absolute; left: 0; font-size: 14px; }}
            .cta-button {{ display: inline-block; background-color: {color_title}; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; text-align: center; }}
            .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #999; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>BB Beauty Bot</h1>
            </div>
            <div class="content">
                {body_html}
                <div style="text-align: center;">
                    <a href="{product_url}" class="cta-button">Descubrir el Secreto</a>
                </div>
            </div>
            <div class="footer">
                <p>Análisis exclusivo de BB Beauty Bot · {datetime.now().strftime('%Y')}</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    log(f"Preparando para enviar correo a {len(recipients)} destinatarios.", "info")
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(EMAIL_SENDER, SMTP_PASS)
            
            for recipient in recipients:
                msg = MIMEMultipart('alternative')
                msg['From'] = formataddr(("BB Beauty Bot ✨", EMAIL_SENDER))
                msg['To'] = recipient
                msg['Subject'] = subject
                msg.attach(MIMEText(html_content, 'html'))
                server.sendmail(EMAIL_SENDER, [recipient], msg.as_string())
                log(f"Correo enviado a {recipient}", "info")
                
        log(f"💌 Proceso de envío de correos completado.", "info")
    except Exception as e:
        log(f"Error enviando email: {e}", "error")
        raise

# --- Flujo Principal ---
def main():
    log("🚀 Iniciando BB Beauty Bot 2.0 (Gemini Edition)", "info")
    
    # Paso 1: Obtener la lista de suscriptores
    subscribers = get_subscribers_from_sheet()
    if not subscribers:
        log("No hay suscriptores para enviar el correo. Finalizando proceso.", "warning")
        return

    today = datetime.now().weekday()  # Lunes=0, Domingo=6

    is_weekend = today >= 5
    if is_weekend:
        log("Es fin de semana. No se envía newsletter.", "info")
        return

    # Paso 2: Búsqueda semanal si es lunes
    if today == 0: 
        log("Día de búsqueda. Iniciando la caza de productos innovadores...", "info")
        if not find_products_with_gemini():
            log("La búsqueda semanal falló. Reintentando en la próxima ejecución.", "error")
            return
    
    # Paso 3: Verificar si los productos de la semana existen
    if not os.path.exists(WEEKLY_PRODUCTS_FILE):
        log("El archivo de productos no existe. Esperando a la próxima búsqueda.", "warning")
        return

    # Paso 4: Seleccionar producto del día y enviar
    try:
        with open(WEEKLY_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            products = json.load(f)
        
        day_index = today
        if day_index >= len(products):
            log(f"No hay producto asignado para hoy (Día {day_index+1}).", "warning")
            return
            
        product_of_the_day = products[day_index]
        day_name = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"][day_index]
        log(f"Producto para el {day_name}: {product_of_the_day.get('nombre')}", "info")

        # Generar y enviar el newsletter
        newsletter_html = generate_newsletter_with_gemini(product_of_the_day)
        subject = f"Tu Dosis de Magia Skincare del {day_name} ✨"
        send_email(subject, newsletter_html, product_of_the_day.get('url', '#'), subscribers)
        
        log("✅ Proceso diario completado exitosamente.", "info")

    except FileNotFoundError:
        log(f"Archivo de productos no encontrado. Ejecuta la búsqueda de lunes primero.", "error")
    except Exception as e:
        log(f"💣 Error crítico en el flujo principal: {e}", "critical")

if __name__ == "__main__":
    main()