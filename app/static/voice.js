/**
 * voice.js — Frontend de voz de Protocolo Lupita
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
    playbackBusy: false,
    startTime: null,
    maxDuration: 300,
    timerInterval: null,
    audioStatus: { microfono: true, whisper: false, piper: false },
    mode: 'manual',
    botSessionId: null,
    botTurnIndex: 0,
    botMaxTurns: 5,
    botCanAdvance: false,
    botRunning: false,
    micAudioContext: null,
    micAnalyser: null,
    micMeterFrame: null,
    micPeak: 0,
    micMeterAvailable: false,
    generation: 0,
    lockedAvatar: null,
    lockedVoiceProfile: null,
    starting: false,

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
    manualStartPanel: $('manualStartPanel'),
    botStartPanel: $('botStartPanel'),
    tabManual: $('tabManual'),
    tabBot: $('tabBot'),
    cfgScenario: $('cfgScenario'),
    cfgBotTurns: $('cfgBotTurns'),
    botControls: $('botControls'),
    botTurnCount: $('botTurnCount'),
    btnStopBot: $('btnStopBot'),
    speakingIndicator: $('speakingIndicator'),
    clabeSummary: $('clabeSummary'),
    micMeterWrap: $('micMeterWrap'),
    micMeter: $('micMeter'),
    micMeterLabel: $('micMeterLabel'),
    processingText: $('processingText'),
    endPanel: $('endPanel'),
    endSummary: $('endSummary'),
    btnRecall: $('btnRecall'),
    btnExit: $('btnExit'),
    cfgAvatar:     $('cfgAvatar'),
    avatarLockNotice: $('avatarLockNotice'),
    startAvatarName: $('startAvatarName'),
    startAvatarIcon: $('startAvatarIcon'),
    activeAvatarName: $('activeAvatarName'),
    activeAvatarIcon: $('activeAvatarIcon'),
};

const AVATAR_PROFILES = Object.freeze({
    lupita: Object.freeze({
        name: 'Doña Lupita', icon: '🧓', voiceKind: 'female',
        voicePreference: /sabina|dalia|paulina|google espa[nñ]ol/i, rate: 0.88, pitch: 1.0,
    }),
    ramiro: Object.freeze({
        name: 'Don Ramiro', icon: '👴', voiceKind: 'male',
        voicePreference: /jorge|raul|diego|miguel|pablo|antonio/i, rate: 0.92, pitch: 0.9,
    }),
    carmen: Object.freeze({
        name: 'Sra. Carmen', icon: '👵', voiceKind: 'female',
        voicePreference: /helena|laura|monica|lucia|sofia|elena/i, rate: 0.88, pitch: 1.02,
    }),
    hector: Object.freeze({
        name: 'Profe Héctor', icon: '👨‍🏫', voiceKind: 'male',
        voicePreference: /pablo|diego|miguel|jorge|raul|antonio/i, rate: 0.96, pitch: 0.94,
    }),
});

function currentAvatarId() {
    return state.lockedAvatar || els.cfgAvatar.value || 'lupita';
}

function updateAvatarIdentity(avatarId = currentAvatarId(), updateActive = true) {
    const avatar = AVATAR_PROFILES[avatarId] || AVATAR_PROFILES.lupita;
    els.startAvatarName.textContent = avatar.name;
    els.startAvatarIcon.textContent = avatar.icon;
    if (updateActive) {
        els.activeAvatarName.textContent = avatar.name;
        els.activeAvatarIcon.textContent = avatar.icon;
    }
}

function setAvatarSelectorLocked(locked) {
    els.cfgAvatar.disabled = locked;
    els.avatarLockNotice.classList.toggle('hidden', !locked);
}

function localeRank(voice) {
    const lang = voice.lang.toLowerCase();
    if (lang.startsWith('es-mx')) return 0;
    if (lang.startsWith('es-419')) return 1;
    if (lang.startsWith('es-es')) return 2;
    return 3;
}

async function getSpanishVoicesForLock() {
    if (!('speechSynthesis' in window)) return [];
    const synthesis = window.speechSynthesis;
    const current = synthesis.getVoices();
    if (current.some(voice => voice.lang.toLowerCase().startsWith('es'))) return current;

    return new Promise(resolve => {
        let settled = false;
        const finish = () => {
            if (settled) return;
            settled = true;
            clearTimeout(timeout);
            synthesis.removeEventListener('voiceschanged', finish);
            resolve(synthesis.getVoices());
        };
        const timeout = setTimeout(finish, 1200);
        synthesis.addEventListener('voiceschanged', finish, { once: true });
    });
}

function selectVoiceForLock(voices, voiceKind, excludedVoiceURI = '', preferredNames = null) {
    const spanish = voices.filter(voice => voice.lang.toLowerCase().startsWith('es'));
    const genderPattern = voiceKind === 'female'
        ? /female|mujer|femenin|sabina|dalia|paulina|helena|laura|monica|lucia|sofia|elena|google espa[nñ]ol/i
        : /male|hombre|masculin|jorge|raul|diego|miguel|pablo|antonio/i;
    const matchingGender = spanish.filter(voice => genderPattern.test(voice.name));
    const matchingName = matchingGender.filter(voice => preferredNames && preferredNames.test(voice.name));
    const candidates = (matchingName.length ? matchingName : matchingGender.length ? matchingGender : spanish)
        .slice()
        .sort((a, b) => localeRank(a) - localeRank(b));
    return candidates.find(voice => voice.voiceURI !== excludedVoiceURI) || candidates[0] || null;
}

async function lockCallIdentity(avatarId) {
    const avatar = AVATAR_PROFILES[avatarId] || AVATAR_PROFILES.lupita;
    const voices = await getSpanishVoicesForLock();
    const citizenVoice = selectVoiceForLock(
        voices,
        avatar.voiceKind,
        '',
        avatar.voicePreference,
    );
    const attackerVoice = selectVoiceForLock(
        voices,
        'male',
        citizenVoice ? citizenVoice.voiceURI : '',
    );
    const voiceProfile = Object.freeze({
        citizen: Object.freeze({
            provider: 'speechSynthesis',
            voice_uri: citizenVoice ? citizenVoice.voiceURI : '',
            voice_name: citizenVoice ? citizenVoice.name : '',
            lang: citizenVoice ? citizenVoice.lang : 'es-MX',
            rate: avatar.rate,
            pitch: avatar.pitch,
        }),
        attacker: Object.freeze({
            provider: 'speechSynthesis',
            voice_uri: attackerVoice ? attackerVoice.voiceURI : '',
            voice_name: attackerVoice ? attackerVoice.name : '',
            lang: attackerVoice ? attackerVoice.lang : 'es-MX',
            rate: 1.08,
            pitch: 0.88,
        }),
    });

    state.lockedAvatar = avatarId;
    state.lockedVoiceProfile = voiceProfile;
    voicePlayer.lockProfile(voiceProfile, {
        citizen: citizenVoice,
        attacker: attackerVoice,
    });
    updateAvatarIdentity(avatarId);
    setAvatarSelectorLocked(true);
    return voiceProfile;
}

function releaseVoiceLock() {
    voicePlayer.unlockProfile();
    state.lockedVoiceProfile = null;
    setAvatarSelectorLocked(false);
}

els.cfgAvatar.addEventListener('change', () => {
    updateAvatarIdentity(
        els.cfgAvatar.value,
        els.callScreen.classList.contains('hidden'),
    );
});
updateAvatarIdentity(els.cfgAvatar.value || 'lupita');


// ═══════════════════════════════════════════════════════════════════════
//  1. INICIAR / TERMINAR LLAMADA
// ═══════════════════════════════════════════════════════════════════════

async function startCall() {
    if (state.active || state.starting) return;
    state.starting = true;
    state.generation += 1;
    const maxDur = parseInt(els.cfgMaxDuration.value) || 300;
    state.maxDuration = maxDur;
    els.btnStart.disabled = true;
    $('incomingNotice').textContent = 'Contestando la llamada…';

    const form = new FormData();
    form.append('max_duration', maxDur);

    try {
        const avatarId = els.cfgAvatar.value || 'lupita';
        const lockedVoiceProfile = await lockCallIdentity(avatarId);
        form.append('locked_avatar', avatarId);
        form.append('locked_voice_profile', JSON.stringify(lockedVoiceProfile));
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
        state.lockedAvatar = data.result.locked_avatar || avatarId;
        state.mode = 'manual';
        state.botSessionId = null;
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
        startTimer();
        await playLupitaVoice(data.result, data.tts_audio_b64);
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
    if (state.mode === 'bot') {
        await stopBotSimulation();
        return;
    }
    if (!state.sessionId || !state.active) return;

    state.active = false;
    stopRecording();
    voicePlayer.stop();
    setSpeaking('lupita', false);

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
    state.botRunning = false;
    state.sessionId = null;
    state.botSessionId = null;
    stopTimer();
    stopRecording();
    voicePlayer.stop();
    releaseVoiceLock();
    setSpeaking('lupita', false);
    stopMicMeter();

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
    if (!text || !state.active || state.processing || state.playbackBusy) return;

    els.textInput.value = '';
    addMessage('atacante', text);

    await processInput({ text });
}


// ═══════════════════════════════════════════════════════════════════════
//  3. MICRÓFONO — Whisper servidor o Web Speech API del navegador
// ═══════════════════════════════════════════════════════════════════════

async function toggleMic() {
    if (state.processing || state.playbackBusy || !state.active) return;
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
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            throw new Error('El navegador no soporta grabación de audio.');
        }
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });

        state.audioStream = stream;
        const recordingGeneration = state.generation;
        state.micPeak = 0;
        state.micMeterAvailable = false;
        startMicMeter(stream);
        stream.getAudioTracks().forEach(track => {
            track.addEventListener('ended', () => {
                if (recordingGeneration === state.generation && state.recording && state.active) {
                    addSystemMessage('⚠️ El micrófono se desconectó. Puedes continuar escribiendo.');
                    if (state.mediaRecorder && state.mediaRecorder.state === 'recording') {
                        state.mediaRecorder.stop();
                    }
                    setRecordingUI(false, 'En llamada...');
                }
            }, { once: true });
        });
        const recordingChunks = [];
        state.audioChunks = recordingChunks;

        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : 'audio/webm';

        state.mediaRecorder = new MediaRecorder(stream, { mimeType });

        state.mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) recordingChunks.push(e.data);
        };

        state.mediaRecorder.onstop = async () => {
            const blob = new Blob(recordingChunks, { type: mimeType });
            if (recordingGeneration === state.generation) stopMicMeter();
            try {
                if (!state.active || recordingGeneration !== state.generation) return;
                if (state.micMeterAvailable && state.micPeak < 0.004) {
                    addSystemMessage('⚠️ No se detectó voz. Intenta de nuevo o escribe tu mensaje.');
                    return;
                }
                els.callStatus.textContent = 'Procesando audio...';
                const wavBlob = await convertToWav(blob);
                addMessage('atacante', '🎤 (Audio enviado — transcribiendo...)');
                await processInput({ audio: wavBlob });
            } finally {
                recordingChunks.length = 0;
                if (state.audioChunks === recordingChunks) state.audioChunks = [];
                if (state.audioStream === stream) {
                    stream.getTracks().forEach(t => t.stop());
                    state.audioStream = null;
                } else {
                    stream.getTracks().forEach(t => t.stop());
                }
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
        const recordingGeneration = state.generation;
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
            if (recordingGeneration !== state.generation) return;
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
            if (recordingGeneration !== state.generation) return;
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
    if (!state.mediaRecorder || !state.recording) stopMicMeter();
    setRecordingUI(false, 'En llamada...');
}


function setRecordingUI(isRecording, statusText) {
    state.recording = isRecording;
    els.btnMic.classList.toggle('recording', isRecording);
    els.btnMic.textContent = isRecording ? '⏹ Soltar y enviar' : '🎤 Hablar';
    els.callStatus.textContent = statusText;
}

function startMicMeter(stream) {
    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        const context = new AudioContextClass();
        const analyser = context.createAnalyser();
        analyser.fftSize = 512;
        context.createMediaStreamSource(stream).connect(analyser);
        state.micAudioContext = context;
        state.micAnalyser = analyser;
        state.micMeterAvailable = true;
        els.micMeterWrap.classList.remove('hidden');
        els.micMeterLabel.textContent = 'Grabando — nivel de micrófono';
        const samples = new Float32Array(analyser.fftSize);
        const updateLevel = () => {
            if (!state.micAnalyser) return;
            analyser.getFloatTimeDomainData(samples);
            const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
            state.micPeak = Math.max(state.micPeak, rms);
            els.micMeter.value = Math.min(1, rms * 8);
            state.micMeterFrame = requestAnimationFrame(updateLevel);
        };
        updateLevel();
    } catch (err) {
        console.warn('No se pudo iniciar el medidor del micrófono:', err);
    }
}

function stopMicMeter() {
    if (state.micMeterFrame) cancelAnimationFrame(state.micMeterFrame);
    state.micMeterFrame = null;
    state.micAnalyser = null;
    els.micMeter.value = 0;
    els.micMeterWrap.classList.add('hidden');
    if (state.micAudioContext) {
        const context = state.micAudioContext;
        state.micAudioContext = null;
        context.close().catch(err => console.warn('Error cerrando AudioContext:', err));
    }
}


/**
 * Convierte audio blob (webm/opus) a WAV PCM 16-bit mono 16kHz.
 */
async function convertToWav(blob) {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });
        try {
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
            return new Blob([wavBuffer], { type: 'audio/wav' });
        } finally {
            await audioCtx.close();
        }

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

    const generation = state.generation;
    const sessionId = state.sessionId;
    state.processing = true;
    const citizenName = AVATAR_PROFILES[currentAvatarId()].name;
    setProcessing(true, audio ? 'Transcribiendo con Whisper...' : `${citizenName} está pensando...`);

    const form = new FormData();
    form.append('session_id', sessionId);

    if (audio) form.append('audio', audio, 'recording.wav');
    if (text) form.append('text', text);

    try {
        const res = await fetch('/voice/process', { method: 'POST', body: form });
        const data = await res.json();
        if (generation !== state.generation || !state.active) return;

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
        await playLupitaVoice(result, data.tts_audio_b64);

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
        if (generation === state.generation && state.active) {
            console.error('Error procesando:', err);
            addSystemMessage('⚠️ Error de comunicación con el servidor');
        }
    } finally {
        if (generation === state.generation) {
            state.processing = false;
            setProcessing(false);
        }
    }
}


// ═══════════════════════════════════════════════════════════════════════
//  5. AUDIO — Voz de Lupita (WAV pregrabado, Piper base64 o SpeechSynthesis)
// ═══════════════════════════════════════════════════════════════════════

function setSpeaking(role, active) {
    state.playbackBusy = active;
    const citizenName = AVATAR_PROFILES[currentAvatarId()].name;
    els.speakingIndicator.classList.toggle('hidden', !active);
    els.speakingIndicator.textContent = role === 'atacante'
        ? '🔊 Estafador hablando...'
        : `🔊 ${citizenName} hablando...`;
    if (active) {
        els.callStatus.textContent = role === 'atacante'
            ? 'Estafador hablando...'
            : `${citizenName} hablando...`;
    } else if (state.active) {
        els.callStatus.textContent = state.mode === 'bot'
            ? 'Simulación educativa continua'
            : 'En llamada...';
    }
    updateInputControls();
}

class VoicePlayer {
    constructor(audioElement) {
        this.audio = audioElement;
        this.queue = [];
        this.running = false;
        this.generation = 0;
        this.finishActive = null;
        this.lockedProfile = null;
        this.lockedVoices = Object.freeze({ citizen: null, attacker: null });
    }

    lockProfile(profile, voices) {
        this.lockedProfile = profile;
        this.lockedVoices = Object.freeze({
            citizen: voices.citizen || null,
            attacker: voices.attacker || null,
        });
    }

    unlockProfile() {
        this.lockedProfile = null;
        this.lockedVoices = Object.freeze({ citizen: null, attacker: null });
    }

    enqueue(play) {
        return new Promise(resolve => {
            this.queue.push({ play, resolve, generation: this.generation });
            void this.drain();
        });
    }

    async drain() {
        if (this.running) return;
        this.running = true;
        while (this.queue.length) {
            const item = this.queue.shift();
            if (item.generation === this.generation) {
                try {
                    await item.play();
                } catch (err) {
                    console.warn('Error reproduciendo audio:', err);
                }
            }
            item.resolve();
        }
        this.running = false;
    }

    say(text, role = 'lupita') {
        return this.enqueue(() => this.speak(text, role));
    }

    sayLupita(result, ttsAudioB64) {
        if (!result) return Promise.resolve();
        const text = result.tts_texto || result.respuesta_texto;
        return this.enqueue(async () => {
            if (this.lockedProfile && this.lockedProfile.citizen.provider === 'speechSynthesis') {
                await this.speak(text, 'lupita');
                return;
            }
            if (ttsAudioB64) {
                try {
                    const binary = atob(ttsAudioB64);
                    const bytes = new Uint8Array(binary.length);
                    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                    const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
                    try {
                        await this.playUrl(url, text);
                    } finally {
                        URL.revokeObjectURL(url);
                    }
                    return;
                } catch (err) {
                    console.warn('Audio de Piper inválido; se usará la voz del navegador.', err);
                }
            }
            if (result.audio_ref) {
                await this.playUrl(`/voice/audio/${encodeURIComponent(result.audio_ref)}`, text);
                return;
            }
            await this.speak(text, 'lupita');
        });
    }

    playRef(filename) {
        if (!filename) return Promise.resolve();
        return this.enqueue(() => this.playUrl(`/voice/audio/${encodeURIComponent(filename)}`, ''));
    }

    async playUrl(url, fallbackText) {
        const generation = this.generation;
        let failed = false;
        await new Promise(resolve => {
            let settled = false;
            let timeout;
            const finish = error => {
                if (settled) return;
                settled = true;
                failed = Boolean(error);
                clearTimeout(timeout);
                this.audio.onended = null;
                this.audio.onerror = null;
                if (this.finishActive === cancel) this.finishActive = null;
                setSpeaking('lupita', false);
                resolve();
            };
            const cancel = () => finish(true);
            this.finishActive = cancel;
            this.audio.pause();
            this.audio.onended = () => finish(false);
            this.audio.onerror = () => finish(true);
            this.audio.src = url;
            setSpeaking('lupita', true);
            timeout = setTimeout(cancel, 30000);
            try {
                Promise.resolve(this.audio.play()).catch(() => finish(true));
            } catch (_) {
                finish(true);
            }
        });
        if (failed && fallbackText && generation === this.generation) {
            await this.speak(fallbackText, 'lupita');
        }
    }

    async speak(text, role) {
        const prepared = prepareSpeechText(text);
        if (!prepared) return;
        if (!('speechSynthesis' in window)) {
            addSystemMessage('⚠️ SpeechSynthesis no está disponible en este navegador; se conserva el texto.');
            return;
        }
        await new Promise(resolve => {
            let settled = false;
            let timeout;
            const finish = () => {
                if (settled) return;
                settled = true;
                clearTimeout(timeout);
                if (this.finishActive === finish) this.finishActive = null;
                setSpeaking(role, false);
                resolve();
            };
            const utterance = new SpeechSynthesisUtterance(prepared);
            const speaker = role === 'atacante' ? 'attacker' : 'citizen';
            const profile = this.lockedProfile && this.lockedProfile[speaker];
            if (profile) {
                utterance.lang = profile.lang;
                utterance.voice = this.lockedVoices[speaker];
                utterance.rate = profile.rate;
                utterance.pitch = profile.pitch;
            } else {
                utterance.lang = 'es-MX';
                utterance.rate = role === 'atacante' ? 1.08 : 0.88;
                utterance.pitch = role === 'atacante' ? 0.88 : 1.0;
            }
            utterance.onend = finish;
            utterance.onerror = finish;
            const timeoutMs = Math.max(12000, Math.min(60000, prepared.length * 140 + 6000));
            timeout = setTimeout(() => {
                window.speechSynthesis.cancel();
                finish();
            }, timeoutMs);
            this.finishActive = () => {
                window.speechSynthesis.cancel();
                finish();
            };
            setSpeaking(role, true);
            try {
                window.speechSynthesis.speak(utterance);
            } catch (err) {
                console.warn('SpeechSynthesis no pudo iniciar:', err);
                finish();
            }
        });
    }

    stop() {
        this.generation += 1;
        this.queue.splice(0).forEach(item => item.resolve());
        if (this.finishActive) this.finishActive();
        this.finishActive = null;
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        this.audio.pause();
        this.audio.removeAttribute('src');
        this.audio.load();
        setSpeaking('lupita', false);
    }
}

function prepareSpeechText(text) {
    if (!text) return '';
    const digits = ['cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve'];
    return String(text)
        .replace(/\bCLABE\b/gi, 'clabe')
        .replace(/\b\d{4,}\b/g, value => value.split('').map(digit => digits[Number(digit)]).join(', '))
        .replace(/[;:]\s*/g, ', ')
        .replace(/\s+/g, ' ')
        .trim();
}

const voicePlayer = new VoicePlayer(els.audioPlayer);

function playLupitaVoice(result, ttsAudioB64) {
    return voicePlayer.sayLupita(result, ttsAudioB64);
}

function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
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
    const voiceProvider = state.lockedVoiceProfile
        ? state.lockedVoiceProfile.citizen.provider
        : 'speechSynthesis';

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

window.addEventListener('pagehide', () => {
    state.active = false;
    state.botRunning = false;
    voicePlayer.stop();
    stopRecording();
    if (state.audioStream) {
        state.audioStream.getTracks().forEach(track => track.stop());
        state.audioStream = null;
    }
    stopMicMeter();
});
