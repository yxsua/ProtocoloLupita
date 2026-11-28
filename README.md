# Protocolo Lupita

Prototipo local para demostrar prevención y análisis de intentos de fraude por llamada y SMS. Incluye un portal público para la ciudadanía y un panel privado para el equipo de gobierno. Las llamadas de demostración, los escenarios y la atribución son sintéticos; el analizador SMS también incluye un dataset de referencia. **Esta aplicación no marca ni recibe llamadas telefónicas reales, no envía reportes a autoridades y no acredita delitos**.

## Contenido

- [Qué incluye](#qué-incluye)
- [Requisitos](#requisitos)
- [Ejecutar en Windows](#ejecutar-en-windows)
- [Ejecutar en Linux o macOS](#ejecutar-en-linux-o-macos)
- [Ejecutar con Docker Compose](#ejecutar-con-docker-compose)
- [Recorrido de la demostración](#recorrido-de-la-demostración)
- [Aplicaciones y módulos](#aplicaciones-y-módulos)
- [Secciones y rutas](#secciones-y-rutas)
- [Configuración](#configuración)
- [Datos, almacenamiento y límites](#datos-almacenamiento-y-límites)
- [Bridge Android y monitor de teléfono](#bridge-android-y-monitor-de-teléfono)
- [Pruebas y documentación relacionada](#pruebas-y-documentación-relacionada)

## Qué incluye

La aplicación principal es un monolito modular construido con FastAPI, Jinja2, HTML, CSS y JavaScript, con SQLite para el historial local. No utiliza un framework JavaScript de frontend. Los módulos de vistas y API se conectan desde `app/main.py`.

La demo se puede presentar en dos pantallas conectadas a la misma instancia: el celular muestra una llamada entrante ficticia y el equipo muestra el dashboard gubernamental en vivo. Un escenario precargado produce ambos lados de la conversación y su transcripción; no se requiere micrófono. Al terminar o cancelar, el reporte queda consultable en **Reportes y métricas**.

## Requisitos

- Python 3.11 o posterior.
- [uv](https://docs.astral.sh/uv/) para crear el entorno e instalar dependencias.
- Para contenedores: Docker Desktop o Docker Engine con Docker Compose v2.
- Para la demo en dos dispositivos: ambos conectados a la misma red local y el firewall de la laptop permitiendo el puerto elegido en esa red.

## Ejecutar en Windows

Desde PowerShell, abre la carpeta raíz del proyecto:

```powershell
Copy-Item .env.example .env
notepad .env
```

Define un usuario y una contraseña de demostración en `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD`. Después instala dependencias e inicia el servidor:

```powershell
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Abre <http://127.0.0.1:8000>. La primera ejecución crea o inicializa las bases SQLite y carga la siembra sintética.

Para abrir la demo desde un celular conectado a la misma LAN, detén el servidor y vuelve a iniciarlo escuchando en las interfaces de red:

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --env-file .env
```

En el celular abre `http://<IP-local-de-la-laptop>:8000/gobierno/simulador`; en la laptop abre `http://<IP-local-de-la-laptop>:8000/gobierno`. Ingresa las credenciales del `.env` en ambos dispositivos. `localhost` en el celular apunta al propio celular, por eso se debe usar la IP local de la laptop.

## Ejecutar en Linux o macOS

Desde una terminal en la raíz del proyecto:

```sh
cp .env.example .env
# Edita .env y define GOV_PANEL_USERNAME y GOV_PANEL_PASSWORD.
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Para una demo por LAN usa `--host 0.0.0.0` y visita desde el segundo dispositivo `http://<IP-local-de-la-laptop>:8000`.

## Ejecutar con Docker Compose

Configura las credenciales y los parámetros del contenedor en `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Define `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD`, luego ejecuta:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Abre <http://127.0.0.1:8000>. Para una presentación por LAN, configura `APP_BIND_ADDRESS=0.0.0.0` en `.env` y aplica el cambio:

```powershell
docker compose up -d
```

Después abre `http://<IP-local-de-la-laptop>:8000` en el celular. Compose conserva las bases y el manifiesto local en el volumen `protocolo-lupita-data`. `docker compose down` conserva el volumen; `docker compose down -v` lo elimina junto con esos datos. La aplicación corre como usuario no privilegiado y con un worker.

## Recorrido de la demostración

1. En la laptop, entra al panel privado en `/gobierno` y deja visible **Llamada en vivo**.
2. En el celular, entra a `/gobierno/simulador`, selecciona un escenario de voz y pulsa **Contestar** cuando aparezca la llamada entrante simulada.
3. El escenario reproduce la voz sintética de la persona atacante y la respuesta de Doña Lupita. La transcripción se presenta en el simulador y se actualiza en el dashboard.
4. El dashboard muestra señales y atribución sintéticas, con los valores sensibles enmascarados. El estado no representa una confirmación oficial de fraude.
5. Deja terminar el escenario o pulsa **Cancelar llamada**. Abre **Reportes y métricas** → **Consultar** para recuperar el reporte cerrado y su transcripción saneada.

El flujo no solicita acceso al micrófono ni conecta con la red telefónica. La voz se genera localmente en el navegador con los clips y opciones locales disponibles. Si el navegador no reproduce voz, la transcripción permite completar la demostración. Solo se permite una llamada simulada activa por proceso; termina o cancela la sesión antes de iniciar otra.

## Aplicaciones y módulos

| Aplicación o módulo | Ubicación | Función |
|---|---|---|
| Portal ciudadano | `app/modules/citizen/` | Recibe reportes de llamadas o mensajes, sanea datos personales antes de analizarlos y orienta sobre siguientes pasos. |
| Analizador de SMS | `app/modules/sms/` | Analiza un SMS escrito por la persona, compara señales y dominios, y ofrece una bandeja con ejemplos sintéticos. Los enlaces no se abren. |
| Avisos públicos | `app/modules/dashboard/` y `app/modules/map/` | Presentan señales y agregados territoriales. Los resultados detallados y la API interna del dashboard requieren credenciales de Gobierno; el mapa público suprime grupos pequeños. |
| Siembra y atribución | `app/modules/planting/` | Crea lotes inmutables de bases SQLite ficticias, asigna un número trampa único por copia y permite atribuir señales recibidas. La administración, descarga y consulta de atribución requieren credenciales gubernamentales. |
| Voz y simulador | `app/modules/voice/` | Gestiona la llamada simulada, escenarios de conversación, transcripción saneada, respuestas de voz, cancelación y cierre del reporte. Requiere acceso gubernamental. |
| Panel gubernamental | `app/modules/government/` | Muestra la sesión en vivo, escenarios, reportes guardados y métricas. La autenticación local usa HTTP Basic. |
| Inteligencia y evidencia | `app/modules/intel/` y `app/modules/evidence/` | Extrae y correlaciona indicadores, agrupa campañas, calcula nivel de confianza y mantiene verificaciones/hash de evidencia. Sus endpoints están protegidos. |
| Eventos del teléfono | `app/modules/mensajes/` | Recibe bridge y relay del monitor Android, analiza textos con el motor SMS y ofrece feed en vivo, búsqueda y filtros en `/mensajes`. |
| Núcleo y escenarios | `app/core/` | Contiene esquemas compartidos, almacenamiento SQLite, registro y ejecución de escenarios de prueba, y configuración de la aplicación. |
| Telefonía real (no activa) | `app/modules/telephony/` | Hay código fuente de integración, pero su router no está montado en `app/main.py`; no forma parte del recorrido ejecutable de esta demo. |

## Secciones y rutas

| Ruta | Acceso | Descripción |
|---|---|---|
| `/` | Público | Portada de orientación y enlaces de la ciudadanía. |
| `/sms` | Público | Analizador de SMS y ejemplos. |
| `/citizen` | Público | Formulario para reportar una llamada o mensaje sospechoso. |
| `/dashboard` | Público | Avisos agregados para la ciudadanía. |
| `/gobierno` | Credenciales | Dashboard de actividad de llamadas en vivo. |
| `/gobierno/simulador` | Credenciales | GUI de llamada y escenarios precargados. |
| `/gobierno/reportes` | Credenciales | Historial consultable y métricas agregadas de los reportes. |
| `/gobierno/siembras` | Credenciales | Crear lotes sintéticos y descargar un ZIP de copias SQLite. |
| `/mensajes` | Credenciales | Feed de eventos recibidos desde un dispositivo de prueba. |
| `/planting` | Público | Explicación del mecanismo de atribución sintética. |
| `/docs` | API | Documentación interactiva de las rutas HTTP. |
| `/api/health` | Público | Estado del servidor y almacenamiento. |

API públicas destacadas: `POST /citizen/api/report`, `POST /sms/api/analyze`, `GET /api/public/alerts`, `GET /api/public/map` y `GET /citizen/api/map-aggregates`. Las rutas internas de voz, reportes, dashboard detallado, inteligencia, siembra y escenarios piden las credenciales de Gobierno.

### Lotes de copias sintéticas

En `/gobierno/siembras`, el equipo puede generar un lote con un identificador nuevo y de 1 a 50 copias. Cada archivo SQLite incluye registros de demostración y un solo número trampa único para esa copia. Los archivos no contienen información personal real; el ZIP incluye `LEEME.txt`, `lote.json` con hashes SHA-256 y una base por copia. El manifiesto descargable omite el número trampa y su relación con el identificador de copia.

Los lotes son inmutables: si un identificador ya existe, la aplicación lo rechaza para conservar las atribuciones históricas. Comparte con cada participante solo su archivo SQLite asignado; no distribuyas el ZIP completo ni el registro interno de atribución. El mapa privado entre número y copia permanece en `data/protocolo_lupita.sqlite3`, bajo control del servidor.

API administrativa (todas las rutas requieren autenticación de Gobierno):

- `GET /api/planting/batches`: lista identificadores, cantidad, fecha y hash sin números trampa.
- `POST /api/planting/batches`: recibe `{"seed_period":"2026-11-demo-01","total_copies":3}` y crea un lote nuevo.
- `GET /api/planting/batches/{seed_period}/download`: descarga el ZIP de ese lote.

Este flujo sirve para una demostración aislada. No conectes las copias ni el prototipo a bases reales; cualquier ejercicio con datos institucionales requiere un diseño y una autorización separados.

El bridge de eventos Android publica en `POST /api/eventos` con la cabecera `X-Device-Key`. La lectura de `GET /api/eventos`, la página `/mensajes` y el WebSocket `/ws/eventos` requieren autenticación gubernamental.

## Configuración

La aplicación lee `.env` al iniciar. `.env` está ignorado por Git; no agregues credenciales ni claves al repositorio.

| Variable | Para qué sirve | Valor de ejemplo para demo |
|---|---|---|
| `GOV_PANEL_USERNAME` | Usuario HTTP Basic del panel privado. | `operador-demo` |
| `GOV_PANEL_PASSWORD` | Contraseña HTTP Basic del panel privado. | Una contraseña exclusiva para la demo. |
| `APP_PORT` | Puerto publicado por Compose. | `8000` |
| `APP_BIND_ADDRESS` | Interfaz local de Compose; `0.0.0.0` permite acceso por LAN. | `127.0.0.1` |
| `APP_DATA_DIR` | Directorio de datos persistentes del contenedor. Compose lo define internamente. | `/var/lib/protocolo-lupita` |
| `PIPER_MODEL_PATH` | Ruta opcional a un modelo local de voz Piper. | Vacía si no se configura. |
| `LUPITA_DEVICE_KEY` | Clave de al menos 32 caracteres que valida eventos Android directos o el relay del monitor. | Vacía si la ingesta Android no se utiliza. |

Si las credenciales gubernamentales están vacías, el panel no concede acceso. Piper es opcional y no se instala con la imagen base. La aplicación no necesita API keys de servicios remotos para el flujo local descrito aquí.

## Datos, almacenamiento y límites

- `data/scenarios/` contiene los guiones JSON sintéticos; `data/fixtures/`, `data/datasets/` y `data/geo/` contienen fixtures, muestras de clasificación y geometrías locales.
- La base de eventos, indicadores, campañas, resultados de escenarios e historial de reportes gubernamentales es `data/prototipo.sqlite3` (en Docker: dentro del volumen). La siembra mantiene su propia base SQLite en `data/protocolo_lupita.sqlite3` y el manifiesto en `data/planting/`.
- El reporte final de una llamada simulada se guarda en SQLite y se puede consultar después de colgar o reiniciar el servidor. Los eventos de actividad en vivo y las sesiones activas usan memoria y se pierden al reiniciar.
- El feed `/mensajes` guarda como máximo 200 eventos en memoria. No es una base persistente ni un archivo de llamadas.
- Los reportes ciudadanos se sanea antes del análisis; el servicio los conserva en memoria para el flujo ciudadano. Las métricas gubernamentales persistidas incluyen los reportes de llamada y análisis SMS conforme a los datos que registra cada módulo.
- Usa datos sintéticos durante la demostración. No conectes teléfonos con mensajes personales ni expongas el servidor de desarrollo a Internet.

## Bridge Android y monitor de teléfono

Hay dos proyectos Android distintos en este repositorio:

1. **`android/` — bridge del portal principal.** Sus fuentes Kotlin pueden publicar notificaciones visibles, SMS entrantes y registros de llamadas nuevos en `/api/eventos`, usando `LUPITA_DEVICE_KEY`. La carpeta contiene fuentes y una guía de integración, pero no un proyecto Gradle completo ni un APK listo para instalar; revisa [`android/README.md`](android/README.md). Actívalo solo en un teléfono propio y autorizado. Su conexión no convierte la llamada simulada en una llamada real.
2. **`monitor_telefono/` — servidor y app Android.** Conserva su servidor y base de datos propios. Para reenviar eventos a `/mensajes`, configura en su `.env` `LUPITA_EVENTS_URL=http://127.0.0.1:8000/api/eventos` y `LUPITA_EVENTS_KEY` con la misma clave aleatoria de `LUPITA_DEVICE_KEY`; el endpoint analiza los textos con el motor SMS local. Búsqueda, filtros y límites están en [`monitor_telefono/docs/INTEGRACION_LUPITA.md`](monitor_telefono/docs/INTEGRACION_LUPITA.md).

## Pruebas y documentación relacionada

Instala también las dependencias de desarrollo y ejecuta la suite desde la raíz:

```powershell
uv sync --group dev
uv run pytest -q
```

Para la prueba de aceptación del recorrido con dos pantallas:

```powershell
uv run pytest -q tests/test_two_screen_acceptance.py
```

Documentos útiles:

- [Integración del prototipo](INTEGRACION.md): estado, límites de acceso y flujo del simulador.
- [Decisiones de arquitectura](DECISIONES_ARQUITECTURA.md): contratos y decisiones de diseño.
- [Aceptación de demo en dos pantallas](docs/aceptacion_demo_dos_pantallas.md): pasos automáticos y comprobación manual LAN.
- [Guion y respaldo de la demostración](docs/guion_respaldo_demo.md): presentación de tres minutos y plan alterno.
- [Plan de demo local](planes_trabajo/06_demo_dual_pantalla_local.md): alcance acordado para la demostración.
