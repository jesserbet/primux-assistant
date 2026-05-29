document.addEventListener('DOMContentLoaded', () => {
    const sessionId = Math.random().toString(36).substring(2, 15);
    const textInput = document.getElementById('text-input');
    const sendButton = document.getElementById('send-button');
    const characterImage = document.getElementById('character-image');
    const status = document.getElementById('status');

    const openMouthImg = `/static/images/boca-abierta.png?v=${sessionId}`;
    const closedMouthImg = `/static/images/boca-cerrada.png?v=${sessionId}`;

    // Apply cache-busted source immediately and preload images
    characterImage.src = closedMouthImg;
    const preloadOpen = new Image();
    preloadOpen.src = openMouthImg;
    const preloadClosed = new Image();
    preloadClosed.src = closedMouthImg;

    let lipSyncInterval;
    let currentAudio = null; // Variable para controlar el audio actual

    const typewriter = (text, element, speed = 50) => {
        if (window.Intl && Intl.Segmenter) {
            const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
            const segments = Array.from(segmenter.segment(text)).map(s => s.segment);
            
            let i = 0;
            element.innerHTML = "";

            function type() {
                if (i < segments.length) {
                    element.innerHTML += segments[i];
                    i++;
                    setTimeout(type, speed);
                }
            }
            type();
        } else {
            let i = 0;
            element.innerHTML = "";
            function type() {
                if (i < text.length) {
                    element.innerHTML += text.charAt(i);
                    i++;
                    setTimeout(type, speed);
                }
            }
            type();
        }
    };

    // NUEVO MOTOR DE AUDIO DE ALTA DEFINICIÓN
    const playAudio = (base64Audio) => {
        // Si hay un audio sonando, lo detenemos
        if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
            clearInterval(lipSyncInterval);
        }

        if (!base64Audio) {
            console.error("No se recibió audio de ElevenLabs");
            return;
        }

        // Crear reproductor de MP3 usando los datos en base64
        currentAudio = new Audio("data:audio/mpeg;base64," + base64Audio);

        // Cuando el audio empieza a sonar, iniciamos la animación
        currentAudio.addEventListener('play', () => {
            let mouthOpen = true;
            lipSyncInterval = setInterval(() => {
                characterImage.src = mouthOpen ? openMouthImg : closedMouthImg;
                mouthOpen = !mouthOpen;
            }, 150); // Velocidad de la boca (150ms)
        });

        // Cuando el audio termina o hay un error, cerramos la boca
        currentAudio.addEventListener('ended', () => {
            clearInterval(lipSyncInterval);
            characterImage.src = closedMouthImg;
        });

        currentAudio.addEventListener('pause', () => {
            clearInterval(lipSyncInterval);
            characterImage.src = closedMouthImg;
        });

        // Reproducir el audio
        currentAudio.play().catch(e => {
            console.error('Error reproduciendo el audio:', e);
            clearInterval(lipSyncInterval);
            characterImage.src = closedMouthImg;
        });
    };

    const handleSendMessage = async () => {
        const message = textInput.value.trim();
        if (!message) return;

        textInput.value = '';
        textInput.style.height = '50px';
        status.textContent = "Pensando..."; 

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message, session_id: sessionId }),
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            
            // 1. Escribir el texto en pantalla
            typewriter(data.response, status);
            
            // 2. Reproducir la voz humana (si el servidor la envió)
            if (data.audio) {
                playAudio(data.audio);
            }

        } catch (error) {
            console.error('Error:', error);
            const errorMessage = 'Lo siento, ha habido un corte en mi matriz de comunicación.';
            typewriter(errorMessage, status);
        }
    };

    sendButton.addEventListener('click', handleSendMessage);

    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });

    textInput.addEventListener('input', () => {
        textInput.style.height = 'auto';
        textInput.style.height = `${textInput.scrollHeight}px`;
    });
});