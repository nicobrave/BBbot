import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Configuración
load_dotenv()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_SAVE_FILE = "perplexity_response.json"

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def search_skincare_products():
    query = """
    Proporciona información en formato JSON sobre 3 productos de skincare naturales y cruelty-free de 2025,
    disponibles en Sephora o Byrdie, con esta estructura exacta:
    {
      "productos": [
        {
          "nombre": "Nombre del producto",
          "marca": "Marca",
          "descripcion": "Descripción técnica",
          "ingredientes": "Ingredientes clave",
          "precio": "Precio aproximado",
          "url": "Enlace al producto",
          "tipo_piel": "Tipo de piel recomendado",
          "fecha_lanzamiento": "2025"
        }
      ]
    }
    """
    
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Payload CORREGIDO según última documentación de Perplexity
    payload = {
        "model": "sonar",  # Modelo actualmente funcional
        "messages": [{
            "role": "user",
            "content": query
        }],
        "temperature": 0.3  # Menor variabilidad para mejor estructura
    }

    try:
        log("Realizando búsqueda en Perplexity API...")
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            with open(PERPLEXITY_SAVE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            return data
        else:
            log(f"Error en API (HTTP {response.status_code}): {response.text}")
            return None
            
    except Exception as e:
        log(f"Error de conexión: {str(e)}")
        return None

def extract_products_from_response(data):
    """Extrae productos del contenido de la respuesta"""
    try:
        content = data['choices'][0]['message']['content']
        
        # Buscar JSON embebido (método robusto)
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        json_str = content[json_start:json_end]
        
        products_data = json.loads(json_str)
        return products_data.get('productos', [])
        
    except json.JSONDecodeError:
        log("El contenido no contiene JSON válido. Respuesta completa:")
        log(content)
        return []
    except Exception as e:
        log(f"Error procesando respuesta: {str(e)}")
        return []

if __name__ == "__main__":
    log("Iniciando BB Beauty Bot - Versión Estable")
    
    # Paso 1: Búsqueda de productos
    api_response = search_skincare_products()
    
    if api_response:
        # Paso 2: Extracción de productos
        productos = extract_products_from_response(api_response)
        
        if productos:
            log("\n✅ Productos encontrados:")
            for idx, prod in enumerate(productos, 1):
                print(f"\n#{idx} {prod.get('nombre', 'Sin nombre')}")
                print(f"🏭 Marca: {prod.get('marca', 'Desconocida')}")
                print(f"💰 Precio: {prod.get('precio', 'N/A')}")
                print(f"🔗 Enlace: {prod.get('url', 'N/A')}")
        else:
            log("⚠️ No se encontraron productos en la respuesta")
    else:
        log("❌ No se pudo completar la búsqueda")