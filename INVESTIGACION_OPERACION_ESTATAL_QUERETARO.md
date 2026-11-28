# Investigación de viabilidad: operación estatal de Protocolo Lupita en Querétaro

**Fecha de corte:** 28 de noviembre de 2026  
**Moneda:** MXN salvo donde se indique USD.  
**Tipo:** estudio preliminar de arquitectura, operación y presupuesto; no es cotización, dictamen jurídico ni autorización para prestar servicios de emergencia.

## 1. Resumen ejecutivo

Protocolo Lupita es hoy un prototipo local con datos sintéticos. Operarlo en todo Querétaro requiere convertir la demo en un servicio público: procesos aprobados, integración institucional, privacidad, seguridad, atención humana, continuidad, accesibilidad y métricas.

El Censo 2020 registró **2,368,467 habitantes y 18 municipios**. Querétaro, San Juan del Río, El Marqués y Corregidora sumaban **1,791,816 habitantes (aprox. 76 %)**; una plataforma digital puede cubrir todo el estado, con enlaces regionales. El Censo reportó **31,383 hablantes de lengua indígena**, por lo que hay que validar contenido accesible, canales y conectividad. [INEGI, resultados del Censo 2020 de Querétaro](https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/nueva_estruc/702825198282.pdf) y [comunicado estatal](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2021/EstSociodemo/ResultCenso2020_Qro.pdf).

| Concepto | Envolvente preliminar |
|---|---:|
| Implementación inicial, integraciones y preparación operativa | **$8–18 M** una sola vez |
| Operación mensual estatal con horario extendido | **$2.0–4.0 M/mes** |
| Operación con centro humano 24/7 y varios puestos concurrentes | **$2.4–4.7 M/mes** |
| Operación anual estimada | **$24–48 M/año**; con 24/7, aprox. **$29–56 M/año** |

Son cifras de planeación, no precios adjudicados. El personal es el mayor gasto recurrente. SMS y voz crecen con el volumen; la nube importa, pero no debería dominar si se controla retención y no se sobredimensiona Kubernetes.

## Lo más innovador y socialmente pertinente de la arquitectura

La propuesta es más valiosa cuando combina detección técnica con garantías para las personas. Su rasgo central no es usar IA por sí sola: es convertir señales de distintos canales en indicios revisables, con límites de privacidad, explicación y supervisión humana.

| Elemento | Qué aporta tecnológicamente | Por qué importa en Querétaro | Estado |
|---|---|---|---|
| **Correlación de señales entre canales** | Une indicadores de SMS, llamadas reportadas y avisos ciudadanos para reconocer patrones/campañas y ordenar revisión, en lugar de tratar cada mensaje como evento aislado. | Permite reconocer tácticas que pueden circular entre municipios y canales; evita que el valor del sistema dependa de un único proveedor o tipo de reporte. | El prototipo ya tiene módulos de SMS, voz, inteligencia y campañas sintéticas. La ingesta real e integración estatal están pendientes. |
| **Inteligencia con evidencia y confianza explícitas** | Conserva origen de señales, hash de evidencia, independencia de fuentes y estados graduados como indicio, corroboración o sin verificar. No transforma una puntuación en una sentencia automática. | Reduce el riesgo de difundir una acusación basada en una sola llamada o mensaje; facilita auditoría, corrección y decisión humana. | Hay reglas, escenarios y cadena de evidencia en el prototipo; se requiere un flujo de revisión, resolución y auditoría institucional en producción. |
| **Privacidad por diseño y separación de superficies** | Sanea PII al recibir reportes, evita conservar audio crudo por defecto, separa el acceso público del gubernamental y suprime agregados pequeños. | Protege a las personas afectadas y evita que un mapa o aviso permita deducir quién reportó. Esto es importante en comunidades pequeñas donde un conteo puede identificar a alguien. | Parte ya está implementada para los flujos de demostración; falta evaluación de impacto, identidad institucional, políticas de conservación y operación segura. |
| **Decisión humana en el circuito** | Reglas deterministas y análisis explicable pueden priorizar casos; las alertas públicas, la derivación y el cierre quedan bajo revisión de personal autorizado. | Una alerta equivocada puede afectar a comercios, personas y confianza pública. La automatización debe acelerar la respuesta, no reemplazar la responsabilidad institucional. | Los límites están declarados en el alcance; la cola y el procedimiento de atención humana son trabajo de producción. |
| **Procesamiento por eventos con escalamiento gradual** | Colas, workers idempotentes y PostgreSQL administrado desacoplan recepción, análisis y notificaciones; facilita absorber picos, reintentar fallos y medir el costo por flujo. | Permite atender campañas repentinas sin perder reportes y priorizar municipios con mayor demanda. Evita que un evento o dependencia externa bloquee todo el portal. | El prototipo es modular pero usa SQLite y algunos estados en memoria. Colas, persistencia de producción y alta disponibilidad son una evolución propuesta. |
| **Operación estatal regional, no solo una app central** | Arquitectura digital única con enlaces municipales y tableros agregados, sin desplegar 18 sistemas independientes. | Cubre las 18 demarcaciones con una base común, mientras conserva acompañamiento cercano para localidades con menor conectividad y brechas de acceso. | La propuesta contempla seis enlaces regionales y puntos focales locales; debe validarse con municipios y usuarios. |
| **Acceso multicanal y accesible** | Web móvil ligera como canal base; voz, WhatsApp o SMS como alternativas optativas y con costo/rate limits visibles. Contenido de lectura sencilla y compatible con tecnologías de asistencia. | No todas las personas tienen datos móviles, habilidades digitales o el mismo idioma. Los canales alternativos deben responder a investigación local y no excluir a población rural, mayor o hablante de lengua indígena. | Hay portal y análisis SMS en el prototipo. Accesibilidad validada, canales reales y contenidos pertinentes requieren trabajo de campo. |
| **Laboratorio reproducible de escenarios sintéticos** | Casos como E01–E14 permiten simular llamadas, SMS, inyección de instrucciones, privacidad, límites de tasa y corroboración sin usar víctimas ni datos reales. | El equipo puede ensayar nuevas reglas, capacitar y mostrar límites antes de afectar reportes reales. Los resultados de simulación no se presentan como efectividad de campo. | El repositorio ya contiene escenarios y una aceptación de demo documentada; se recomienda mantenerlos como pruebas de regresión y capacitación. |
| **Residencia regional y portabilidad tecnológica** | Desplegar en una región mexicana de nube, aislar proveedor de voz/mensajería y llevar métricas de gasto por canal facilita auditar y cambiar servicios. | Reduce dependencia innecesaria y ayuda a evaluar ubicación de tratamiento, costos y continuidad con el sector público. La región local por sí sola no equivale a cumplimiento. | Región y arquitectura son opciones por validar; contratos y rutas de datos con terceros necesitan revisión específica. |

### La innovación que conviene preservar al escalar

1. **Correlacionar sin etiquetar personas.** El producto debe relacionar indicadores/campañas con fuentes trazables, no generar listas públicas de presuntos responsables.
2. **Automatizar lo reversible y supervisar lo sensible.** Deduplicar, validar formato y priorizar puede automatizarse; publicar alertas o transferir información requiere autoridad y revisión.
3. **Diseñar para señales débiles y datos mínimos.** Un reporte ciudadano puede aportar contexto sin exigir CURP, ubicación precisa o audio completo.
4. **Medir el beneficio social además de precisión técnica.** Tiempo de orientación, acceso por municipio, comprensión y costo por caso atendido deben acompañar métricas de clasificación.
5. **Escalar por evidencia.** Activar más canales, turnos o modelos de IA únicamente si el piloto prueba que mejora la cobertura o el tiempo de atención y mantiene seguridad y privacidad.

Así se presenta una arquitectura tecnológicamente avanzada sin hacer depender el valor público de una caja negra: combina correlación multicanal, eventos escalables, evidencia auditable y alternativas de acceso con revisión humana y protección de datos.

## Flujos y módulos disponibles en el sistema

El sistema actual es una aplicación web modular servida por FastAPI. Las pantallas se renderizan con Jinja2, HTML, CSS y JavaScript; los módulos se conectan desde `app/main.py`. El siguiente inventario describe el prototipo existente, no una futura instalación estatal.

### Recorridos funcionales

#### 1. Orientación y reporte ciudadano

1. La persona entra a `/` y puede ir al portal `/citizen` para reportar una llamada o un mensaje sospechoso.
2. El portal sanea o enmascara datos personales antes de pasar el contenido al análisis local.
3. El servicio calcula señales y devuelve orientación o una ruta preventiva. El flujo no presenta la evaluación como veredicto ni envía el reporte a una autoridad.
4. Los agregados autorizados alimentan avisos/mapa públicos, aplicando supresión de grupos pequeños.

El reporte ciudadano del prototipo no constituye una denuncia formal. La persistencia y retención dependen del módulo: el servicio ciudadano usa memoria, mientras que métricas/reportes internos seleccionados se guardan en SQLite.

#### 2. Análisis de SMS

1. En `/sms`, la persona escribe o selecciona un mensaje de ejemplo.
2. El analizador local busca señales de suplantación, enlaces, números, cuentas y coincidencias con dominios de referencia.
3. Presenta explicación y riesgo; los enlaces se muestran desactivados y no se abren.
4. Puede usarse el flujo de reporte ciudadano para enviar un caso saneado.

La bandeja se alimenta con fixtures sintéticos. El prototipo no intercepta el buzón SMS del público ni envía respuestas.

#### 3. Simulación privada de llamada y reporte

1. Personal de demo inicia sesión en `/gobierno` y abre el dashboard. En otro navegador o celular conectado a la misma instancia entra a `/gobierno/simulador`.
2. Selecciona un guion sintético, por ejemplo un escenario de voz E01–E08. La interfaz presenta una llamada entrante ficticia para contestar o rechazar.
3. Al contestar, el simulador reproduce los turnos de ambos personajes con audio local disponible y muestra la transcripción. No necesita conectarse a la red telefónica ni solicitar micrófono para recorrer el guion.
4. Cada turno se sanea antes de alimentar inteligencia local. El dashboard privado recibe la sesión y la transcripción mediante eventos/SSE; muestra indicadores enmascarados, campaña, confianza y hash de evidencia.
5. Al terminar o cancelar, se cierra la sesión y queda un reporte sintético consultable desde `/gobierno/reportes`. El reporte se guarda en SQLite; la sesión activa y los eventos en vivo son memoria y se pierden al reiniciar.

Solo se permite una llamada simulada activa por proceso. Rechazar no crea la conversación; cancelar cierra una sesión contestada. No se guarda audio crudo según el flujo documentado.

#### 4. Siembra y atribución controlada

1. Un operador autenticado abre `/gobierno/siembras` y crea un lote sintético de 1 a 50 copias.
2. Cada copia SQLite recibe un número trampa único. Un ZIP incluye las copias y un manifiesto con hashes; la descarga para participantes omite la relación interna entre número y copia.
3. Una señal dirigida a una trampa ficticia puede atribuirse a la copia correspondiente en el registro privado.

Los lotes son inmutables y se diseñaron para demostración aislada. No deben poblarse con bases reales ni distribuirse junto con el mapa privado de atribución.

#### 5. Avisos y mapa

La ciudadanía consulta `/dashboard` y los endpoints públicos de avisos/mapa. Solo se exponen agregados permitidos; el backend aplica el umbral municipal para no mostrar grupos pequeños. Los resultados detallados, atribución y señales internas se reservan al panel autenticado.

#### 6. Feed de eventos de un dispositivo de prueba

El bridge Kotlin de `android/` puede publicar eventos visibles del dispositivo a `POST /api/eventos` con una clave de dispositivo. La página privada `/mensajes` muestra el feed en vivo, filtros y búsqueda; el WebSocket `/ws/eventos` distribuye eventos a clientes autenticados. También existe un proyecto separado `monitor_telefono/` que puede retransmitir eventos al endpoint.

Esta integración es opcional y separada de la simulación. El repositorio incluye fuentes y guías, no un APK listo para instalar ni un producto de monitoreo masivo. Usarla requiere teléfono propio/autorizado, consentimiento y evaluación jurídica y de privacidad.

#### 7. Escenarios reproducibles para demo y verificación

Las rutas privadas `/api/scenarios` permiten listar casos; se pueden ejecutar individualmente o en conjunto y consultar resultados. Los fixtures E01–E14 permiten mostrar lógica de voz/SMS, límites de tasa, saneamiento, umbral municipal, inyección de instrucciones y corroboración con datos sintéticos. La ejecución sirve para demo y regresión funcional; no mide efectividad real en la población.

### Mapa de módulos

| Módulo | Ubicación | Función disponible |
|---|---|---|
| Portal ciudadano | `app/modules/citizen/` | Reportes de llamadas/mensajes, saneamiento, límites y orientación. |
| SMS | `app/modules/sms/` | Reglas locales, comparación de dominios, explicación y ejemplos. |
| Voz | `app/modules/voice/` | Sesión de llamada simulada, escenarios, respuestas de voz, transcripción saneada, cancelación y cierre. |
| Gobierno | `app/modules/government/` | Autenticación local, panel, simulador, historial y métricas. |
| Inteligencia | `app/modules/intel/` | Extracción/correlación de indicadores, campañas y niveles de confianza. |
| Evidencia | `app/modules/evidence/` | Registro/verificación de evidencias y referencias hash. |
| Siembra | `app/modules/planting/` | Lotes inmutables, copias SQLite, exportación y atribución ficticia. |
| Dashboard y mapa | `app/modules/dashboard/`, `app/modules/map/` | Actividad interna, agregados y avisos públicos con umbral. |
| Eventos Android | `app/modules/mensajes/`, `android/`, `monitor_telefono/` | Ingesta opcional de eventos del dispositivo de prueba y feed privado. |
| Núcleo | `app/core/` | Configuración, esquemas, SQLite, registro/ejecución de escenarios y manejadores. |
| Telefonía | `app/modules/telephony/` | Hay código de integración, pero el router no está montado en el modo ejecutable descrito. No proporciona telefonía real activa. |

### Rutas de entrada y nivel de acceso

| Ruta | Acceso actual | Uso |
|---|---|---|
| `/` | Público | Portada y rutas ciudadanas. |
| `/citizen` | Público | Reporte saneado y orientación. |
| `/sms` | Público | Análisis de SMS escrito y ejemplos. |
| `/dashboard` | Público | Avisos agregados. |
| `/planting` | Público | Explicación de atribución sintética. |
| `/gobierno` | Credenciales locales | Dashboard privado. |
| `/gobierno/simulador` | Credenciales locales | Simulación de llamadas. |
| `/gobierno/reportes` | Credenciales locales | Historial y métricas de demostración. |
| `/gobierno/siembras` | Credenciales locales | Administración de lotes sintéticos. |
| `/mensajes` | Credenciales locales | Feed Android/dispositivo de prueba. |
| `/api/health` | Público | Estado básico del proceso y almacenamiento. |
| `/docs` | API | Documentación interactiva de endpoints. |

Las APIs internas de voz, escenarios, inteligencia, atribución, dashboard detallado y siembra requieren credenciales gubernamentales. La protección actual usa credenciales locales/HTTP Basic: antes de producción se debe sustituir por identidad institucional, MFA, gestión de sesiones y auditoría adecuada.

### Persistencia y límites que afectan el flujo

- `data/prototipo.sqlite3` guarda eventos, indicadores, campañas, resultados de escenarios e historial gubernamental seleccionado.
- `data/protocolo_lupita.sqlite3` conserva el mapa interno de atribución y la siembra; el manifiesto de lotes está en `data/planting/`.
- Los reportes finales de llamadas simuladas se pueden consultar tras reiniciar porque se guardan en SQLite; sesiones y eventos en vivo usan memoria.
- El feed `/mensajes` conserva hasta 200 eventos en memoria, no un archivo histórico del teléfono.
- Los reportes ciudadanos se sanea antes del análisis y el módulo los mantiene en memoria para su flujo; no asumir que tienen persistencia completa.
- El servidor local está pensado para un worker cuando se usan sesiones/bus en memoria. Escalar horizontalmente exige reemplazar esos componentes por estado compartido y colas.

### Funciones fuera de operación en el sistema actual

No están activos: recepción u originación de llamadas telefónicas, recepción de SMS reales del público, grabación/transcripción de llamadas reales, envío de alertas o reportes a terceros, atención oficial de emergencias, despliegue estatal, operación 24/7 o decisiones automatizadas con efecto jurídico. El código de integración telefónica no debe presentarse como servicio disponible.

## 2. Alcance real y brecha con producción

El prototipo incluye FastAPI, portal ciudadano, análisis de SMS, reportes saneados, panel privado, llamadas sintéticas por escenarios, dashboard, atribución ficticia, SQLite y Docker. La documentación registra aprobada la aceptación automatizada de dos pantallas.

No recibe ni inicia llamadas reales, no ingiere SMS reales, no remite reportes a autoridades y no es un canal de emergencia. Sesiones y actividad en vivo viven en memoria; la autenticación actual es local. Faltan centro de atención, SLA, integración institucional, respuesta a incidentes y soporte regional.

**Alcance recomendado:** comenzar con orientación y recepción voluntaria de reportes, con revisión humana y derivación por canales oficiales ya autorizados. No afirmar que identifica personas, acredita delitos ni sustituye denuncias o emergencias. Telecomunicaciones reales deben ser una fase aparte, aprobada por el área responsable, jurídico, privacidad y seguridad.

## 3. Modelo operativo estatal

1. **Centro estatal de operación** para supervisión, incidentes y métricas agregadas.
2. **Canal digital estatal** mediante web adaptable; WhatsApp opcional. Mantener alternativa que no dependa de instalar una app o tener datos móviles.
3. **Puntos focales municipales** designados desde personal existente al inicio. Seis enlaces regionales pueden acompañar capacitación y escalamiento; no hacen falta 18 centros duplicados.
4. **Analistas humanos** revisan señales antes de publicar avisos o derivar casos. El modelo prioriza, no determina culpabilidad ni actúa automáticamente.
5. **Atención telefónica/presencial** según horario acordado.

```text
Ciudadanía → captura y aviso de privacidad → minimización/antiabuso
           → análisis local explicable → revisión humana
           → respuesta preventiva o derivación institucional aprobada
           → métricas estatales agregadas
```

No grabar audio por defecto. Si se habilita voz, definir aviso, finalidad, acceso, retención, proveedor de transcripción y base jurídica.

**Horario:** A) extendido, por ejemplo 07:00–22:00, con guardia institucional fuera de horario; B) atención humana 24/7. Tres puestos ocupados continuamente requieren unas 16 personas (aprox. 5.2 FTE por puesto) más supervisión. Reserva orientativa para 24/7: **$0.4–0.7 M MXN/mes** adicionales. Un formulario disponible todo el día no equivale a respuesta humana inmediata.

## 4. Arquitectura objetivo

- **Nube:** evaluar AWS en mx-central-1, región con tres zonas de disponibilidad. Región local ayuda a diseñar residencia/latencia, pero no prueba cumplimiento ni controla terceros. [AWS: regiones disponibles](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html), [historial de México Central](https://docs.aws.amazon.com/es_es/global-infrastructure/latest/regions/doc-history.html).
- **Aplicación:** separar API y workers asíncronos, contenedores administrados y escalamiento horizontal. Sin equipo Kubernetes dedicado, empezar con contenedores administrados. EKS cuesta **$0.10 USD/hora por clúster** estándar, aparte de nodos, discos, balanceo, tráfico y observabilidad. [AWS EKS pricing](https://aws.amazon.com/eks/pricing/).
- **Datos:** reemplazar SQLite por PostgreSQL administrado, cifrado, Multi-AZ y recuperación a punto en tiempo; separar datos de contacto de indicadores. Añadir colas, reintentos idempotentes y cola de errores.
- **Objetos:** almacenar solo documentos necesarios. No guardar audio crudo por defecto; fijar retención y eliminación verificable.
- **Seguridad:** WAF, MFA/SSO institucional, secretos administrados, acceso por rol y auditoría. Evitar PII en logs.
- **Continuidad:** respaldos cifrados e inmutables, restauraciones probadas, runbooks y simulacros. Acordar RPO/RTO con el responsable.
- **Observabilidad:** disponibilidad, latencia, errores, colas, gasto por canal y costo por reporte atendido.

RDS factura por instancia, almacenamiento, operaciones y respaldos; S3 por almacenamiento, solicitudes, recuperación y transferencia. No hay un precio fijo sin dimensión, retención y tráfico. [AWS RDS PostgreSQL](https://aws.amazon.com/rds/postgresql/pricing/), [AWS S3](https://aws.amazon.com/s3/pricing/).

| Componente | Objetivo propuesto |
|---|---|
| Portal público | 99.9 % mensual; publicar mantenimiento. |
| Ingesta de reportes | 99.9 %; cola con reintento, sin prometer investigación concluida. |
| Consola privada | 99.5–99.9 %; MFA y auditoría. |
| Recuperación | RPO ≤15 min; RTO ≤4 h, a cotizar y probar. |

Son objetivos de diseño, no SLA actuales.

## 5. Costos de APIs y canales

### Tarifas consultadas

Twilio publica en México **$0.2045 MXN/min** para llamada entrante local, **$0.9672 MXN/min** saliente a móvil y **$127.80/mes** por número local. [Twilio Voice México](https://www.twilio.com/es-mx/voice/pricing/mx).

Twilio SMS a México: **$0.1819 USD por segmento saliente**, **$0.02 USD entrante**, con posibles cargos de operador; un texto largo puede consumir varios segmentos. [Twilio SMS México](https://www.twilio.com/en-us/sms/pricing/mx). Conversión: FIX Banxico **$19.6598 MXN/USD** (27-nov-2026), por tanto aprox. **$3.58 MXN por segmento SMS saliente**. La factura real puede usar otra conversión/impuestos. [Banxico FIX](https://www.banxico.org.mx/apps/dao-web/4/52/Fix48.html).

WhatsApp: tarifa de plataforma Twilio **$0.1022 MXN/mensaje**; una plantilla Utility fuera de ventana agrega **$0.069525 MXN** de Meta, total de referencia **$0.171725**. Reglas dependen de categoría/ventana. [Twilio WhatsApp México](https://www.twilio.com/es-mx/whatsapp/pricing).

Como opción de transcripción, OpenAI publica gpt-4o-mini-transcribe a **$0.003 USD/minuto**, aprox. **$0.059 MXN/minuto** al FIX citado. Transmitir audio a un proveedor externo requiere revisión de privacidad, contrato, retención y finalidad. [OpenAI API pricing](https://platform.openai.com/pricing).

### Ejemplos mensuales variables

Escenarios ilustrativos que se deben sustituir por telemetría del piloto. WhatsApp usa Utility fuera de ventana; SMS supone un segmento por mensaje. Sin renta de números, call center, nube, cargos adicionales o impuestos no incluidos.

| Consumo mensual | Inicial | Estatal base | Alto |
|---|---:|---:|---:|
| Minutos entrantes locales | 50,000 | 250,000 | 1,000,000 |
| Minutos salientes a móvil | 5,000 | 20,000 | 50,000 |
| Mensajes WhatsApp | 10,000 | 50,000 | 200,000 |
| SMS salientes (segmentos) | 1,000 | 5,000 | 20,000 |
| Minutos a transcripción API | 10,000 | 50,000 | 200,000 |
| **Total variable estimado/mes** | **$20,944** | **$99,884** | **$370,521** |

Cálculo: minutos entrada × 0.2045; minutos móvil × 0.9672; WhatsApp × 0.171725; segmentos SMS × 0.1819 USD × FIX; minutos transcritos × 0.003 USD × FIX. Diez números locales sumarían aprox. $1,278/mes. No incluye grabación, carriers, registro de remitentes o mensajes fallidos.

**Implicación:** SMS masivo se vuelve caro ($71,520 MXN para 20,000 segmentos al FIX usado); limitarlo a seguimiento consentido. WhatsApp puede costar menos, pero depende de tarifas Meta/categoría. Voz facilita acceso sin datos móviles y crea expectativa de respuesta humana. Mantener reglas locales como ruta predeterminada y hacer opcional cualquier modelo generativo.

## 6. Infraestructura cloud

Reserva mensual de planeación, no precio de calculadora ni cotización AWS.

| Rubro | Rango/mes |
|---|---:|
| Cómputo, contenedores y balanceo | $35,000–$100,000 |
| PostgreSQL, respaldo y almacenamiento | $35,000–$100,000 |
| WAF, secretos y seguridad | $20,000–$60,000 |
| Logs, métricas y alertas | $20,000–$70,000 |
| Egreso, CDN, DNS y objetos | $15,000–$50,000 |
| DR parcial/ambiente de continuidad | $25,000–$70,000 |
| **Total de referencia** | **$150,000–$450,000** |

Antes de licitar, modelar mx-central-1 en AWS Pricing Calculator con Multi-AZ, ambientes, operaciones, GB, retención, egress y backup. Audio y logs retenidos elevan nube y riesgo. Etiquetar costos por canal y ambiente, usar alertas presupuestales. Alternativas: nube estatal (validar redundancia/guardias), nube pública o híbrida (más integración). “Ya hay servidores” no implica costo marginal cero.

## 7. Talento humano

Los montos son **supuestos de planeación cargados** (prestaciones/cargas estimadas), no tabuladores oficiales ni estudios salariales. Sustituir por tabuladores estatales y propuestas reales.

| Función central | FTE | Costo cargado/mes |
|---|---:|---:|
| Dirección de servicio/programa | 1 | $90–140 mil |
| Producto, UX, contenido y accesibilidad | 2 | $90–150 mil |
| Backend, arquitectura, integraciones y datos | 9 | $530–865 mil |
| SRE/DevSecOps/ciberseguridad | 3 | $210–330 mil |
| Analistas de inteligencia y calidad | 5 | $250–400 mil |
| Atención humana horario extendido | 8 | $200–304 mil |
| Supervisión de atención | 2 | $90–140 mil |
| Privacidad, jurídico y gobierno de datos | 1–2 | $70–150 mil |
| Enlaces de adopción municipal | 6 | $210–330 mil |
| **Total indicativo** | **37–38** | **$1.74–2.81 M** |

Seis enlaces acompañan municipios; designar puntos focales existentes evita crear 18 plazas por defecto. Atención 24/7 requiere más agentes; estimar $0.4–0.7 M/mes extra para tres puestos simultáneos.

Otros gastos: auditoría/penetración **$0.5–1.5 M/año**; capacitación **$0.3–0.8 M/año**; equipo y conectividad inicial **$0.8–2.0 M**; materiales/adopción **$0.4–1.2 M/año**. Al anualizar reservas y sumar consumo cloud/API, el consolidado es **$2.0–4.0 M/mes** en horario extendido o **$2.4–4.7 M/mes** con 24/7. Excluye incidentes mayores e integraciones aún no cotizadas.

## 8. Inversión inicial

| Paquete | Rango único |
|---|---:|
| Descubrimiento/diseño de servicio | $0.8–1.5 M |
| Reingeniería: SSO/MFA, Postgres, colas, API, migración | $3.0–6.0 M |
| Seguridad, privacidad, continuidad y pruebas | $1.2–2.5 M |
| Integración formal de canales/sistemas (si se aprueba) | $1.0–3.0 M |
| Equipo y red del centro | $0.8–2.0 M |
| Accesibilidad, contenido y adopción | $0.6–1.5 M |
| Contingencia/estabilización | $0.8–1.5 M |
| **Total estimado** | **$8.2–18.0 M** |

Puede bajar con componentes públicos ya contratados y equipo interno; sube si se migra historial, compra un contact center o se exige 24/7 desde el inicio. Telefonía real es opcional porque no es parte de la demo.

## 9. Privacidad, seguridad y cumplimiento

Revisar la **Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados** publicada el 20 de marzo de 2025 y la legislación aplicable de Querétaro. [DOF, ley general](https://www.dof.gob.mx/nota_detalle.php%3Fcodigo%3D5752569%26fecha%3D20/03/2025); [normatividad estatal](https://secon.queretaro.gob.mx/portal-transparencia/). La Ley de Gobierno Digital local menciona respaldos, contingencia, registro de configuración y tratamiento conforme a normas de datos. [Ley de Gobierno Digital 2026](https://queretaro.gob.mx/documents/20121/1743648/25%2BLEY%2BDE%2BGOBIERNO%2BDIGITAL%2BDEL%2BESTADO%2BDE%2BQUER%C3%89TARO%2B2026.pdf/4f45a0b1-4fd0-a5b9-ca07-f4f826000359?t=1773785914800).

Antes de producción: identificar responsable, finalidad, fundamento, retención y accesos; publicar aviso y proceso ARCO; determinar si aplica evaluación de impacto; minimizar CURP, teléfono y geolocalización; aprobar contratos de encargados, transferencias y subencargados; suprimir grupos pequeños en mapas; cifrar, aplicar MFA y mínimo privilegio; no guardar PII en logs; probar borrado y respaldos; acordar transferencias interinstitucionales. Dictamen jurídico debe validar textos y autoridades vigentes: este documento no es opinión legal.

## 10. Despliegue por fases

| Fase | Duración | Criterio de salida |
|---|---:|---|
| Patrocinio y descubrimiento | 4–6 semanas | Dueño, finalidad, datos, horario, instituciones, presupuesto y privacidad preliminar. |
| Diseño y piloto interno | 8–12 semanas | Arquitectura, SSO/MFA, Postgres, auditoría, atención y restauración; datos sintéticos/anonimizados. |
| Piloto acotado | 8–12 semanas | 2–4 municipios, volumen limitado; medir tiempos, costos, quejas y falsos positivos. |
| Expansión regional | 3–4 meses | Oleadas al resto de municipios, capacitación y protocolos consolidados. |
| Operación estabilizada | Continua | Revisión mensual de costo, seguridad, privacidad y equidad. |

Operación estatal inicial: **8–12 meses**, sujeta a contratación y acuerdos. No usar datos reales antes de cerrar privacidad, seguridad, recuperación y procesos.

## 11. Métricas y riesgos

Medir disponibilidad; tiempo de primera respuesta/cierre; reportes revisados y derivados; costo por reporte y canal; cobertura municipal relativa a población; acceso móvil/conectividad limitada; precisión y falsos positivos revisados por personas; incidentes y restauraciones. No usar “delitos identificados” o “fraudes detenidos” como KPI sin definición y evidencia auditada.

| Riesgo | Mitigación |
|---|---|
| Confusión con emergencia/denuncia oficial | Instrucciones claras, canales vigentes y derivación aprobada. |
| Falso positivo/publicación dañina | No publicar identidades; revisión humana, trazabilidad y corrección. |
| Exceso de datos personales | Minimización, retención corta y evaluación de impacto. |
| Ransomware/interrupción | MFA, segmentación, respaldo inmutable y simulacros. |
| Dependencia de proveedor | Abstracción intercambiable, límites de gasto y web como base. |
| Brecha rural/digital | Canal autorizado telefónico/presencial, sitio ligero y enlaces municipales. |
| Consumo API excesivo | Opt-in, cuotas, deduplicación, rate limit y alertas. |
| Clasificación obsoleta | Muestras revisadas, cambios versionados y pausa segura. |

Antes de autorizar, decidir responsable; propósito/exclusiones; horario/SLA; notificaciones consentidas; voz real; datos/retención; convenios; nube/residencia; RPO/RTO; presupuesto multianual.

## 12. Recomendación

Financiar primero una **fase de 4–6 semanas de descubrimiento**. Entregables: proceso y responsable institucional, matriz de datos, análisis de privacidad, requisitos de atención, capacidad por municipio, cotizaciones formales de nube/canales y presupuesto de 12 meses. Si el piloto demuestra utilidad y seguridad, desplegar web estatal, reglas explicables, revisión humana, derivación autorizada y canales limitados por consentimiento. Agregar 24/7 o transcripción API solo después de medir demanda y aprobar el proceso.

## Fuentes consultadas (noviembre de 2026)

- [INEGI, Censo 2020 Querétaro](https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/nueva_estruc/702825198282.pdf) y [comunicado](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2021/EstSociodemo/ResultCenso2020_Qro.pdf).
- AWS: [regiones](https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html), [historial región](https://docs.aws.amazon.com/es_es/global-infrastructure/latest/regions/doc-history.html), [EKS](https://aws.amazon.com/eks/pricing/), [RDS](https://aws.amazon.com/rds/postgresql/pricing/), [S3](https://aws.amazon.com/s3/pricing/).
- Twilio: [Voice México](https://www.twilio.com/es-mx/voice/pricing/mx), [SMS México](https://www.twilio.com/en-us/sms/pricing/mx), [WhatsApp México](https://www.twilio.com/es-mx/whatsapp/pricing).
- [OpenAI API pricing](https://platform.openai.com/pricing); [Banxico FIX](https://www.banxico.org.mx/apps/dao-web/4/52/Fix48.html).
- Marco: [DOF, ley general de datos (2025)](https://www.dof.gob.mx/nota_detalle.php%3Fcodigo%3D5752569%26fecha%3D20/03/2025), [normatividad estatal](https://secon.queretaro.gob.mx/portal-transparencia/) y [Ley de Gobierno Digital de Querétaro (2026)](https://queretaro.gob.mx/documents/20121/1743648/25%2BLEY%2BDE%2BGOBIERNO%2BDIGITAL%2BDEL%2BESTADO%2BDE%2BQUER%C3%89TARO%2B2026.pdf/4f45a0b1-4fd0-a5b9-ca07-f4f826000359?t=1773785914800).

