import os
import base64
import asyncio
import json
import requests
import edge_tts
from flask import Flask, render_template, request, jsonify
from groq import Groq
from datetime import datetime, timedelta
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

# --- SISTEMA DE CASCADA ---
def llamar_ia_con_respaldo(mensajes, herramientas_activas=None):
    modelos_disponibles = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",    
        "mixtral-8x7b-32768"       
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
            if "rate limit" in error_str or "429" in error_str or "400" in error_str or "tool_use_failed" in error_str:
                print(f"⚠️ Modelo {modelo} falló. Cambiando al siguiente...")
                continue
            else:
                raise e
                
    raise Exception("Todos mis motores de IA están temporalmente agotados.")

# --- HERRAMIENTA 1: BÚSQUEDA ---
def buscar_en_internet(query):
    try:
        resultados = DDGS().text(query, max_results=3)
        if not resultados:
            return "No se encontraron resultados recientes."
        texto_resultado = "Aquí tienes la información de internet:\n"
        for r in resultados:
            texto_resultado += f"- {r['title']}: {r['body']}\n"
        return texto_resultado
    except Exception as e:
        return f"Error al buscar en internet: {str(e)}"

# --- HERRAMIENTA 2: LEER CALENDARIO ---
def leer_agenda(google_token):
    if not google_token:
        return "Error: No tengo acceso a tu calendario."
    
    ahora = datetime.utcnow().isoformat() + 'Z' 
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin={ahora}&maxResults=10&singleEvents=true&orderBy=startTime"
    headers = {"Authorization": f"Bearer {google_token}", "Accept": "application/json"}
    
    try:
        respuesta = requests.get(url, headers=headers)
        if respuesta.status_code == 200:
            eventos = respuesta.json().get('items', [])
            if not eventos:
                return "La agenda está libre. No tienes eventos próximos."
            
            texto_agenda = "Aquí están los próximos eventos:\n"
            for evento in eventos:
                resumen = evento.get('summary', 'Evento sin título')
                inicio = evento['start'].get('dateTime', evento['start'].get('date'))
                texto_agenda += f"- {resumen} (Fecha y hora: {inicio})\n"
            return texto_agenda
        else:
            return f"Error al leer el calendario: {respuesta.text}"
    except Exception as e:
        return f"Error interno: {str(e)}"

# --- HERRAMIENTA 3: CREAR EVENTO (¡LA NUEVA MAGIA!) ---
def crear_evento_calendario(google_token, summary, start_time, end_time):
    if not google_token:
        return "Error: No tengo permisos de escritura. Cierra sesión y vuelve a entrar."
    
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {google_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "America/Guatemala"},
        "end": {"dateTime": end_time, "timeZone": "America/Guatemala"}
    }
    
    try:
        respuesta = requests.post(url, headers=headers, json=payload)
        if respuesta.status_code == 200:
            return f"¡Éxito! El evento '{summary}' fue creado en la agenda correctamente."
        else:
            return f"Error al crear el evento en Google: {respuesta.text}"
    except Exception as e:
        return f"Error interno del servidor: {str(e)}"

# --- MOTOR DE VOZ ---
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
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    user_id = data.get("uid")
    user_name = data.get("user_name", "Usuario")
    google_token = data.get("google_token") 
    
    if not user_id:
        return jsonify({"response": "Error: Necesitas iniciar sesión con Google."}), 200

    zona_horaria = pytz.timezone('America/Guatemala')
    fecha_hora_actual = datetime.now(zona_horaria).strftime('%Y-%m-%d %H:%M:%S')
    
    doc_ref = db.collection('usuarios').document(user_id)
    doc = doc_ref.get()
    
    historial = []
    es_creador = False

    if doc.exists:
        datos_bd = doc.to_dict()
        historial = datos_bd.get('historial', [])

    instrucciones = f"""
    Tu nombre es Primux. Eres el asistente virtual de {user_name}.
    Hoy es {fecha_hora_actual} (Hora de Guatemala). TIENES ACCESO A SU AGENDA.
    Puedes LEER y CREAR eventos. Sé conciso.
    """

    if len(historial) == 0:
        historial.append({"role": "system", "content": instrucciones})
    else:
        if historial[0].get("role") == "system":
            historial[0] = {"role": "system", "content": instrucciones}
        else:
            historial.insert(0, {"role": "system", "content": instrucciones})

    historial.append({"role": "user", "content": user_message})

    # --- AGREGAMOS LA NUEVA HERRAMIENTA AL CEREBRO ---
    herramientas = [
        {
            "type": "function",
            "function": {
                "name": "buscar_en_internet",
                "description": "Busca datos en internet.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "leer_agenda",
                "description": "Lee los próximos eventos de la agenda.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "crear_evento_calendario",
                "description": "Crea un nuevo evento en Google Calendar. El formato de las fechas debe ser estricto (ISO 8601).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Título del evento."},
                        "start_time": {"type": "string", "description": "Fecha inicio en ISO 8601 (ej. '2026-06-05T18:00:00')."},
                        "end_time": {"type": "string", "description": "Fecha fin en ISO 8601 (ej. '2026-06-05T19:00:00')."}
                    },
                    "required": ["summary", "start_time", "end_time"],
                },
            },
        }
    ]

    try:
        respuesta_mensaje = llamar_ia_con_respaldo(historial, herramientas)
        
        if respuesta_mensaje.tool_calls:
            mensaje_asistente = {
                "role": "assistant",
                "content": respuesta_mensaje.content,
                "tool_calls": [
                    {
                        "id": t.id,
                        "type": "function",
                        "function": {"name": t.function.name, "arguments": t.function.arguments}
                    } for t in respuesta_mensaje.tool_calls
                ]
            }
            historial.append(mensaje_asistente)
            
            for tool_call in respuesta_mensaje.tool_calls:
                nombre_funcion = tool_call.function.name
                argumentos = json.loads(tool_call.function.arguments)
                
                if nombre_funcion == "buscar_en_internet":
                    resultados = buscar_en_internet(argumentos.get("query"))
                elif nombre_funcion == "leer_agenda":
                    resultados = leer_agenda(google_token)
                elif nombre_funcion == "crear_evento_calendario":
                    print(f"📝 Creando evento: {argumentos.get('summary')}...")
                    resultados = crear_evento_calendario(
                        google_token, 
                        argumentos.get("summary"), 
                        argumentos.get("start_time"), 
                        argumentos.get("end_time")
                    )
                
                historial.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": nombre_funcion,
                    "content": resultados,
                })
            
            respuesta_mensaje_2 = llamar_ia_con_respaldo(historial)
            primux_respuesta = respuesta_mensaje_2.content
        else:
            primux_respuesta = respuesta_mensaje.content
        
        historial.append({"role": "assistant", "content": primux_respuesta})
        doc_ref.set({'historial': historial, 'es_creador': es_creador})

        audio_base64 = generar_voz(primux_respuesta)
        return jsonify({"response": primux_respuesta, "audio": audio_base64})
        
    except Exception as e:
        print(f"💥 ERROR: {str(e)}")
        return jsonify({"response": f"Error: {str(e)}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)