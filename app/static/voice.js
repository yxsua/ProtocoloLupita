/**
 * voice.js — Frontend del módulo de voz (Doña Lupita)
 *
 * Funcionalidades:
 *   1. Reconocimiento de voz:
 *      - Si Whisper está activo en servidor: graba WAV 16kHz y lo envía al backend.
 *      - Si Whisper no está activo: usa Web Speech API (es-MX) del navegador en tiempo real.
 *   2. Reproducción de la voz de Lupita:
 *      - Audios pregrabados (/voice/audio/*.wav) con voz en español.
 *      - Piper TTS en base64 para dígitos dinámicos, con respaldo automático de
 *        Web Speech Synthesis (es-MX) si Piper no está instalado.
 *   3. Temporizador de duración de llamada y modo texto siempre disponible.
 */

// ═══════════════════════════════════════════════════════════════════════
//  Estado global
// ═══════════════════════════════════════════════════════════════════════

const state = {
    sessionId: null,
    active: false,
    recording: false,
    processing: false,
    startTime: null,
    maxDuration: 300,
    timerInterval: null,
    audioStatus: { microfono: true, whisper: false, piper: false },

    // Grabación WAV (modo Whisper servidor)
    mediaRecorder: null,
    audioChunks: [],
    audioStream: null,

    // Reconocimiento en navegador (respaldo cuando Whisper no está instalado)
    speechRecognition: null,
    speechTranscript: '',
    speechRestartTimer: null,
    speechLanguage: 'es-MX',
};

// ═══════════════════════════════════════════════════════════════════════
//  Referencias DOM
// ═══════════════════════════════════════════════════════════════════════

const $ = (id) => document.getElementById(id);

const els = {
    btnStart:       $('btnStart'),
    startScreen:    $('startScreen'),
    callScreen:     $('callScreen'),
    chatContainer:  $('chatContainer'),
    textInput:      $('textInput'),
    btnSend:        $('btnSend'),
    btnMic:         $('btnMic'),
    btnHangup:      $('btnHangup'),
    timer:          $('timer'),
    callStatus:     $('callStatus'),
    processing:     $('processing'),
    audioPlayer:    $('audioPlayer'),
    badgeMic:       $('badgeMic'),
    badgeWhisper:   $('badgeWhisper'),
    badgePiper:     $('badgePiper'),
    cfgMaxDuration: $('cfgMaxDuration'),
};


// ═══════════════════════════════════════════════════════════════════════
//  1. INICIAR / TERMINAR LLAMADA
// ═══════════════════════════════════════════════════════════════════════

async function startCall() {
    const maxDur = parseInt(els.cfgMaxDuration.value) || 300;
    state.maxDuration = maxDur;
    els.btnStart.disabled = true;
    $('incomingNotice').textContent = 'Contestando la llamada…';

    const form = new FormData();
    form.append('max_duration', maxDur);

    try {
        const res = await fetch('/voice/start', { method: 'POST', body: form });
        const responseText = await res.text();
        let data = null;
        try {
            data = responseText ? JSON.parse(responseText) : {};
        } catch (_) {
            data = {
                detail: responseText.trim() === 'Internal Server Error'
                    ? `Error interno del servidor (${res.status}). Revisa el registro de la aplicación.`
                    : responseText.slice(0, 180),
            };
        }
        if (!res.ok) {
            throw new Error(data.detail || `El servidor respondió con error (${res.status}).`);
        }
        if (!data.session_id || !data.result) {
            throw new Error('El servidor devolvió una respuesta incompleta. Reinicia la simulación.');
        }

        state.sessionId = data.session_id;
        state.active = true;
        state.startTime = Date.now();
        state.audioStatus = data.audio_status || state.audioStatus;

        // Mostrar pantalla de llamada
        els.startScreen.classList.add('hidden');
        els.callScreen.classList.remove('hidden');
        $('btnAfterCall').classList.add('hidden');

        // Actualizar badges
        updateBadges(state.audioStatus);

        // Agregar saludo de Lupita y reproducir su voz
        addMessage('lupita', data.result.respuesta_texto, data.result.ultima_intencion);
        playLupitaVoice(data.result, null);

        // Iniciar temporizador
        startTimer();
        els.textInput.focus();

    } catch (err) {
        console.error('Error iniciando llamada:', err);
        $('incomingNotice').textContent = err.message || 'No se pudo contestar la llamada. Intenta de nuevo.';
        els.btnStart.disabled = false;
    }
}


async function cancelIncoming() {
    const declineButton = $('btnDecline');
    declineButton.disabled = true;
    els.btnStart.disabled = true;
    $('incomingNotice').textContent = 'Cancelando cualquier sesión activa…';

    try {
        const response = await fetch('/voice/cancel-active', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `No se pudo cancelar (${response.status}).`);

        els.startScreen.classList.add('rejected');
        $('incomingNotice').textContent = data.status === 'cancelled'
            ? 'Llamada activa cancelada. Puedes iniciar otra simulación.'
            : 'Llamada entrante rechazada. Puedes iniciar otra simulación.';
        $('simulatorNotice').textContent = data.status === 'cancelled'
            ? 'Se cerró la sesión que seguía activa en el servidor y el dashboard recibió su evento de cierre.'
            : 'La llamada se rechazó; no había una sesión activa en el servidor.';
        declineButton.classList.add('hidden');
        els.btnStart.classList.add('hidden');
        $('btnNewCall').classList.remove('hidden');
    } catch (error) {
        $('incomingNotice').textContent = error.message || 'No se pudo cancelar la llamada. Intenta de nuevo.';
        declineButton.disabled = false;
        els.btnStart.disabled = false;
    }
}


function newIncomingCall() {
    els.startScreen.classList.remove('rejected');
    $('incomingNotice').textContent = 'La llamada está entrando en el simulador.';
    $('simulatorNotice').textContent = 'Puedes rechazar la llamada entrante o cancelar la conversación en cualquier momento.';
    $('btnDecline').classList.remove('hidden');
    els.btnStart.classList.remove('hidden');
    els.btnStart.disabled = false;
    $('btnNewCall').classList.add('hidden');
}


function startNewCall() {
    state.sessionId = null;
    state.active = false;
    state.processing = false;
    state.startTime = null;
    stopTimer();
    els.chatContainer.replaceChildren();
    els.textInput.value = '';
    els.textInput.disabled = false;
    els.btnSend.disabled = false;
    els.btnMic.disabled = false;
    els.btnHangup.disabled = false;
    $('btnAfterCall').classList.add('hidden');
    els.callScreen.classList.add('hidden');
    els.startScreen.classList.remove('hidden');
    newIncomingCall();
}


async function hangup() {
    if (!state.sessionId) return;

    stopRecording();
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    const form = new FormData();
    form.append('session_id', state.sessionId);

    try {
        const res = await fetch('/voice/hangup', { method: 'POST', body: form });
        const data = await res.json();

        addSystemMessage('El ejemplo terminó.');
        endCall(data.result);

    } catch (err) {
        console.error('Error colgando:', err);
        endCall(null);
    }
}


function endCall(result) {
    state.active = false;
    stopTimer();
    stopRecording();

    els.callStatus.textContent = 'Llamada terminada';
    els.textInput.disabled = true;
    els.btnSend.disabled = true;
    els.btnMic.disabled = true;
    els.btnHangup.disabled = true;
    $('btnAfterCall').classList.remove('hidden');

    if (result && result.indicadores && result.indicadores.length > 0) {
        addSystemMessage('Se encontraron señales que pueden ayudar a revisar la situación.');
    }

    addSystemMessage('Puedes revisar un mensaje o enviar un reporte desde el menú.');
}


// ═══════════════════════════════════════════════════════════════════════
//  2. ENVIAR TEXTO
// ═══════════════════════════════════════════════════════════════════════

async function sendText() {
    const text = els.textInput.value.trim();
    if (!text || !state.active || state.processing) return;

    els.textInput.value = '';
    addMessage('atacante', text);

    await processInput({ text });
}


// ═══════════════════════════════════════════════════════════════════════
//  3. MICRÓFONO — Whisper servidor o Web Speech API del navegador
// ═══════════════════════════════════════════════════════════════════════

async function toggleMic() {
    if (state.recording) {
        stopRecording();
    } else {
        await startRecording();
    }
}


async function startRecording() {
    // Prioriza reconocimiento local: el audio no se envía a servicios remotos.
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!state.audioStatus.whisper && SpeechRec) {
        await startLocalBrowserSpeechRecognition(SpeechRec);
        return;
    }

    // Camino con Whisper en servidor (o grabación WAV directa)
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
            }
        });

        state.audioStream = stream;
        state.audioChunks = [];

        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : 'audio/webm';

        state.mediaRecorder = new MediaRecorder(stream, { mimeType });

        state.mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) state.audioChunks.push(e.data);
        };

        state.mediaRecorder.onstop = async () => {
            const blob = new Blob(state.audioChunks, { type: mimeType });
            const wavBlob = await convertToWav(blob);

            addMessage('atacante', '🎤 (Audio enviado — transcribiendo...)');
            await processInput({ audio: wavBlob });

            if (state.audioStream) {
                state.audioStream.getTracks().forEach(t => t.stop());
                state.audioStream = null;
            }
        };

        state.mediaRecorder.start(250);
        setRecordingUI(true, '🔴 Grabando...');

    } catch (err) {
        console.error('Error accediendo al micrófono:', err);
        addSystemMessage('⚠️ No se pudo acceder al micrófono. Usa el modo texto.');
    }
}


async function startLocalBrowserSpeechRecognition(SpeechRec) {
    if (typeof SpeechRec.available !== 'function') {
        const message = 'Este navegador no ofrece reconocimiento local de voz. Usa el modo texto o configura Whisper local.';
        $('speechSetupNotice').textContent = message;
        return;
    }

    try {
        let availability = 'unavailable';
        for (const language of ['es-MX', 'es-ES']) {
            availability = await SpeechRec.available({ langs: [language], processLocally: true });
            if (availability !== 'unavailable') {
                state.speechLanguage = language;
                break;
            }
        }
        if (availability === 'available') {
            startBrowserSpeechRecognition(SpeechRec);
        } else if (availability === 'downloadable') {
            $('speechSetupNotice').textContent = `Este equipo necesita el paquete local ${state.speechLanguage} antes de poder dictar.`;
            if (typeof SpeechRec.install === 'function') {
                $('btnInstallSpeech').classList.remove('hidden');
            } else {
                $('speechSetupNotice').textContent += ' La instalación desde el navegador no está disponible; configura Whisper local o usa texto.';
            }
        } else if (availability === 'downloading') {
            $('speechSetupNotice').textContent = 'El paquete local de español todavía se está preparando. Intenta de nuevo en unos momentos.';
        } else {
            const message = 'No hay reconocimiento local de español disponible. Puedes escribir la frase o configurar Whisper local.';
            $('speechSetupNotice').textContent = message;
        }
    } catch (error) {
        console.warn('No se pudo consultar el reconocimiento local:', error);
        $('speechSetupNotice').textContent = 'No se pudo iniciar el reconocimiento local. Usa el modo texto o configura Whisper local.';
    }
}


async function installLocalSpeech() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const button = $('btnInstallSpeech');
    if (!SpeechRec || typeof SpeechRec.install !== 'function') return;

    button.disabled = true;
    button.textContent = 'Preparando paquete local…';
    $('speechSetupNotice').textContent = 'Descargando el paquete de reconocimiento en español para este dispositivo.';
    try {
        const installed = await SpeechRec.install({ langs: [state.speechLanguage], processLocally: true });
        if (!installed) throw new Error('El navegador no pudo instalar el paquete de español.');
        $('speechSetupNotice').textContent = 'Paquete local listo. Presiona Voz para empezar a hablar.';
        button.classList.add('hidden');
    } catch (error) {
        $('speechSetupNotice').textContent = error.message || 'No se pudo instalar el paquete. Usa el modo texto o configura Whisper local.';
    } finally {
        button.disabled = false;
        button.textContent = 'Preparar reconocimiento local de voz';
    }
}


function startBrowserSpeechRecognition(SpeechRec, resume = false) {
    try {
        const recognition = new SpeechRec();
        recognition.lang = state.speechLanguage;
        recognition.processLocally = true;
        recognition.interimResults = true;
        recognition.continuous = true;

        if (!resume) state.speechTranscript = '';
        state.speechRecognition = recognition;
        let processedFinalResultCount = 0;

        recognition.onresult = (event) => {
            let finalText = '';
            let interimText = '';
            for (let i = processedFinalResultCount; i < event.results.length; i++) {
                const text = event.results[i][0].transcript.trim();
                if (event.results[i].isFinal) {
                    finalText += `${text} `;
                    processedFinalResultCount = i + 1;
                }
                else interimText += `${text} `;
            }
            if (finalText.trim()) {
                state.speechTranscript = [state.speechTranscript, finalText.trim()]
                    .filter(Boolean)
                    .join(' ')
                    .trim();
            }
            const liveText = [state.speechTranscript, interimText.trim()].filter(Boolean).join(' ');
            els.callStatus.textContent = liveText ? `Escuchando: “${liveText}”` : 'Escuchando a la persona que llama…';
        };

        recognition.onerror = (event) => {
            console.warn('SpeechRecognition error:', event.error);
            if (event.error === 'no-speech') {
                // Algunos navegadores cierran la sesión si hay una pausa al empezar.
                // onend la vuelve a abrir mientras el botón siga en modo escucha.
                return;
            }
            if (['not-allowed', 'service-not-allowed', 'audio-capture', 'network'].includes(event.error)) {
                state.recording = false;
                state.speechRecognition = null;
                const messages = {
                    'not-allowed': 'Permiso de micrófono denegado. Habilítalo en el navegador y vuelve a intentarlo.',
                    'service-not-allowed': 'El navegador no pudo iniciar el paquete local de español. Prepáralo desde esta pantalla o usa Whisper local.',
                    'audio-capture': 'No se encontró un micrófono disponible. Revisa el dispositivo y vuelve a intentarlo.',
                    network: 'El reconocimiento local del navegador no está disponible en este momento. Usa el modo texto o Whisper local.',
                };
                if (event.error === 'service-not-allowed') {
                    $('btnInstallSpeech').classList.remove('hidden');
                    $('speechSetupNotice').textContent = messages[event.error];
                }
                setRecordingUI(false, 'En llamada…');
                $('speechSetupNotice').textContent = messages[event.error];
            }
        };

        recognition.onend = async () => {
            const finalText = state.speechTranscript.trim();
            state.speechRecognition = null;

            if (state.recording && state.active) {
                setRecordingUI(true, 'Pausa breve… sigue hablando');
                state.speechRestartTimer = setTimeout(() => {
                    state.speechRestartTimer = null;
                    if (state.recording && state.active) {
                        startBrowserSpeechRecognition(SpeechRec, true);
                    }
                }, 250);
                return;
            }

            state.speechTranscript = '';
            setRecordingUI(false, 'En llamada...');

            if (finalText && state.active) {
                addMessage('atacante', finalText);
                await processInput({ text: finalText });
            }
        };

        recognition.start();
        setRecordingUI(true, '🔴 Escuchando (habla ahora)...');

    } catch (err) {
        console.error('Error iniciando reconocimiento:', err);
        addSystemMessage('⚠️ Reconocimiento de voz no disponible. Usa el modo texto.');
    }
}


function stopRecording() {
    if (state.speechRestartTimer) {
        clearTimeout(state.speechRestartTimer);
        state.speechRestartTimer = null;
    }
    if (state.speechRecognition) {
        try { state.speechRecognition.stop(); } catch (_) {}
    }
    if (state.mediaRecorder && state.recording) {
        state.mediaRecorder.stop();
    }
    setRecordingUI(false, 'En llamada...');
}


function setRecordingUI(isRecording, statusText) {
    state.recording = isRecording;
    els.btnMic.classList.toggle('recording', isRecording);
    els.btnMic.textContent = isRecording ? '⏹' : '🎤';
    els.callStatus.textContent = statusText;
}


/**
 * Convierte audio blob (webm/opus) a WAV PCM 16-bit mono 16kHz.
 */
async function convertToWav(blob) {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });
        const arrayBuffer = await blob.arrayBuffer();
        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);

        const channelData = audioBuffer.getChannelData(0);
        const sampleRate = audioBuffer.sampleRate;

        let samples = channelData;
        if (sampleRate !== 16000) {
            const ratio = 16000 / sampleRate;
            const newLength = Math.round(channelData.length * ratio);
            samples = new Float32Array(newLength);
            for (let i = 0; i < newLength; i++) {
                const srcIdx = i / ratio;
                const idx0 = Math.floor(srcIdx);
                const idx1 = Math.min(idx0 + 1, channelData.length - 1);
                const frac = srcIdx - idx0;
                samples[i] = channelData[idx0] * (1 - frac) + channelData[idx1] * frac;
            }
        }

        const wavBuffer = encodeWav(samples, 16000);
        audioCtx.close();
        return new Blob([wavBuffer], { type: 'audio/wav' });

    } catch (err) {
        console.error('Error convirtiendo a WAV:', err);
        return blob;
    }
}


function encodeWav(samples, sampleRate) {
    const numChannels = 1;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample / 8;
    const dataLength = samples.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
    view.setUint16(32, numChannels * bytesPerSample, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(view, 36, 'data');
    view.setUint32(40, dataLength, true);

    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        offset += 2;
    }

    return buffer;
}


function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}


// ═══════════════════════════════════════════════════════════════════════
//  4. PROCESAR ENTRADA (enviar al backend)
// ═══════════════════════════════════════════════════════════════════════

async function processInput({ text, audio }) {
    if (!state.active || state.processing) return;

    state.processing = true;
    setProcessing(true);

    // Reproducir audio de espera/relleno mientras procesa audio (ej. Whisper)
    if (audio) {
        const idx = Math.floor(Math.random() * 4) + 1;
        playAudioRef(`espera_0${idx}.mp3`);
    }

    const form = new FormData();
    form.append('session_id', state.sessionId);

    if (audio) form.append('audio', audio, 'recording.wav');
    if (text) form.append('text', text);

    try {
        const res = await fetch('/voice/process', { method: 'POST', body: form });
        const data = await res.json();

        if (data.error) {
            addSystemMessage('No pudimos continuar. Vuelve a iniciar el ejemplo.');
            return;
        }

        const result = data.result;

        if (audio) {
            if (data.transcripcion_usuario) {
                replaceLastAtacanteMessage(data.transcripcion_usuario);
            } else {
                replaceLastAtacanteMessage('(Audio sin transcripción. Usa el modo texto.)');
            }
        } else if (data.transcripcion_usuario) {
            replaceLastAtacanteMessage(data.transcripcion_usuario);
        }

        // Mostrar respuesta de Lupita y reproducir su voz de inmediato
        addMessage('lupita', result.respuesta_texto, result.ultima_intencion);
        playLupitaVoice(result, data.tts_audio_b64);

        if (result.indicadores && result.indicadores.length > 0) {
            addSystemMessage('Se encontró una señal que puede ayudar a revisar la situación.');
        }

        // Verificar fin de llamada
        if (result.status !== 'active') {
            const statusMsg = {
                'timeout': 'El ejemplo terminó por límite de tiempo.',
                'completed': 'El ejemplo terminó.',
                'user_hangup': 'El ejemplo terminó.',
            };
            addSystemMessage(statusMsg[result.status] || 'El ejemplo terminó.');
            endCall(result);
        }

    } catch (err) {
        console.error('Error procesando:', err);
        addSystemMessage('⚠️ Error de comunicación con el servidor');
    } finally {
        state.processing = false;
        setProcessing(false);
    }
}


// ═══════════════════════════════════════════════════════════════════════
//  5. AUDIO — Voz de Lupita (WAV pregrabado, Piper base64 o SpeechSynthesis)
// ═══════════════════════════════════════════════════════════════════════

function playLupitaVoice(result, ttsAudioB64) {
    if (!result) return;

    // 1. Si Piper sintetizó audio dinámico en el servidor
    if (ttsAudioB64) {
        playBase64Audio(ttsAudioB64, result.respuesta_texto);
        return;
    }

    // 2. Si hay fragmento pregrabado en /voice/audio/
    if (result.audio_ref) {
        playAudioRef(result.audio_ref, result.respuesta_texto);
        return;
    }

    // 3. Contenido dinámico sin Piper (ej. repetir dígitos) → voz del navegador
    if (result.tts_texto || result.respuesta_texto) {
        speakBrowserVoice(result.tts_texto || result.respuesta_texto);
    }
}


function playAudioRef(filename, fallbackText = null) {
    if (!filename) return;
    try {
        els.audioPlayer.pause();
        els.audioPlayer.src = `/voice/audio/${filename}`;
        els.audioPlayer.play().catch(() => {
            if (fallbackText) speakBrowserVoice(fallbackText);
        });
    } catch (_) {
        if (fallbackText) speakBrowserVoice(fallbackText);
    }
}


function playBase64Audio(b64data, fallbackText = null) {
    if (!b64data) return;
    try {
        const binary = atob(b64data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: 'audio/wav' });
        const url = URL.createObjectURL(blob);
        els.audioPlayer.pause();
        els.audioPlayer.src = url;
        els.audioPlayer.play().catch(() => {
            if (fallbackText) speakBrowserVoice(fallbackText);
        });
        els.audioPlayer.onended = () => URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Error reproduciendo TTS:', err);
        if (fallbackText) speakBrowserVoice(fallbackText);
    }
}


function speakBrowserVoice(text) {
    if (!text || !('speechSynthesis' in window)) return;
    try {
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'es-MX';
        utter.rate = 0.98;
        utter.pitch = 1.02;

        const voices = window.speechSynthesis.getVoices();
        const natural = voices.find(v =>
            v.lang.startsWith('es-MX') && /Dalia|Natural|Online|Google/i.test(v.name)
        );
        const sabina = voices.find(v => v.lang.startsWith('es-MX') || v.name.includes('Sabina'));
        const spanish = natural || sabina || voices.find(v => v.lang.startsWith('es'));
        if (spanish) utter.voice = spanish;

        window.speechSynthesis.speak(utter);
    } catch (err) {
        console.warn('Error en speechSynthesis:', err);
    }
}


// ═══════════════════════════════════════════════════════════════════════
//  6. TEMPORIZADOR
// ═══════════════════════════════════════════════════════════════════════

function startTimer() {
    state.startTime = Date.now();
    state.timerInterval = setInterval(updateTimer, 1000);
    updateTimer();
}


function stopTimer() {
    if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
    }
}


function updateTimer() {
    const elapsed = getElapsedSeconds();
    const remaining = state.maxDuration - elapsed;

    els.timer.textContent = formatTime(elapsed);

    els.timer.className = 'timer';
    if (remaining <= 30) {
        els.timer.classList.add('danger');
    } else if (remaining <= 60) {
        els.timer.classList.add('warning');
    }

    if (remaining <= 0 && state.active) {
        addSystemMessage('⏱️ Tiempo agotado');
        hangup();
    }
}


function getElapsedSeconds() {
    if (!state.startTime) return 0;
    return Math.floor((Date.now() - state.startTime) / 1000);
}


function formatTime(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}


// ═══════════════════════════════════════════════════════════════════════
//  7. UI — Mensajes y elementos
// ═══════════════════════════════════════════════════════════════════════

function addMessage(role, text, intent) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const content = document.createElement('span');
    content.className = 'text';
    content.textContent = text;
    div.appendChild(content);
    els.chatContainer.appendChild(div);
    scrollToBottom();
}


function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'message system';
    div.textContent = text;
    els.chatContainer.appendChild(div);
    scrollToBottom();
}


function replaceLastAtacanteMessage(newText) {
    const messages = els.chatContainer.querySelectorAll('.message.atacante');
    if (messages.length > 0) {
        const last = messages[messages.length - 1];
        const textSpan = last.querySelector('.text');
        if (textSpan) textSpan.textContent = newText;
    } else if (newText) {
        addMessage('atacante', newText);
    }
}


function setProcessing(active) {
    els.processing.classList.toggle('active', active);
    els.textInput.disabled = active;
    els.btnSend.disabled = active;
}


function updateBadges(status) {
    if (!status) return;

    const set = (el, on) => {
        el.className = `tool-status ${on ? 'on' : 'off'}`;
    };

    const hasBrowserSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    const hasBrowserTTS = 'speechSynthesis' in window;

    set(els.badgeMic, status.microfono);
    set(els.badgeWhisper, status.whisper || hasBrowserSpeech);
    set(els.badgePiper, status.piper || hasBrowserTTS);
    els.badgeMic.textContent = status.microfono ? 'Micrófono disponible' : 'Micrófono no disponible';
    els.badgeWhisper.textContent = (status.whisper || hasBrowserSpeech) ? 'Dictado disponible' : 'Usa el teclado';
    els.badgePiper.textContent = (status.piper || hasBrowserTTS) ? 'Respuesta con voz' : 'Respuesta en texto';
}


function scrollToBottom() {
    requestAnimationFrame(() => {
        els.chatContainer.scrollTop = els.chatContainer.scrollHeight;
    });
}



// ═══════════════════════════════════════════════════════════════════════
//  8. ATAJOS DE TECLADO
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        sendText();
    }
    if (e.code === 'Space' && document.activeElement !== els.textInput && state.active) {
        e.preventDefault();
        toggleMic();
    }
    if (e.key === 'Escape' && state.active) {
        hangup();
    }
});
