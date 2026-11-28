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
};

// ═══════════════════════════════════════════════════════════════════════
//  Referencias DOM
// ═══════════════════════════════════════════════════════════════════════

const $ = (id) => document.getElementById(id);

const els = {
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

    const form = new FormData();
    form.append('max_duration', maxDur);

    try {
        const res = await fetch('/voice/start', { method: 'POST', body: form });
        const data = await res.json();

        state.sessionId = data.session_id;
        state.active = true;
        state.startTime = Date.now();
        state.audioStatus = data.audio_status || state.audioStatus;

        // Mostrar pantalla de llamada
        els.startScreen.classList.add('hidden');
        els.callScreen.classList.remove('hidden');

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
        alert('Error al iniciar la llamada. Verifica que el servidor esté corriendo.');
    }
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

        addSystemMessage('📵 Llamada terminada por el usuario');
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

    if (result && result.indicadores && result.indicadores.length > 0) {
        addSystemMessage('📋 Resumen de indicadores recopilados:');
        result.indicadores.forEach(ind => addIndicatorCard(ind));
    }

    addSystemMessage(`⏱️ Duración total: ${formatTime(getElapsedSeconds())}`);
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
    // Si Whisper NO está activo en el servidor y el navegador soporta Web Speech API,
    // usamos reconocimiento de voz directo en español (es-MX).
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!state.audioStatus.whisper && SpeechRec) {
        startBrowserSpeechRecognition(SpeechRec);
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


function startBrowserSpeechRecognition(SpeechRec) {
    try {
        const recognition = new SpeechRec();
        recognition.lang = 'es-MX';
        recognition.interimResults = true;
        recognition.continuous = true;

        state.speechTranscript = '';
        state.speechRecognition = recognition;

        recognition.onresult = (event) => {
            let fullText = '';
            for (let i = 0; i < event.results.length; i++) {
                fullText += event.results[i][0].transcript + ' ';
            }
            state.speechTranscript = fullText.trim();
            els.callStatus.textContent = `🎙️ "${state.speechTranscript}"`;
        };

        recognition.onerror = (event) => {
            console.warn('SpeechRecognition error:', event.error);
            if (event.error === 'not-allowed') {
                addSystemMessage('⚠️ Permiso de micrófono denegado. Usa el modo texto.');
            }
            setRecordingUI(false, 'En llamada...');
        };

        recognition.onend = async () => {
            const finalText = state.speechTranscript.trim();
            state.speechRecognition = null;
            setRecordingUI(false, 'En llamada...');

            if (finalText && state.active) {
                addMessage('atacante', `🎤 "${finalText}"`);
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
            addSystemMessage(`⚠️ ${data.error}`);
            return;
        }

        const result = data.result;

        if (audio) {
            if (data.transcripcion_usuario) {
                replaceLastAtacanteMessage(`🎤 "${data.transcripcion_usuario}"`);
            } else {
                replaceLastAtacanteMessage('🎤 (Audio sin transcripción — usa el modo texto)');
            }
        }

        // Mostrar respuesta de Lupita y reproducir su voz de inmediato
        addMessage('lupita', result.respuesta_texto, result.ultima_intencion);
        playLupitaVoice(result, data.tts_audio_b64);

        // Mostrar indicadores nuevos
        if (result.indicadores && result.indicadores.length > 0) {
            result.indicadores.forEach(ind => {
                if (!document.querySelector(`[data-indicator-id="${ind.id}"]`)) {
                    addIndicatorCard(ind);
                }
            });
        }

        // Verificar fin de llamada
        if (result.status !== 'active') {
            const statusMsg = {
                'timeout': '⏱️ Llamada terminada automáticamente (tiempo límite)',
                'completed': '✅ Llamada completada',
                'user_hangup': '📵 Llamada terminada por el usuario',
            };
            addSystemMessage(statusMsg[result.status] || `Estado: ${result.status}`);
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

    let html = `<span class="text">${escapeHtml(text)}</span>`;
    if (intent) {
        html += `<div class="meta"><span class="intent-tag">${intent}</span></div>`;
    }

    div.innerHTML = html;
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


function addIndicatorCard(indicator) {
    const div = document.createElement('div');
    div.className = 'indicator-card';
    div.setAttribute('data-indicator-id', indicator.id);

    const dvIcon = indicator.digito_verificador_ok === true ? '✅'
        : indicator.digito_verificador_ok === false ? '❌' : '⏳';

    const confClass = indicator.confianza === 'alta' ? 'alta'
        : indicator.confianza === 'media' ? 'media' : 'baja';

    div.innerHTML = `
        <div class="label">📋 ${indicator.tipo.toUpperCase()} detectada</div>
        <div class="value">${escapeHtml(indicator.valor_enmascarado || indicator.valor)}</div>
        <span class="conf ${confClass}">${indicator.confianza}</span>
        <span style="margin-left: 8px; font-size: 11px; color: var(--text-muted)">
            DV: ${dvIcon} · Fuentes: ${indicator.fuentes ? indicator.fuentes.length : 0}
            ${indicator.fuentes && indicator.fuentes.length <= 1 ? ' ⚠️ fuente única' : ''}
        </span>
    `;

    els.chatContainer.appendChild(div);
    scrollToBottom();
}


function replaceLastAtacanteMessage(newText) {
    const messages = els.chatContainer.querySelectorAll('.message.atacante');
    if (messages.length > 0) {
        const last = messages[messages.length - 1];
        const textSpan = last.querySelector('.text');
        if (textSpan) textSpan.textContent = newText;
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
        el.className = `badge ${on ? 'on' : 'off'}`;
    };

    const hasBrowserSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    const hasBrowserTTS = 'speechSynthesis' in window;

    set(els.badgeMic, status.microfono);
    set(els.badgeWhisper, status.whisper || hasBrowserSpeech);
    set(els.badgePiper, status.piper || hasBrowserTTS);

    if (!status.whisper && hasBrowserSpeech) {
        els.badgeWhisper.textContent = '🗣 Voz Web';
    }
    if (!status.piper && hasBrowserTTS) {
        els.badgePiper.textContent = '🔊 Voz Lupita';
    }
}


function scrollToBottom() {
    requestAnimationFrame(() => {
        els.chatContainer.scrollTop = els.chatContainer.scrollHeight;
    });
}


function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
