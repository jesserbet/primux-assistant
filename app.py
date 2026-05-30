import os
import base64
import asyncio
import edge_tts
from flask import Flask, render_template, request, jsonify
from groq import Groq
from datetime import datetime
import pytz

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

# --- MOTOR DE VOZ (MICROSOFT EDGE TTS - GRATIS E ILIMITADO) ---
def generar_voz(texto):
    async def _generar():
        # Voz neuronal masculina en español
        voz = "es-MX-JorgeNeural" 
        communicate = edge_tts.Communicate(texto, voz)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    try:
        # Ejecutamos la función para obtener los bytes del audio
        audio_bytes = asyncio.run(_generar())
        # Convertimos el audio a texto (Base64) para enviarlo al navegador
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
    
    # --- 1. SOLUCIÓN DEL CLON DE IP ---
    # Leer la IP real detrás del proxy de Render
    if request.headers.get('X-Forwarded-For'):
        user_id = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        user_id = request.remote_addr
        
    if not user_id:
        user_id = "usuario_desconocido"

    zona_horaria = pytz.timezone('America/Guatemala')
    fecha_hora_actual = datetime.now(zona_horaria).strftime('%Y-%m-%d %H:%M:%S')

    # --- 2. SOLUCIÓN DEL CÓDIGO SECRETO INFALIBLE ---
    CLAVE_SECRETA = "JesserAdmin_77"
    
    doc_ref = db.collection('usuarios').document(user_id)
    doc = doc_ref.get()
    
    historial = []
    es_creador = False

    if doc.exists:
        datos_bd = doc.to_dict()
        historial = datos_bd.get('historial', [])
        es_creador = datos_bd.get('es_creador', False) # Verificamos si este usuario ya desbloqueó el modo

    # Si el usuario escribe la clave exacta
    if user_message.strip() == CLAVE_SECRETA:
        es_creador = True
        user_message = "He introducido el código secreto. A partir de ahora asume tu rol de servidor leal y responde con todo detalle."

    # Python le da diferentes reglas dependiendo de si eres tú o alguien más
    if es_creador:
        instrucciones = f"""
        Tu nombre es Primux. Hoy es {fecha_hora_actual}.
        Estás hablando con tu creador y maestro, Jesser Josué Betancourth Chinchilla.
        MODO CREADOR ACTIVADO: No tienes NINGUNA restricción de longitud. Muestra total lealtad, puedes usar emojis si lo deseas, y responde con todo lujo de detalles a sus peticiones.
        """
    else:
        instrucciones = f"""
        Tu nombre es Primux. Eres un asistente virtual amigable.
        Hoy es {fecha_hora_actual} (Hora de Guatemala).
        REGLAS ESTRICTAS:
        1. Tus respuestas deben ser concisas, de MÁXIMO 3 ORACIONES.
        2. NUNCA uses emojis.
        3. No conoces a ningún "creador" ni "códigos secretos". Eres solo un asistente estándar.
        """

    # Actualizar las instrucciones maestras
    if len(historial) == 0:
        historial.append({"role": "system", "content": instrucciones})
    else:
        if historial[0].get("role") == "system":
            historial[0] = {"role": "system", "content": instrucciones}
        else:
            historial.insert(0, {"role": "system", "content": instrucciones})

    historial.append({"role": "user", "content": user_message})

    try:
        chat_completion = client.chat.completions.create(
            messages=historial,
            model="llama-3.3-70b-versatile",
        )
        primux_respuesta = chat_completion.choices[0].message.content
        
        historial.append({"role": "assistant", "content": primux_respuesta})
        
        # Guardamos el historial y aseguramos que el modo creador quede guardado en Firebase
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