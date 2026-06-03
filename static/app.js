// --- 1. IMPORTAR FIREBASE DESDE LOS SERVIDORES DE GOOGLE ---
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

// --- 2. TU CONFIGURACIÓN DE SEGURIDAD ---
const firebaseConfig = {
  apiKey: "AIzaSyDrn-rKvs5F-qGpyqOv7N2fVfj1I7ovQwE",
  authDomain: "primux-fb211.firebaseapp.com",
  projectId: "primux-fb211",
  storageBucket: "primux-fb211.firebasestorage.app",
  messagingSenderId: "306312909213",
  appId: "1:306312909213:web:29875273a1c00e3c329f74"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

let currentUser = null; 
let googleAccessToken = null; 

document.addEventListener('DOMContentLoaded', () => {
    const loginContainer = document.getElementById('login-container');
    const appContainer = document.getElementById('app-container');
    const googleLoginBtn = document.getElementById('google-login-btn');
    const logoutBtn = document.getElementById('logout-btn');

    const sessionId = Math.random().toString(36).substring(2, 15);
    const textInput = document.getElementById('text-input');
    const sendButton = document.getElementById('send-button');
    const characterImage = document.getElementById('character-image');
    const status = document.getElementById('status');

    const openMouthImg = `/static/images/boca-abierta.png?v=${sessionId}`;
    const closedMouthImg = `/static/images/boca-cerrada.png?v=${sessionId}`;

    characterImage.src = closedMouthImg;
    const preloadOpen = new Image(); preloadOpen.src = openMouthImg;
    const preloadClosed = new Image(); preloadClosed.src = closedMouthImg;

    let lipSyncInterval;
    let currentAudio = null;

    // --- 4. CONTROLADOR DE PUERTAS ---
    onAuthStateChanged(auth, (user) => {
        if (user) {
            currentUser = user;
            // 🧠 AQUÍ RECUPERAMOS EL PASE VIP SI RECARGASTE LA PÁGINA
            googleAccessToken = sessionStorage.getItem('google_token');
            
            loginContainer.style.display = 'none';
            appContainer.style.display = 'block'; 
            status.textContent = `¡Hola, ${user.displayName.split(' ')[0]}! ¿En qué puedo ayudarte?`;
        } else {
            currentUser = null;
            googleAccessToken = null;
            // 🧠 BORRAMOS EL PASE VIP POR SEGURIDAD AL SALIR
            sessionStorage.removeItem('google_token'); 
            loginContainer.style.display = 'flex';
            appContainer.style.display = 'none';
        }
    });

    googleLoginBtn.addEventListener('click', async () => {
        try {
            provider.addScope('https://www.googleapis.com/auth/calendar.readonly');
            const result = await signInWithPopup(auth, provider);
            
            const credential = GoogleAuthProvider.credentialFromResult(result);
            if (credential) {
                googleAccessToken = credential.accessToken;
                // 🧠 GUARDAMOS EL PASE VIP EN LA MEMORIA DEL NAVEGADOR
                sessionStorage.setItem('google_token', googleAccessToken);
            }
        } catch (error) {
            console.error("Error al iniciar sesión:", error);
            alert("Hubo un error al conectar con Google. Revisa tu conexión.");
        }
    });

    logoutBtn.addEventListener('click', async () => {
        try {
            await signOut(auth);
        } catch (error) {
            console.error("Error al cerrar sesión:", error);
        }
    });

    // --- 5. LÓGICA DE ANIMACIÓN ---
    const typewriter = (text, element, speed = 50) => {
        if (window.Intl && Intl.Segmenter) {
            const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
            const segments = Array.from(segmenter.segment(text)).map(s => s.segment);
            let i = 0; element.innerHTML = "";
            function type() {
                if (i < segments.length) {
                    element.innerHTML += segments[i];
                    i++; setTimeout(type, speed);
                }
            }
            type();
        } else {
            let i = 0; element.innerHTML = "";
            function type() {
                if (i < text.length) {
                    element.innerHTML += text.charAt(i);
                    i++; setTimeout(type, speed);
                }
            }
            type();
        }
    };

    const playAudio = (base64Audio) => {
        if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
            clearInterval(lipSyncInterval);
        }
        if (!base64Audio) return;

        currentAudio = new Audio("data:audio/mpeg;base64," + base64Audio);

        currentAudio.addEventListener('play', () => {
            let mouthOpen = true;
            lipSyncInterval = setInterval(() => {
                characterImage.src = mouthOpen ? openMouthImg : closedMouthImg;
                mouthOpen = !mouthOpen;
            }, 150);
        });

        currentAudio.addEventListener('ended', () => { clearInterval(lipSyncInterval); characterImage.src = closedMouthImg; });
        currentAudio.addEventListener('pause', () => { clearInterval(lipSyncInterval); characterImage.src = closedMouthImg; });
        
        currentAudio.play().catch(e => {
            console.error('Error reproduciendo:', e);
            clearInterval(lipSyncInterval); characterImage.src = closedMouthImg;
        });
    };

    // --- 6. ENVÍO DE MENSAJES ---
    const handleSendMessage = async () => {
        const message = textInput.value.trim();
        if (!message || !currentUser) return; 

        textInput.value = '';
        textInput.style.height = '50px';
        status.textContent = "Pensando..."; 

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    message: message, 
                    session_id: sessionId,
                    uid: currentUser.uid,
                    user_name: currentUser.displayName,
                    google_token: googleAccessToken
                }),
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();
            typewriter(data.response, status);
            if (data.audio) playAudio(data.audio);

        } catch (error) {
            console.error('Error:', error);
            typewriter('Lo siento, ha habido un corte en mi matriz de comunicación.', status);
        }
    };

    sendButton.addEventListener('click', handleSendMessage);
    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); handleSendMessage();
        }
    });
    textInput.addEventListener('input', () => {
        textInput.style.height = 'auto';
        textInput.style.height = `${textInput.scrollHeight}px`;
    });
});