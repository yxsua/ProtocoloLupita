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
    voicePlayer.stop();
    voicePlayer.unlockProfile();
    state.mode = 'manual';
    state.botRunning = false;

    const form = new FormData();
    form.append('max_duration', maxDur);

    try {
        const avatarId = els.cfgAvatar.value || 'lupita';
        const lockedVoiceProfile = await lockCallIdentity(avatarId);
        form.append('locked_avatar', avatarId);
        form.append('locked_voice_profile', JSON.stringify(lockedVoiceProfile));
        const res = await fetch('/voice/start', { method: 'POST', body: form });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.error || 'No se pudo iniciar la llamada.');

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
        els.endPanel.classList.add('hidden');
        setModeControls();
        els.chatContainer.replaceChildren();
        els.clabeSummary.classList.add('hidden');

        // Actualizar badges
        updateBadges(state.audioStatus);

        // Agregar saludo de Lupita y reproducir su voz
        addMessage('lupita', data.result.respuesta_texto, data.result.ultima_intencion);
        startTimer();
        await playLupitaVoice(data.result, data.tts_audio_b64);
        els.textInput.focus();

    } catch (err) {
        console.error('Error iniciando llamada:', err);
        state.active = false;
        state.lockedAvatar = null;
        releaseVoiceLock();
        alert('Error al iniciar la llamada. Verifica que el servidor esté corriendo.');
    } finally {
        state.starting = false;
    }
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

        addSystemMessage('📵 Llamada terminada por el usuario');
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
    els.btnStopBot.disabled = true;

    if (result && result.indicadores && result.indicadores.length > 0) {
        addSystemMessage('📋 Resumen de indicadores recopilados:');
        result.indicadores.forEach(ind => addIndicatorCard(ind));
    }
    addSystemMessage(`⏱️ Duración total: ${formatTime(getElapsedSeconds())}`);
    els.endSummary.textContent = state.mode === 'bot'
        ? 'Simulación terminada'
        : 'Llamada finalizada';
    els.endPanel.classList.remove('hidden');
}

function selectStartMode(mode) {
    const bot = mode === 'bot';
    els.manualStartPanel.classList.toggle('hidden', bot);
    els.botStartPanel.classList.toggle('hidden', !bot);
    els.tabManual.classList.toggle('selected', !bot);
    els.tabBot.classList.toggle('selected', bot);
    els.tabManual.setAttribute('aria-selected', String(!bot));
    els.tabBot.setAttribute('aria-selected', String(bot));
}

function setModeControls() {
    const isBot = state.mode === 'bot';
    els.botControls.classList.toggle('hidden', !isBot);
    document.querySelector('.input-bar').classList.toggle('hidden', isBot);
    els.btnHangup.classList.toggle('hidden', isBot);
    els.callStatus.textContent = isBot
        ? 'Simulación educativa continua'
        : 'En llamada...';
}

async function startBotSimulation() {
    if (state.active || state.starting) return;
    state.starting = true;
    state.generation += 1;
    const maxDuration = Math.max(30, Math.min(300, parseInt(els.cfgMaxDuration.value, 10) || 180));
    const maxTurns = Math.max(1, Math.min(6, parseInt(els.cfgBotTurns.value, 10) || 5));
    const form = new FormData();
    form.append('scenario_id', els.cfgScenario.value || 'E01');
    form.append('max_turns', String(maxTurns));
    form.append('max_duration', String(maxDuration));

    try {
        voicePlayer.stop();
        voicePlayer.unlockProfile();
        const avatarId = els.cfgAvatar.value || 'lupita';
        const lockedVoiceProfile = await lockCallIdentity(avatarId);
        form.append('locked_avatar', avatarId);
        form.append('locked_voice_profile', JSON.stringify(lockedVoiceProfile));
        const res = await fetch('/voice/bot/start', { method: 'POST', body: form });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.error || 'No se pudo iniciar la simulación.');

        state.mode = 'bot';
        state.lockedAvatar = data.result.locked_avatar || avatarId;
        state.botSessionId = data.bot_session_id;
        state.botTurnIndex = data.turn_index;
        state.botMaxTurns = data.max_turns;
        state.botCanAdvance = data.can_advance;
        state.maxDuration = maxDuration;
        state.audioStatus = data.audio_status || state.audioStatus;
        state.active = true;
        state.botRunning = true;
        state.startTime = Date.now();
        els.startScreen.classList.add('hidden');
        els.callScreen.classList.remove('hidden');
        els.endPanel.classList.add('hidden');
        els.chatContainer.replaceChildren();
        els.clabeSummary.classList.add('hidden');
        updateBadges(state.audioStatus);
        setModeControls();
        addMessage('lupita', data.result.respuesta_texto, data.result.ultima_intencion);
        startTimer();
        await playLupitaVoice(data.result, data.tts_audio_b64);
        updateBotControls();
        if (state.active && state.botCanAdvance) void runBotTurns();
    } catch (err) {
        console.error('Error iniciando simulación:', err);
        state.active = false;
        state.lockedAvatar = null;
        releaseVoiceLock();
        alert(err.message || 'Error al iniciar la simulación.');
    } finally {
        state.starting = false;
    }
}

async function runBotTurns() {
    const generation = state.generation;
    while (generation === state.generation && state.active && state.botRunning && state.botCanAdvance) {
        await delay(900);
        if (!state.active || !state.botRunning) return;

        try {
            const form = new FormData();
            form.append('bot_session_id', state.botSessionId);
            const res = await fetch('/voice/bot/next', { method: 'POST', body: form });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.error || 'No se pudo avanzar la simulación.');
            if (generation !== state.generation || !state.active || !state.botRunning) return;

            if (data.attacker_text) {
                addMessage('atacante', data.attacker_text);
                await voicePlayer.say(data.attacker_text, 'atacante');
            }
            if (generation !== state.generation || !state.active || !state.botRunning) return;

            if (data.result && data.result.respuesta_texto) {
                addMessage('lupita', data.result.respuesta_texto, data.result.ultima_intencion);
                await playLupitaVoice(data.result, data.tts_audio_b64);
                showIndicators(data.result);
            }
            if (generation !== state.generation) return;

            state.botTurnIndex = data.turn_index;
            state.botCanAdvance = data.can_advance;
            updateBotControls();
            if (data.result && data.result.status !== 'active') {
                addSystemMessage('Simulación terminada por el límite configurado.');
                state.botSessionId = null;
                endCall(data.result);
                return;
            }
            if (state.botCanAdvance) await delay(750);
        } catch (err) {
            if (generation !== state.generation) return;
            console.error('Error durante la simulación:', err);
            addSystemMessage(`⚠️ ${err.message || 'Error durante la simulación.'}`);
            await stopBotSimulation();
            return;
        }
    }

    if (generation === state.generation && state.active && state.botRunning) {
        addSystemMessage('Simulación terminada por el límite configurado.');
        endCall(null);
    }
}

function updateBotControls() {
    els.botTurnCount.textContent = `Turno ${state.botTurnIndex} / ${state.botMaxTurns}`;
}

async function stopBotSimulation() {
    if (!state.botSessionId) {
        endCall(null);
        return;
    }
    state.active = false;
    state.botRunning = false;
    state.botCanAdvance = false;
    voicePlayer.stop();
    setSpeaking('lupita', false);
    stopTimer();
    const form = new FormData();
    form.append('bot_session_id', state.botSessionId);
    try {
        const res = await fetch('/voice/bot/stop', { method: 'POST', body: form });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'No se pudo detener la simulación.');
        state.botSessionId = null;
        addSystemMessage('Simulación detenida por el usuario.');
        endCall(data.result);
    } catch (err) {
        console.error('Error deteniendo simulación:', err);
        addSystemMessage(`⚠️ ${err.message || 'No se pudo detener la simulación en el servidor.'}`);
        endCall(null);
    }
}

async function recallCall() {
    const previousMode = state.mode;
    state.generation += 1;
    state.active = false;
    state.botRunning = false;
    voicePlayer.stop();
    stopRecording();
    stopMicMeter();
    stopTimer();

    if (state.sessionId) {
        const form = new FormData();
        form.append('session_id', state.sessionId);
        try {
            await fetch('/voice/hangup', { method: 'POST', body: form });
        } catch (err) {
            console.warn('No se pudo cerrar la sesión anterior:', err);
        }
    }
    if (state.botSessionId) {
        const form = new FormData();
        form.append('bot_session_id', state.botSessionId);
        try {
            await fetch('/voice/bot/stop', { method: 'POST', body: form });
        } catch (err) {
            console.warn('No se pudo cerrar la simulación anterior:', err);
        }
    }

    state.sessionId = null;
    state.botSessionId = null;
    state.processing = false;
    state.playbackBusy = false;
    state.recording = false;
    state.audioChunks = [];
    state.botTurnIndex = 0;
    state.botCanAdvance = false;
    state.startTime = null;
    els.processing.classList.remove('active');
    els.micMeterWrap.classList.add('hidden');
    els.chatContainer.replaceChildren();
    els.endPanel.classList.add('hidden');
    els.callScreen.classList.add('hidden');
    els.startScreen.classList.remove('hidden');
    els.textInput.disabled = false;
    els.btnSend.disabled = false;
    els.btnMic.disabled = false;
    els.btnHangup.disabled = false;
    els.btnStopBot.disabled = false;
    selectStartMode(previousMode);

    if (previousMode === 'bot') await startBotSimulation();
    else await startCall();
}

async function exitToMain() {
    state.generation += 1;
    state.active = false;
    state.botRunning = false;
    voicePlayer.stop();
    releaseVoiceLock();
    stopRecording();
    stopMicMeter();
    stopTimer();
    if (state.sessionId) {
        const form = new FormData();
        form.append('session_id', state.sessionId);
        try {
            await fetch('/voice/hangup', { method: 'POST', body: form, keepalive: true });
        } catch (err) {
            console.warn('No se pudo cerrar la llamada antes de salir:', err);
        }
    }
    if (state.botSessionId) {
        const form = new FormData();
        form.append('bot_session_id', state.botSessionId);
        try {
            await fetch('/voice/bot/stop', { method: 'POST', body: form, keepalive: true });
        } catch (err) {
            console.warn('No se pudo detener el bot antes de salir:', err);
        }
    }
    window.location.assign('/');
}

function updateInputControls() {
    const disabled = !state.active || state.processing || state.playbackBusy || state.mode === 'bot';
    els.textInput.disabled = disabled;
    els.btnSend.disabled = disabled;
    els.btnMic.disabled = disabled;
}

function setProcessing(active, message = '') {
    els.processing.classList.toggle('active', active);
    if (message) els.processingText.textContent = message;
    updateInputControls();
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
    // Si Whisper NO está activo en el servidor y el navegador soporta Web Speech API,
    // usamos reconocimiento de voz directo en español (es-MX).
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!state.audioStatus.whisper && SpeechRec) {
        startBrowserSpeechRecognition(SpeechRec);
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
        if (state.audioStream) {
            state.audioStream.getTracks().forEach(track => track.stop());
            state.audioStream = null;
        }
        stopMicMeter();
        setRecordingUI(false, 'En llamada...');
        addSystemMessage(err && err.name === 'NotAllowedError'
            ? '⚠️ Permiso de micrófono denegado. Puedes escribir tu mensaje.'
            : '⚠️ No se pudo acceder al micrófono. Puedes escribir tu mensaje.');
    }
}


function startBrowserSpeechRecognition(SpeechRec) {
    try {
        const recordingGeneration = state.generation;
        const recognition = new SpeechRec();
        recognition.lang = 'es-MX';
        recognition.interimResults = true;
        recognition.continuous = true;

        state.speechTranscript = '';
        state.speechRecognition = recognition;

        recognition.onresult = (event) => {
            if (recordingGeneration !== state.generation) return;
            let fullText = '';
            for (let i = 0; i < event.results.length; i++) {
                fullText += event.results[i][0].transcript + ' ';
            }
            state.speechTranscript = fullText.trim();
            els.callStatus.textContent = `🎙️ "${state.speechTranscript}"`;
        };

        recognition.onerror = (event) => {
            if (recordingGeneration !== state.generation) return;
            console.warn('SpeechRecognition error:', event.error);
            if (event.error === 'not-allowed') {
                addSystemMessage('⚠️ Permiso de micrófono denegado. Usa el modo texto.');
            }
            setRecordingUI(false, 'En llamada...');
        };

        recognition.onend = async () => {
            if (recordingGeneration !== state.generation) return;
            const finalText = state.speechTranscript.trim();
            state.speechRecognition = null;
            setRecordingUI(false, 'En llamada...');

            if (finalText && state.active && recordingGeneration === state.generation) {
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
        await playLupitaVoice(result, data.tts_audio_b64);

        // Mostrar indicadores nuevos
        showIndicators(result);

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
    div.dataset.speaker = role === 'lupita'
        ? `🧓 ${AVATAR_PROFILES[currentAvatarId()].name}`
        : `🎭 ${state.mode === 'bot' ? 'Bot Estafador' : 'Atacante'}`;

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

function showIndicators(result) {
    const indicators = result && Array.isArray(result.indicadores) ? result.indicadores : [];
    indicators.forEach(indicator => {
        const alreadyAdded = Array.from(document.querySelectorAll('.indicator-card'))
            .some(card => card.getAttribute('data-indicator-id') === indicator.id);
        if (!alreadyAdded) {
            addIndicatorCard(indicator);
        }
    });

    const clabe = indicators.filter(indicator => indicator.tipo === 'clabe').slice(-1)[0];
    if (clabe) {
        const valid = clabe.digito_verificador_ok === true;
        els.clabeSummary.textContent =
            `CLABE detectada: ${clabe.valor_enmascarado || '••••'} · ` +
            `${valid ? 'dígito verificador válido' : clabe.digito_verificador_ok === false ? 'dígito verificador inválido' : 'pendiente de validar'} · ` +
            `confianza ${clabe.confianza}`;
        els.clabeSummary.classList.remove('hidden');
    }
}


function replaceLastAtacanteMessage(newText) {
    const messages = els.chatContainer.querySelectorAll('.message.atacante');
    if (messages.length > 0) {
        const last = messages[messages.length - 1];
        const textSpan = last.querySelector('.text');
        if (textSpan) textSpan.textContent = newText;
    }
}


function updateBadges(status) {
    if (!status) return;

    const set = (el, on) => {
        el.className = `badge ${on ? 'on' : 'off'}`;
    };

    const hasBrowserSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    const hasBrowserTTS = 'speechSynthesis' in window;
    const voiceProvider = state.lockedVoiceProfile
        ? state.lockedVoiceProfile.citizen.provider
        : 'speechSynthesis';

    set(els.badgeMic, status.microfono);
    set(els.badgeWhisper, status.whisper || hasBrowserSpeech);
    set(els.badgePiper, voiceProvider === 'piper' ? status.piper : hasBrowserTTS);
    els.badgePiper.textContent = voiceProvider === 'piper'
        ? '🔊 Piper fijado'
        : '🔊 Voz fijada';

    if (!status.whisper && hasBrowserSpeech) {
        els.badgeWhisper.textContent = '🗣 Voz Web';
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
