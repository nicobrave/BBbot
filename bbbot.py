import os
import json
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Optional

# --- Configuración ---
load_dotenv()

# Credenciales
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_PASS = os.getenv("SMTP_PASS")
OPENAI_KEY = os.getenv("OPENAI_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Clients
client = OpenAI(api_key=OPENAI_KEY)

# Archivos
STATE_FILE = "state.json"
PERPLEXITY_SAVE_FILE = "perplexity_response.json"
ENRICHED_DATA_FILE = "enriched_products.json"

# --- Utilidades ---
def log(msg: str, level: str = "info"):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}")

def load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        log(f"Error loading state: {str(e)}", "error")
    return {"history": [], "last_run": None}

def save_state(state: dict):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        log(f"Error saving state: {str(e)}", "error")

def normalize(text: str) -> str:
    return text.lower().strip()

def is_duplicate(url: str, state: dict) -> bool:
    return normalize(url) in [normalize(u) for u in state["history"]]

# --- Agente 1: Buscador de Productos ---
def find_product_urls() -> List[str]:
    """Busca productos de skincare innovadores usando Sonar Deep Research"""
    if not PERPLEXITY_API_KEY:
        log("Error: API key no configurada", "error")
        return []
        
    # Verificar si es lunes
    today = datetime.now().weekday()
    if today != 0:  # 0 es lunes
        log("No es lunes, usando datos existentes", "info")
        try:
            with open(PERPLEXITY_SAVE_FILE, 'r') as f:
                products = json.load(f)
                log(f"Usando {len(products)} productos existentes")
                return [p['url'] for p in products]
        except Exception as e:
            log(f"Error cargando datos existentes: {str(e)}", "error")
            return []
        
    query = """
    Proporciona información en formato JSON sobre 5 productos de skincare innovadores de 2024-2025,
    con esta estructura exacta:
    {
      "productos": [
        {
          "nombre": "Nombre del producto",
          "marca": "Marca",
          "descripcion": "Descripción técnica detallada",
          "ingredientes": ["Lista de ingredientes clave"],
          "tecnologia": "Tecnología o innovación principal",
          "beneficios": ["Lista de beneficios principales"],
          "precio": "Precio aproximado",
          "url": "Enlace oficial al producto",
          "tipo_piel": "Tipo de piel recomendado",
          "fecha_lanzamiento": "2024-2025",
          "estudios_clinicos": "Información sobre estudios clínicos si aplica",
          "sostenibilidad": "Información sobre sostenibilidad"
        }
      ]
    }
    """
    
    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
            json={
                "model": "sonar-deep-research",
                "messages": [{"role": "user", "content": query}],
                "temperature": 0.3,
                "max_tokens": 4000
            },
            timeout=900
        )
        
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content']
            
            # Extraer JSON de la respuesta
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                log("No se encontró formato JSON válido", "error")
                return []
                
            products_data = json.loads(content[json_start:json_end])
            products = products_data.get('productos', [])
            
            # Guardar la respuesta completa
            with open(PERPLEXITY_SAVE_FILE, 'w') as f:
                json.dump(products, f, indent=4)
                
            log(f"Encontrados {len(products)} productos innovadores")
            return [p['url'] for p in products]
            
        log(f"Error API: {response.status_code}", "error")
        return []
        
    except Exception as e:
        log(f"Error en investigación: {str(e)}", "error")
        return []

# --- Versión de Prueba ---
if __name__ == "__main__":
    print("=== Prueba de Búsqueda ===")
    urls = find_product_urls()
    
    if urls:
        print("\nURLs encontradas:")
        for url in urls:
            print(f"- {url}")
    else:
        print("No se encontraron URLs válidas")

# --- Agente de Generación de Contenido ---
def generate_newsletter(product_data: Dict) -> str:
    """Genera contenido premium para el newsletter de un producto"""
    if not OPENAI_KEY:
        log("Error: API key no configurada", "error")
        raise ValueError("API key no configurada")
        
    prompt = f"""
    Eres un experto en belleza con 15 años de experiencia en análisis de productos premium.
    Crea un análisis detallado y exclusivo sobre este producto de skincare, SOLO usando HTML puro (no uses Markdown, ni #, ni **, ni *). Usa etiquetas <h1>, <h2>, <ul>, <li>, <p> y <br> para el formato. Asegúrate de que los títulos sean claros, grandes y coloridos, y que haya buen espaciado entre secciones. No uses ningún símbolo de Markdown.

    Producto: {product_data['nombre']}
    Marca: {product_data['marca']}
    Precio: {product_data['precio']}
    Tecnología: {product_data['tecnologia']}
    Descripción: {product_data['descripcion']}
    Ingredientes Clave: {', '.join(product_data['ingredientes'])}
    Beneficios: {', '.join(product_data['beneficios'])}
    Tipo de Piel: {product_data['tipo_piel']}
    Estudios Clínicos: {product_data['estudios_clinicos']}
    Sostenibilidad: {product_data['sostenibilidad']}

    Estructura del análisis:
    <h1>Título Impactante (debe incluir "BB Beauty Bot" y ser de 8 palabras)</h1>
    <h2>Introducción</h2>
    <p>Contexto del mercado y posición del producto</p>
    <h2>Análisis Técnico Profundo</h2>
    <ul>
        <li>Desglose de ingredientes clave</li>
        <li>Comparación con tecnologías similares</li>
        <li>Efectividad científica</li>
    </ul>
    <h2>Beneficios Exclusivos</h2>
    <ul>
        <li>Resultados esperados</li>
        <li>Diferenciadores únicos</li>
        <li>Casos de uso específicos</li>
    </ul>
    <h2>Guía de Uso Premium</h2>
    <ul>
        <li>Protocolo de aplicación</li>
        <li>Combinaciones sinérgicas</li>
        <li>Consejos de expertos</li>
    </ul>
    <h2>Valoración Experta</h2>
    <ul>
        <li>Puntos fuertes</li>
        <li>Áreas de mejora</li>
        <li>Comparativa con competidores</li>
    </ul>
    <h2>Conclusión y Recomendación</h2>
    <p>Recomendación final y cierre</p>

    Estilo:
    - Profesional, creativo y visualmente atractivo
    - Títulos y subtítulos destacados con <h1> y <h2>
    - Listas con <ul> y <li> y emojis si es relevante
    - Usa <p> para párrafos y <br> para separar bloques de texto
    - No uses #, *, ni ningún símbolo de Markdown
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Eres un experto en belleza con acceso a investigaciones científicas y conocimiento del mercado premium."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log(f"Error generando contenido: {str(e)}", "error")
        raise

# --- Agente de Email ---
def send_email(subject: str, body_text: str, product_url: str):
    """Envía el newsletter premium por email"""
    if not all([EMAIL_SENDER, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT, SMTP_PASS]):
        log("Error: Credenciales incompletas", "error")
        raise ValueError("Credenciales incompletas")
        
    recipients = [email.strip() for email in EMAIL_RECEIVER.split(",")]
    
    msg = MIMEMultipart('alternative')
    msg['From'] = formataddr(("BB Beauty Bot Premium", EMAIL_SENDER))
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    msg['X-Priority'] = '1'
    
    # Versión texto
    msg.attach(MIMEText(body_text, 'plain'))
    
    # Versión HTML Premium con estilos mejorados
    html_content = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 700px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background: linear-gradient(135deg, #ff69b4, #d63384);
                padding: 40px 20px;
                text-align: center;
                color: white;
                border-radius: 10px 10px 0 0;
            }}
            .content {{
                background: white;
                padding: 30px;
                border: 1px solid #eee;
                border-radius: 0 0 10px 10px;
            }}
            h1 {{
                color: #ff69b4;
                font-size: 28px;
                margin-bottom: 20px;
                text-align: center;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.2);
            }}
            h2 {{
                color: #ff69b4;
                font-size: 22px;
                margin-top: 30px;
                margin-bottom: 15px;
                border-bottom: 2px solid #ff69b4;
                padding-bottom: 5px;
            }}
            ul {{
                list-style-type: none;
                padding-left: 20px;
            }}
            li {{
                margin-bottom: 10px;
                position: relative;
                padding-left: 25px;
            }}
            li:before {{
                content: "✨";
                position: absolute;
                left: 0;
            }}
            .cta-button {{
                display: inline-block;
                background: #d63384;
                color: white;
                padding: 15px 30px;
                text-decoration: none;
                border-radius: 5px;
                margin: 20px 0;
                font-weight: bold;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                color: #666;
                font-size: 12px;
            }}
            .premium-badge {{
                background: gold;
                color: #333;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
                margin-left: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>BB Beauty Bot <span class="premium-badge">PREMIUM</span></h1>
        </div>
        <div class="content">
            {body_text}
            <div style="text-align: center;">
                <a href="{product_url}" class="cta-button">Ver Producto Exclusivo</a>
            </div>
        </div>
        <div class="footer">
            <p>BB Beauty Bot Premium · Análisis Exclusivo · {datetime.now().strftime('%d/%m/%Y')}</p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_content, 'html'))
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(EMAIL_SENDER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())
        log("Email premium enviado")
    except Exception as e:
        log(f"Error enviando email: {str(e)}", "error")
        raise

def test_with_saved_data() -> List[str]:
    """Prueba el sistema usando datos guardados previamente"""
    try:
        with open(PERPLEXITY_SAVE_FILE, 'r') as f:
            products = json.load(f)
            log(f"Usando {len(products)} productos guardados")
            return [p['url'] for p in products]
    except Exception as e:
        log(f"Error cargando datos guardados: {str(e)}", "error")
        return []

# --- Flujo Principal ---
def main(test_mode: bool = False):
    log("🚀 Iniciando BB Beauty Bot - Sistema Completo")
    state = load_state()
    
    try:
        # Verificar si es fin de semana
        today = datetime.now().weekday()
        if today >= 5:  # 5 es sábado, 6 es domingo
            log("Es fin de semana, no se envía newsletter", "info")
            return
            
        # Paso 1: Obtener productos (búsqueda o existentes)
        product_urls = find_product_urls()
        if not product_urls:
            log("No se encontraron URLs válidas", "warning")
            return
            
        # Paso 2: Seleccionar producto del día
        try:
            with open(PERPLEXITY_SAVE_FILE, 'r') as f:
                products = json.load(f)
                if today >= len(products):
                    log("No hay suficientes productos para el día", "warning")
                    return
                product = products[today]  # lunes=0, martes=1, etc.
                log(f"Seleccionado producto para {['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'][today]}: {product['nombre']}")
        except Exception as e:
            log(f"Error cargando producto del día: {str(e)}", "error")
            return
        
        # Paso 3: Generar newsletter para el producto del día
        try:
            newsletter_content = generate_newsletter(product)
            
            # Crear asunto
            subject = f"✨ BB Beauty Bot | Producto del Día: {product['marca']} {product['nombre']}"
            
            # Enviar email
            send_email(
                subject=subject,
                body_text=newsletter_content,
                product_url=product['url']
            )
            
            log(f"✅ Newsletter enviado para: {product['nombre']}")
            
        except Exception as e:
            log(f"Error generando o enviando newsletter: {str(e)}", "error")
            raise
        
    except Exception as e:
        log(f"💣 Error crítico: {str(e)}", "critical")

def generate_executive_summary(products: List[Dict]) -> str:
    """Genera un resumen ejecutivo integrado de todos los productos"""
    if not OPENAI_KEY:
        log("Error: API key no configurada", "error")
        raise ValueError("API key no configurada")
        
    products_info = "<br><br>".join([
        f"""
        <b>Producto:</b> {p['nombre']}<br>
        <b>Marca:</b> {p['marca']}<br>
        <b>Precio:</b> {p['precio']}<br>
        <b>Tecnología:</b> {p['tecnologia']}<br>
        <b>Descripción:</b> {p['descripcion']}<br>
        <b>Ingredientes Clave:</b> {', '.join(p['ingredientes'])}<br>
        <b>Beneficios:</b> {', '.join(p['beneficios'])}<br>
        <b>Tipo de Piel:</b> {p['tipo_piel']}<br>
        <b>Estudios Clínicos:</b> {p['estudios_clinicos']}<br>
        <b>Sostenibilidad:</b> {p['sostenibilidad']}<br>
        """
        for p in products
    ])
    
    prompt = f"""
    Eres un experto en belleza con 15 años de experiencia en análisis de productos premium.
    Crea un análisis integrado y exclusivo sobre estos productos de skincare, SOLO usando HTML puro (no uses Markdown, ni #, ni **, ni *). Usa etiquetas <h1>, <h2>, <ul>, <li>, <p> y <br> para el formato. Asegúrate de que los títulos sean claros, grandes y coloridos, y que haya buen espaciado entre secciones. No uses ningún símbolo de Markdown.

    {products_info}

    Estructura del análisis en formato HTML elegante:
    <h1>Título Impactante (debe incluir "BB Beauty Bot" y ser de 8 palabras)</h1>
    <h2>Introducción</h2>
    <p>Tendencias del mercado y contexto de los productos</p>
    <h2>Análisis Técnico Comparativo</h2>
    <ul>
        <li>Innovaciones tecnológicas destacadas</li>
        <li>Ingredientes revolucionarios</li>
        <li>Efectividad científica</li>
    </ul>
    <h2>Beneficios Integrados</h2>
    <ul>
        <li>Resultados esperados por tipo de piel</li>
        <li>Diferenciadores únicos de cada producto</li>
        <li>Casos de uso específicos</li>
    </ul>
    <h2>Guía de Uso Premium</h2>
    <ul>
        <li>Protocolos de aplicación</li>
        <li>Combinaciones sinérgicas entre productos</li>
        <li>Consejos de expertos</li>
    </ul>
    <h2>Valoración Experta</h2>
    <ul>
        <li>Puntos fuertes de cada producto</li>
        <li>Áreas de mejora</li>
        <li>Comparativa entre productos</li>
    </ul>
    <h2>Conclusión y Recomendaciones</h2>
    <p>Recomendaciones personalizadas y conclusiones finales</p>

    Estilo:
    - Profesional, creativo y visualmente atractivo
    - Títulos y subtítulos destacados con <h1> y <h2>
    - Listas con <ul> y <li> y emojis si es relevante
    - Usa <p> para párrafos y <br> para separar bloques de texto
    - No uses #, *, ni ningún símbolo de Markdown
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Eres un experto en belleza con acceso a investigaciones científicas y conocimiento del mercado premium."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log(f"Error generando resumen ejecutivo: {str(e)}", "error")
        raise

if __name__ == "__main__":
    # Para pruebas, usar test_mode=True
    main(test_mode=True)