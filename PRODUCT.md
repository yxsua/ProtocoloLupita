# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Personas de Querétaro** que reciben llamadas o mensajes sospechosos y necesitan entender señales de fraude o extorsión, proteger su información y decidir qué hacer después.
- **Personal de gobierno** que consulta indicadores agregados y señales correlacionadas para orientar decisiones estratégicas y una respuesta proactiva.
- **Equipo de demostración y evaluación** que recorre el prototipo con escenarios y datos sintéticos.

## Product Purpose

Protocolo Lupita orienta a la ciudadanía para proteger su información frente a intentos de fraude y extorsión, y proporciona al gobierno indicadores clave para decisiones estratégicas y preventivas. El producto actual es un prototipo local de demostración, no un servicio operativo de atención de incidentes.

## Positioning

El mecanismo principal son números trampa vinculados a copias sintéticas diferenciadas. La atribución de una copia y la correlación de señales de llamadas, SMS y reportes permiten mostrar cómo se podrían detectar fugas y patrones de campaña. Los resultados de la demo son sintéticos e indicativos; no acreditan delitos.

## Operating Context

El portal se ejecuta localmente en una laptop y puede presentarse en dos pantallas conectadas a la misma instancia: una experiencia pública para la ciudadanía y un panel privado para el equipo de gobierno. Los escenarios precargados muestran una llamada simulada y su transcripción sin usar la red telefónica ni requerir micrófono. Para una demostración en celular, ambos dispositivos se conectan a la misma red local.

## Capabilities and Constraints

- Incluye orientación pública, reporte ciudadano de llamadas o mensajes, análisis de SMS escrito por la persona, avisos públicos agregados y mapa con umbral mínimo para grupos pequeños.
- El panel gubernamental protegido presenta actividad y señales detalladas, simulación de voz, atribución, reportes, métricas y eventos de prueba.
- La aplicación principal es web: FastAPI y Jinja2 sirven vistas HTML con CSS y JavaScript sin framework de frontend; SQLite conserva los datos locales previstos por cada módulo.
- La llamada, los escenarios, los números, las copias y la atribución de la demostración son sintéticos. El prototipo no recibe ni realiza llamadas telefónicas reales, no envía reportes a autoridades ni confirma delitos.
- El portal sanea o enmascara datos personales en los flujos ciudadanos; los avisos y mapas públicos exponen información agregada.
- La autenticación del panel de demostración es local y HTTP Basic. La demo está pensada para una red local controlada, no para exposición directa a Internet.
- El bridge Android del portal y el monitor de teléfono son componentes/proyectos separados; el monitor no forma parte del producto que describe este registro.

## Brand Commitments

El nombre del producto es **Protocolo Lupita**. La experiencia de demostración usa a Doña Lupita como personaje de voz sintética.

## Evidence on Hand

El repositorio incluye guiones de llamada, escenarios de prueba, ejemplos sintéticos de SMS, dominios de referencia, geometrías municipales locales y datos de demostración. No hay testimonios, resultados de campo ni métricas de desempeño validadas; futuras superficies no deben presentarlos como reales ni inventar tasas de detección.

## Product Principles

- Ayudar a las personas a proteger su información y entender sus siguientes pasos.
- Dar al gobierno señales útiles para actuar de forma proactiva frente a fraudes y extorsiones.
- Usar números trampa y copias sintéticas como mecanismo central de atribución.
- Presentar los resultados como indicadores para análisis, nunca como confirmación automática de culpabilidad.
