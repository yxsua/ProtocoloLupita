# Monitor de teléfono: especificación

## 1. Objetivo

Una página web que muestra, en tiempo real, los mensajes, SMS y llamadas que llegan a teléfonos Android propios, indicando de qué aplicación viene cada uno. Se usa solo con dispositivos propios y con el consentimiento expreso de sus usuarios.

Flujo: teléfono Android (servicio de escucha de notificaciones) → `POST /api/eventos` → servidor FastAPI → WebSocket → página web.

## 2. Aislamiento (regla principal)

- Todo vive en `/monitor_telefono`. No se modifica, importa ni depende nada de `/app` ni de la voz de Lupita (Whisper, Piper).
- Entorno propio: `requirements.txt` dentro de `server/`, puerto por defecto **8100**.
- Se puede leer `/app` solo para confirmar que no hay conflictos de nombres o puertos.
- Documentar, sin implementar, un posible punto de integración futuro con Lupita (por ejemplo, que Lupita lea eventos por la API).

## 3. Estructura

```
monitor_telefono/
  ESPECIFICACION.md
  README.md
  .env.example
  .gitignore
  server/      FastAPI + Jinja2 + SQLite
    app/ (main.py, db.py, auth.py, hub.py, routes/, templates/, static/)
    tests/
    requirements.txt, run.ps1, run.sh
  android/     Proyecto Kotlin completo, abrible en Android Studio
  scripts/     simulador de teléfono
  docs/        GUIA_INSTALACION.md, AVISO_PRIVACIDAD.md, INTEGRACION_LUPITA.md
```

## 4. Servidor

### 4.1 Evento

| Campo | Notas |
|---|---|
| `id_evento` | UUID. Opcional: si falta, el servidor lo genera como hash de dispositivo+app+fecha+texto |
| `dispositivo` | Se toma del token, no del cuerpo |
| `tipo` | `notificacion` (por defecto), `sms`, `llamada` |
| `app` | Paquete Android, por ejemplo `com.whatsapp` |
| `remitente`, `texto` | Con límite de longitud (256 y 4000) |
| `direccion` | `entrante`, `saliente`, `perdida` (solo llamadas) |
| `duracion_s` | Solo llamadas |
| `fecha` | UTC. Por defecto, la hora actual |

### 4.2 Persistencia

- SQLite con la librería estándar (`sqlite3`), modo WAL, llamadas desde endpoints asíncronos mediante `run_in_threadpool`. Sin ORMs.
- Índices por fecha, dispositivo y app. `id_evento` único: un duplicado responde 200 y no se guarda otra vez.
- Retención: `RETENCION_DIAS` (por defecto 30). Limpieza al arrancar y cada 24 h.
- Tabla `dispositivos`: id, nombre, hash del token (SHA-256 de un token aleatorio de 32 bytes), fecha de alta, último contacto, estado (`activo` o `revocado`). El token se muestra una sola vez al crear el dispositivo.

### 4.3 API

- `POST /api/eventos`: autenticación de dispositivo. Acepta el token en `X-Device-Key`, en `Authorization: Bearer` o en `?key=` (para apps reenviadoras de terceros; el parámetro no debe quedar en los logs). Acepta JSON o formulario. Acepta alias de campos: `from`/`sender`/`number` → `remitente`; `message`/`body`/`content` → `texto`; `package`/`app_name` → `app`. Si el cuerpo no es JSON válido, no se rechaza: se guarda el cuerpo crudo como `texto`. Responde 201. Límite de ritmo por dispositivo.
- `GET /api/eventos`: requiere sesión. Filtros: dispositivo, app, tipo, texto, desde, hasta. Paginación por cursor.
- `WS /ws/eventos`: requiere sesión y verifica el header `Origin`. Envía solo eventos nuevos; el historial se pide por la API REST.
- `GET /api/salud`: sin datos sensibles.

### 4.4 Interfaz web

- Login con contraseña de `MONITOR_PASSWORD`. Si no está definida, el servidor no arranca y explica por qué. Cookie de sesión firmada con `SECRET_KEY`, `HttpOnly`, `SameSite=Strict`. Token CSRF en los formularios que modifican datos.
- JS y CSS en archivos estáticos propios, para poder usar CSP estricta (`script-src 'self'`). Resto de cabeceras de seguridad.
- Todo contenido de mensajes se inserta con `textContent`, nunca como HTML.
- **Feed:** nombre amigable de la app (WhatsApp, Telegram, Mensajes, Teléfono…), remitente, texto, hora y dispositivo. Filtros por dispositivo, app y tipo; búsqueda; carga de historial al abrir; indicador de conexión; reconexión automática cada 2 s sin duplicar eventos.
- **Dispositivos:** alta, URL de ingesta lista para copiar con un ejemplo de JSON, último contacto, revocar, eliminar. "Eliminar dispositivo" y "Borrar datos" borran sus eventos de forma definitiva, con confirmación.
- Estado vacío con instrucciones. Modo claro y oscuro. Vista móvil. Teclado y foco visibles.

### 4.5 Dependencias permitidas

`fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `pydantic`, `itsdangerous` (sesión), `pytest`, `httpx` (pruebas). Cualquier otra, justificada en el README.

## 5. App Android (Kotlin, minSdk 26)

1. **Captura:** `NotificationListenerService`. Ignora las notificaciones propias, los resúmenes de grupo y las ongoing (reproductores, etc.). Para notificaciones `MessagingStyle` lee `EXTRA_MESSAGES` y envía solo los mensajes nuevos, porque las apps actualizan una misma notificación con cada mensaje. Solo envía las apps que la persona haya activado.
2. **Cola local:** cada evento se guarda en Room con su `id_evento` (UUID) y se envía con WorkManager, con reintentos de espera creciente. Sin red no se pierde nada; al volver se envía todo sin duplicados.
3. **Pantallas:**
   - *Consentimiento:* qué datos se comparten, con qué servidor y cómo revocar. Aceptación expresa antes de continuar.
   - *Configuración:* URL del servidor, token, nombre del dispositivo, botón "Probar conexión". Token guardado de forma segura (Android Keystore o equivalente vigente).
   - *Permisos:* acceso a notificaciones, exclusión de batería y aviso de "Permitir ajustes restringidos" (Android 13+, apps fuera de Google Play) con instrucciones paso a paso.
   - *Apps a compartir:* lista con interruptores. Por defecto, ninguna.
   - *Estado:* conexión, eventos pendientes, últimos eventos enviados, botón de pausa y botón de borrar configuración y cola.
4. **Indicador permanente** visible mientras el monitoreo esté activo (notificación ongoing de la propia app). Todo lo que se envía debe poder verse en la pantalla de estado.
5. Si el sistema desconecta el servicio de escucha, llamar a `requestRebind`.
6. **HTTPS** en producción. HTTP en claro solo en el build de depuración, mediante `networkSecurityConfig`, para red local.
7. **Llamadas (fase opcional, solo si no complica lo demás):** permisos `READ_PHONE_STATE` y `READ_CALL_LOG` pedidos únicamente si la persona los activa; envía `tipo=llamada` con dirección y duración. Nunca se graba audio.

## 6. Pruebas

**Servidor (pytest):** login requerido; token inválido o revocado → 401; idempotencia; alias de campos y cuerpo malformado; filtros; paginación; retención; WebSocket en vivo con sesión y rechazo sin sesión; borrado de datos.

**Simulador (`scripts/simular_telefono.py`):** envía eventos de prueba a la API con un token (mensajes con comillas, saltos de línea, emojis y duplicados incluidos).

**Android:** pruebas unitarias de la cola y de la lógica de deduplicación.

## 7. Documentación

- `GUIA_INSTALACION.md`: arrancar el servidor (Windows PowerShell y Linux/macOS), regla de firewall, registrar un teléfono, compilar e instalar el APK, probar en la misma Wi-Fi y acceder desde fuera de casa (recomendar Tailscale; explicar la alternativa de proxy con HTTPS).
- `AVISO_PRIVACIDAD.md`: borrador (datos tratados, finalidad, retención, revocación, borrado), pensado para la LFPDPPP de México. Indicar que es un borrador y no sustituye asesoría legal.
- `INTEGRACION_LUPITA.md`: idea futura, sin implementar.
- `README.md`: resumen, comandos exactos y tabla de variables de entorno (`MONITOR_PASSWORD`, `SECRET_KEY`, `RETENCION_DIAS`, `PUERTO`).

## 8. Restricciones

- No grabar audio de llamadas ni capturar nada fuera de los campos descritos. Sin funciones ocultas.
- Nada de claves en el código ni en el repo. `.env.example` con valores vacíos. `.gitignore` para `.env`, la base de datos y los artefactos de Android.
- Decisiones razonables sin preguntar por cada detalle; documentarlas en el README. Detenerse solo ante un bloqueo real.
- Decir con claridad lo que se verificó y lo que no. No afirmar que la app Android compila si no se pudo compilar.

## 9. Fases y criterios de terminado

**Fase 1: servidor.** `pytest` pasa. Arranco el servidor, entro con la contraseña, registro un dispositivo, el simulador envía eventos y aparecen al instante en el feed, con filtros y búsqueda, y siguen ahí tras reiniciar el servidor.

**Fase 2: app Android.** El proyecto compila con `./gradlew assembleDebug` (o se indica claramente que no se pudo verificar). Un teléfono real envía una notificación y aparece en el feed.

**Fase 3: cierre.** Documentación completa, revisión de seguridad (secretos, CSP, CSRF, logs sin tokens), `git status` confirma que nada cambió fuera de `/monitor_telefono`, y un resumen final con archivos creados, qué se verificó, qué no, y los pasos manuales pendientes.
