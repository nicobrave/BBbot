import os
import json
import logging
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

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

# --- API Keys and Email Credentials ---
# These should be set as environment variables for security and flexibility.
# For example, in a .env file loaded by python-dotenv, or in the deployment environment.

# Credenciales para el envío de correos y APIs
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_PASS = os.getenv("SMTP_PASS")
OPENAI_KEY = os.getenv("OPENAI_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Clients
client = OpenAI(api_key=OPENAI_KEY)

# Archivos de datos y estado
STATE_FILE = "state.json"  # Guarda el estado de la aplicación, como la última ejecución.
PERPLEXITY_SAVE_FILE = "perplexity_response.json"  # Almacena la respuesta de Perplexity API (lista de productos).
ENRICHED_DATA_FILE = "enriched_products.json"  # Potencialmente para datos de productos enriquecidos (actualmente no usado activamente).

# --- Utilidades ---
def load_state() -> dict:
    """
    Loads the application state from STATE_FILE.

    The state includes information like the last run time.
    If STATE_FILE does not exist or is corrupted, returns a default state:
    {"last_run": None}.
    The 'history' key, if present in an old state file, is removed.

    Returns:
        dict: The loaded application state.
    """
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                loaded_state = json.load(f)
                # Remove 'history' if it exists
                loaded_state.pop("history", None)
                return loaded_state
    except Exception as e:
        logging.error(f"Error loading state: {str(e)}")
    return {"last_run": None}

def save_state(state: dict):
    """
    Saves the given application state to STATE_FILE.

    The 'history' key is removed from the state before saving if present.

    Args:
        state (dict): The application state to save.
    """
    # Ensure 'history' is not saved
    state.pop("history", None)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving state: {str(e)}")

def normalize(text: str) -> str:
    """
    Normalizes a string by converting to lowercase and stripping whitespace.
    Useful for consistent comparisons or storage.

    Args:
        text (str): The input string.

    Returns:
        str: The normalized string.
    """
    return text.lower().strip()

# --- Agente 1: Buscador de Productos ---
def find_product_urls() -> List[str]:
    """
    Fetches innovative skincare product URLs.

    On Mondays, it queries the Perplexity API for new products, saves them
    to PERPLEXITY_SAVE_FILE (a JSON list of product dictionaries),
    and returns their URLs.
    On other weekdays, it attempts to load product data directly from
    PERPLEXITY_SAVE_FILE and returns the URLs from this cached data.

    The PERPLEXITY_SAVE_FILE is expected to contain a JSON list of objects,
    where each object represents a product and should have at least a 'url' key.

    Returns:
        List[str]: A list of product URLs, or an empty list if no products
                   are found or an error occurs.
    """
    if not PERPLEXITY_API_KEY:
        logging.error("Error: API key no configurada")
        return []
        
    # Verificar si es lunes (0 = Lunes, 1 = Martes, ..., 6 = Domingo)
    today = datetime.now().weekday()
    if today != 0:  # Si no es lunes
        logging.info("No es lunes, usando datos existentes de PERPLEXITY_SAVE_FILE.")
        # Intentar cargar productos desde el archivo guardado
        try:
            with open(PERPLEXITY_SAVE_FILE, 'r') as f:
                products = json.load(f)

            if not isinstance(products, list):
                logging.error(f"'{PERPLEXITY_SAVE_FILE}' does not contain a list")
                return []

            logging.info(f"Usando {len(products)} productos existentes")
            valid_products_urls = []
            for p in products:
                if isinstance(p, dict) and 'url' in p:
                    valid_products_urls.append(p['url'])
                else:
                    logging.warning(f"Skipping malformed product data item in '{PERPLEXITY_SAVE_FILE}': {p}")
            return valid_products_urls

        except FileNotFoundError:
            logging.error(f"Archivo de datos existentes '{PERPLEXITY_SAVE_FILE}' no encontrado.")
            return []
        except json.JSONDecodeError as e:
            logging.error(f"Error decodificando JSON de '{PERPLEXITY_SAVE_FILE}': {str(e)}")
            return []
        except Exception as e:
            logging.error(f"Error inesperado cargando datos existentes: {str(e)}")
            return []
        
    # Query para la API de Perplexity, solicitando datos en formato JSON.
    # Esta estructura de query es específica para obtener la información deseada de productos.
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
    
    # Realizar la llamada a la API de Perplexity
    try:
        response = requests.post( # NOSONAR
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
            json={
                "model": "sonar-deep-research",
                "messages": [{"role": "user", "content": query}],
                "temperature": 0.3,
                "max_tokens": 4000
            },
            timeout=900  # Timeout extendido para permitir respuestas largas de la API.
        )
        response.raise_for_status() # Generará un HTTPError para respuestas 4xx/5xx

        # Procesar la respuesta de la API
        try:
            data = response.json()
            content = data['choices'][0]['message']['content']
            
            # La API de Perplexity puede devolver JSON dentro de una cadena de texto,
            # por lo que es necesario extraer la subcadena JSON.
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                logging.error("No se encontró formato JSON válido en la respuesta de la API.")
                return []

            products_data = json.loads(content[json_start:json_end])
        except json.JSONDecodeError as e:
            logging.error(f"Error decodificando JSON de la respuesta de la API: {str(e)}")
            logging.debug(f"Contenido recibido de la API (parcial): {content[:500]}") # Loggear parte del contenido
            return []

        products = products_data.get('productos', [])
        if not isinstance(products, list):
            logging.error("API response for 'productos' is not a list")
            return []
            
        # Guardar la respuesta completa
        with open(PERPLEXITY_SAVE_FILE, 'w') as f:
            json.dump(products, f, indent=4)
            
        logging.info(f"Encontrados {len(products)} productos innovadores")
        
        valid_products_urls = []
        for p in products:
            if isinstance(p, dict) and 'url' in p:
                valid_products_urls.append(p['url'])
            else:
                logging.warning(f"Skipping malformed product data item from API response: {p}")
        return valid_products_urls

    except requests.exceptions.RequestException as e:
        logging.error(f"Error de red o HTTP durante la llamada a la API: {str(e)}")
        return []
    except Exception as e: # Captura general para otros errores inesperados (ej. KeyError en 'choices')
        logging.error(f"Error inesperado durante la investigación de productos: {str(e)}")
        return []

# --- Agente de Generación de Contenido ---
def generate_newsletter(product_data: Dict) -> str:
    """
    Generates premium HTML newsletter content for a given skincare product.

    Uses OpenAI's GPT-4 Turbo model to create a detailed analysis based on
    the provided product data.

    Args:
        product_data (Dict): A dictionary containing details of the product,
                             expected to have keys like 'nombre', 'marca',
                             'descripcion', 'ingredientes', etc.

    Returns:
        str: The generated newsletter content as an HTML string.

    Raises:
        ValueError: If the OpenAI API key is not configured.
        Exception: If there's an error during API communication or content generation.
    """
    if not OPENAI_KEY:
        logging.error("Error: API key no configurada")
        raise ValueError("API key no configurada")
        
    # Prompt detallado para OpenAI, especificando la estructura y estilo del contenido HTML.
    # Este prompt está diseñado para generar un análisis de producto de alta calidad.
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
    
    # Llamada a la API de OpenAI para generar el contenido del newsletter
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",  # Modelo de OpenAI especificado
            messages=[
                {"role": "system", "content": "Eres un experto en belleza con acceso a investigaciones científicas y conocimiento del mercado premium."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error generando contenido: {str(e)}")
        raise

# --- Agente de Email ---
def send_email(subject: str, body_text: str, product_url: str):
    """
    Sends a premium newsletter email with the given subject and body.

    The email is sent in both plain text and HTML format.
    SMTP server details and credentials are read from environment variables.

    Args:
        subject (str): The subject line of the email.
        body_text (str): The main content of the newsletter (HTML expected for rich formatting).
        product_url (str): The URL to the featured product for a CTA button.

    Raises:
        ValueError: If email credentials are not completely configured.
        Exception: If there's an error during SMTP communication or email sending.
    """
    if not all([EMAIL_SENDER, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT, SMTP_PASS]):
        logging.error("Error: Credenciales incompletas para el envío de email.")
        raise ValueError("Credenciales incompletas para el envío de email.")
        
    recipients = [email.strip() for email in EMAIL_RECEIVER.split(",")]
    
    # Crear el contenedor del mensaje - 'alternative' permite enviar versiones plain text y HTML.
    msg = MIMEMultipart('alternative')
    msg['From'] = formataddr(("BB Beauty Bot Premium", EMAIL_SENDER)) # Nombre del remitente personalizado
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    msg['X-Priority'] = '1' # Marcar como alta prioridad
    
    # Adjuntar la versión en texto plano del cuerpo del mensaje.
    # Aunque el foco es el HTML, el texto plano es un buen fallback.
    msg.attach(MIMEText(body_text, 'plain'))
    
    # Adjuntar la versión HTML del cuerpo del mensaje.
    # Incluye estilos CSS inline para máxima compatibilidad con clientes de correo.
    html_content = f"""
    <html>
    <head>
        <style>
            /* Estilos generales y específicos para el correo */
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
    
    # Enviar el correo usando SMTP.
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()  # Iniciar TLS para seguridad
            server.login(EMAIL_SENDER, SMTP_PASS)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())
        logging.info(f"Email premium enviado a: {', '.join(recipients)}")
    except Exception as e:
        logging.error(f"Error enviando email: {str(e)}")
        raise

def test_with_saved_data() -> List[str]:
    """
    Utility function to load product URLs from the PERPLEXITY_SAVE_FILE.

    Useful for testing parts of the system that require product URLs without
    making an API call, or for quickly seeding data.

    Returns:
        List[str]: A list of product URLs, or an empty list if the file
                   is not found, is corrupted, or contains no valid product URLs.
    """
    try:
        with open(PERPLEXITY_SAVE_FILE, 'r') as f:
            products = json.load(f)
        if not isinstance(products, list):
            logging.warning(f"'{PERPLEXITY_SAVE_FILE}' (loaded by test_with_saved_data) does not contain a list.")
            return []

        urls = [p['url'] for p in products if isinstance(p, dict) and 'url' in p]
        logging.info(f"Usando {len(urls)} productos guardados desde '{PERPLEXITY_SAVE_FILE}' para prueba.")
        return urls
    except FileNotFoundError:
        logging.error(f"Archivo de datos guardados '{PERPLEXITY_SAVE_FILE}' no encontrado para prueba.")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Error decodificando JSON de '{PERPLEXITY_SAVE_FILE}' para prueba: {str(e)}")
        return []
    except Exception as e:
        logging.error(f"Error cargando datos guardados para prueba: {str(e)}")
        return []

# --- Flujo Principal ---
def main(test_mode: bool = False):
    """
    Main function for the BB Beauty Bot.

    Orchestrates the process of:
    1. Checking if it's a weekday (exits on weekends).
    2. Fetching product URLs (via API on Mondays, from cache otherwise).
    3. Selecting a product for the current day.
    4. Generating a newsletter for the selected product.
    5. Sending the newsletter via email.

    Logs critical errors encountered during the process. The `test_mode`
    parameter is currently passed but does not significantly alter behavior.

    Args:
        test_mode (bool): A flag originally intended for testing mode.
                          Currently has no specific effect in the main flow.
    """
    logging.info("🚀 Iniciando BB Beauty Bot - Sistema Completo")
    state = load_state() # Cargar estado de la aplicación
    
    try:
        # Verificar si es fin de semana (0=Lunes, ..., 5=Sábado, 6=Domingo)
        today = datetime.now().weekday()
        if today >= 5:  # Sábado o Domingo
            logging.info("Es fin de semana, no se envía newsletter. Finalizando ejecución.")
            return
            
        # Paso 1: Obtener URLs de productos
        logging.info("Paso 1: Obteniendo URLs de productos...")
        product_urls = find_product_urls()
        if not product_urls:
            logging.warning("No se encontraron URLs de productos válidas. Finalizando ejecución.")
            return
        logging.info(f"Se encontraron {len(product_urls)} URLs de productos.")
            
        # Paso 2: Seleccionar producto del día
        logging.info("Paso 2: Seleccionando producto del día...")
        try:
            # Cargar la lista de productos desde el archivo guardado por find_product_urls
            with open(PERPLEXITY_SAVE_FILE, 'r') as f:
                products = json.load(f)

            if not isinstance(products, list):
                logging.error(f"El archivo '{PERPLEXITY_SAVE_FILE}' no contiene una lista válida para la selección de productos. Finalizando.")
                return

            # Seleccionar producto basado en el día de la semana (Lunes=0, Martes=1, etc.)
            if today >= len(products):
                logging.warning(f"No hay suficientes productos en '{PERPLEXITY_SAVE_FILE}' para el día de hoy (índice {today}, total {len(products)}). Finalizando.")
                return

            product_candidate = products[today] # El producto para el día actual

            # Validar la estructura del producto seleccionado
            if not isinstance(product_candidate, dict) or \
               not all(k in product_candidate for k in ['nombre', 'marca', 'url']): # Claves esenciales
                logging.error(f"El producto en el índice {today} en '{PERPLEXITY_SAVE_FILE}' está malformado o le faltan claves esenciales. Finalizando.")
                logging.debug(f"Datos del producto candidato: {product_candidate}")
                return

            product = product_candidate
            logging.info(f"Producto seleccionado para {['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'][today]}: {product.get('nombre', 'Nombre Desconocido')}")

        except FileNotFoundError:
            logging.error(f"El archivo de productos '{PERPLEXITY_SAVE_FILE}' no fue encontrado durante la selección del producto del día. Finalizando.")
            return
        except json.JSONDecodeError as e:
            logging.error(f"Error decodificando JSON de '{PERPLEXITY_SAVE_FILE}' durante la selección del producto del día: {str(e)}. Finalizando.")
            return
        except Exception as e: # Captura general para otros errores inesperados
            logging.error(f"Error inesperado cargando el producto del día desde '{PERPLEXITY_SAVE_FILE}': {str(e)}. Finalizando.")
            return
        
        # Paso 3: Generar y enviar newsletter para el producto del día
        logging.info(f"Paso 3: Generando y enviando newsletter para: {product.get('nombre', 'N/A')}")
        try:
            # Generar contenido del newsletter
            newsletter_content = generate_newsletter(product)
            
            # Crear asunto del correo
            subject = f"✨ BB Beauty Bot | Producto del Día: {product.get('marca','Marca Desconocida')} {product.get('nombre','Nombre Desconocido')}"
            
            # Enviar el correo electrónico
            send_email(
                subject=subject,
                body_text=newsletter_content,
                product_url=product.get('url', '#') # Usar '#' como URL de fallback
            )
            
            logging.info(f"✅ Newsletter enviado exitosamente para: {product.get('nombre', 'N/A')}")
            
        except Exception as e: # Captura errores de generación de newsletter o envío de email
            logging.error(f"Error durante la generación o envío del newsletter para '{product.get('nombre', 'N/A')}': {str(e)}")
            # Decidir si relanzar la excepción o simplemente terminar. Por ahora, se relanza.
            raise
        
    except Exception as e: # Captura cualquier otra excepción no manejada en el flujo principal
        logging.critical(f"💣 Error crítico no manejado en el flujo principal de BB Beauty Bot: {str(e)}")

if __name__ == "__main__":
# Este bloque se ejecuta cuando el script es llamado directamente.
# Ideal para iniciar la lógica principal de la aplicación.
    main(test_mode=True)