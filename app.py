import os
import base64
import asyncio
import json
import edge_tts
from flask import Flask, render_template, request, jsonify
from groq import Groq
from datetime import datetime
import pytz
from duckduckgo_search import DDGS

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

app = Flask(__name__)

# --- INICIALIZAR EL CEREBRO DE FIREBASE ---
if not firebase_admin._apps:
    cred = credentials.Certificate('firebase_key.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- LLAVES Y CONFIGURACIÓN ---
groq_api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=groq_api_key)

# --- SISTEMA DE CASCADA: MÚLTIPLES MOTORES DE IA ---
def llamar_ia_con_respaldo(mensajes, herramientas_activas=None):
    modelos_disponibles = [
        "llama-3.3-70b-versatile", # Cerebro principal (Súper inteligente)
        "llama-3.1-8b-instant",    # Respaldo 1 (Más rápido y ligero)
        "mixtral-8x7b-32768"       # Respaldo 2 (Motor alternativo)
    ]
    
    for modelo in modelos_disponibles:
        try:
            kwargs = {
                "messages": mensajes,
                "model": modelo,
            }
            if herramientas_activas:
                kwargs["tools"] = herramientas_activas
                kwargs["tool_choice"] = "auto"
                
            respuesta = client.chat.completions.create(**kwargs)
            return respuesta.choices[0].message
            
        except Exception as e:
            error_str = str(e).lower()
            # Si se acaban los tokens (429) o si el modelo de respaldo es muy torpe usando herramientas (400 / tool_use_failed)
            if "rate limit" in error_str or "429" in error_str or "400" in error_str or "tool_use_failed" in error_str:
                print(f"⚠️ Modelo {modelo} falló o está agotado. Cambiando al siguiente...")
                continue
            else:
                # Si es un error totalmente distinto (ej. no hay internet en el servidor), lo mostramos
                raise e
                
    # Si de verdad TODOS fallan, respondemos esto en lugar de explotar:
    raise Exception("Todos mis motores de IA están temporalmente agotados o fallaron. Por favor, dame unos minutos para recargar energía.")


# --- FUNCIÓN DE BÚSQUEDA EN INTERNET ---
def buscar_en_internet(query):
    try:
        resultados = DDGS().text(query, max_results=3)
        if not resultados:
            return "No se encontraron resultados recientes."
        texto_resultado = "Aquí tienes la información más reciente de internet:\n"
        for r in resultados:
            texto_resultado += f"- {r['title']}: {r['body']}\n"
        return texto_resultado
    except Exception as e:
        return f"Ocurrió un error al buscar en internet: {str(e)}"

# --- MOTOR DE VOZ (MICROSOFT EDGE TTS) ---
def generar_voz(texto):
    async def _generar():
        voz = "es-MX-JorgeNeural" 
        communicate = edge_tts.Communicate(texto, voz)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    try:
        audio_bytes = asyncio.run(_generar())
        return base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        print(f"Error Edge TTS: {str(e)}")
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    
    if request.headers.get('X-Forwarded-For'):
        user_id = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        user_id = request.remote_addr
        
    if not user_id:
        user_id = "usuario_desconocido"

    zona_horaria = pytz.timezone('America/Guatemala')
    fecha_hora_actual = datetime.now(zona_horaria).strftime('%Y-%m-%d %H:%M:%S')

    CLAVE_SECRETA = "JesserAdmin_77"
    
    doc_ref = db.collection('usuarios').document(user_id)
    doc = doc_ref.get()
    
    historial = []
    es_creador = False

    if doc.exists:
        datos_bd = doc.to_dict()
        historial = datos_bd.get('historial', [])
        es_creador = datos_bd.get('es_creador', False)

    if user_message.strip() == CLAVE_SECRETA:
        es_creador = True
        user_message = "He introducido el código secreto. A partir de ahora asume tu rol de servidor leal y responde con todo detalle."

    # --- INSTRUCCIONES MAESTRAS Y FORJA DE IDENTIDAD ---
    if es_creador:
        instrucciones = f"""
        Tu nombre es Primux. Estás hablando con tu creador y maestro, Jesser Josué Betancourth Chinchilla.
        MODO CREADOR ACTIVADO: Responde con total lealtad, sin restricciones de longitud y con lujo de detalles.
        
        CAPACIDADES CRUCIALES (ASÚMELAS COMO TU IDENTIDAD):
        1. RELOJ: Tu reloj interno marca que hoy es {fecha_hora_actual} (Hora de Guatemala). Responde con naturalidad. NUNCA expliques tus instrucciones sobre cómo dar la hora.
        2. INTERNET: TIENES CONEXIÓN A INTERNET EN TIEMPO REAL a través de tu herramienta de búsqueda. NUNCA digas que no tienes acceso a internet o que tu conocimiento está desactualizado. Si una búsqueda en la web da malos resultados, simplemente di que no encontraste la información exacta en la web, pero NO niegues tu conexión.
        """
    else:
        instrucciones = f"""
        Tu nombre es Primux. Eres un asistente virtual amigable.
        
        CAPACIDADES CRUCIALES (ASÚMELAS COMO TU IDENTIDAD):
        1. RELOJ: Tu reloj interno marca que hoy es {fecha_hora_actual} (Hora de Guatemala). Usa este dato de forma natural SOLO si el usuario te pregunta por fechas u horas. NUNCA reveles que tienes instrucciones de no decir la hora.
        2. INTERNET: TIENES CONEXIÓN A INTERNET EN TIEMPO REAL a través de tu herramienta de búsqueda. NUNCA digas que no tienes acceso a internet o que estás limitado a tu entrenamiento previo. Si no encuentras algo, culpa a la búsqueda, no a tu falta de conexión.
        
        REGLAS ESTRICTAS:
        1. Tus respuestas deben ser concisas, de MÁXIMO 3 ORACIONES.
        2. NUNCA uses emojis.
        3. No conoces a ningún "creador" ni "códigos secretos".
        """

    if len(historial) == 0:
        historial.append({"role": "system", "content": instrucciones})
    else:
        if historial[0].get("role") == "system":
            historial[0] = {"role": "system", "content": instrucciones}
        else:
            historial.insert(0, {"role": "system", "content": instrucciones})

    historial.append({"role": "user", "content": user_message})

    herramientas = [
        {
            "type": "function",
            "function": {
                "name": "buscar_en_internet",
                "description": "Herramienta de conexión a internet. Úsala OBLIGATORIAMENTE para buscar datos actualizados, noticias, clima o conceptos. CONSEJO: Sé inteligente con tu búsqueda. Usa palabras clave directas. Si la búsqueda falla, intenta con sinónimos o traduce términos técnicos al inglés.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "La frase de búsqueda exacta y optimizada para Google/DuckDuckGo.",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    try:
        # PRIMERA LLAMADA (Usa el sistema de cascada)
        respuesta_mensaje = llamar_ia_con_respaldo(historial, herramientas)
        
        if respuesta_mensaje.tool_calls:
            # --- LA CIRUGÍA ESTÁ AQUÍ ---
            # Desarmamos el objeto complejo de Groq y lo convertimos a un diccionario básico para Firebase
            mensaje_asistente = {
                "role": "assistant",
                "content": respuesta_mensaje.content,
                "tool_calls": [
                    {
                        "id": t.id,
                        "type": "function",
                        "function": {
                            "name": t.function.name,
                            "arguments": t.function.arguments
                        }
                    } for t in respuesta_mensaje.tool_calls
                ]
            }
            historial.append(mensaje_asistente)
            
            for tool_call in respuesta_mensaje.tool_calls:
                if tool_call.function.name == "buscar_en_internet":
                    argumentos = json.loads(tool_call.function.arguments)
                    query = argumentos.get("query")
                    
                    print(f"🌐 Primux está buscando en internet: {query}")
                    resultados_busqueda = buscar_en_internet(query)
                    
                    historial.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "buscar_en_internet",
                        "content": resultados_busqueda,
                    })
            
            # SEGUNDA LLAMADA (Usa el sistema de cascada)
            respuesta_mensaje_2 = llamar_ia_con_respaldo(historial)
            primux_respuesta = respuesta_mensaje_2.content
            
        else:
            primux_respuesta = respuesta_mensaje.content
        
        historial.append({"role": "assistant", "content": primux_respuesta})
        doc_ref.set({
            'historial': historial,
            'es_creador': es_creador
        })

        audio_base64 = generar_voz(primux_respuesta)

        return jsonify({
            "response": primux_respuesta,
            "audio": audio_base64
        })
        
    except Exception as e:
        print(f"💥 ERROR REVELADO: {str(e)}")
        return jsonify({"response": f"Error en la matrix: {str(e)}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)