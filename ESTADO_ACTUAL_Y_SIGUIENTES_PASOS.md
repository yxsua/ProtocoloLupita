# Estado actual del proyecto y siguientes pasos

**Proyecto:** Protocolo Lupita  
**Fecha del resumen:** 28 de noviembre de 2026  
**Alcance:** prototipo de demostración local, con datos y escenarios sintéticos.

## Resumen ejecutivo

El proyecto cuenta con una aplicación web modular en FastAPI, Jinja2, HTML, CSS y JavaScript, con almacenamiento SQLite. La experiencia se divide en un portal público para ciudadanía y un área privada de Gobierno. El flujo principal de demostración simula llamadas mediante escenarios precargados, muestra una transcripción saneada en el simulador y el dashboard, y guarda el reporte para consulta posterior.

La documentación registra aprobada la prueba automatizada de aceptación en dos pantallas. La validación manual desde laptop y celular en una red local, el reinicio real del contenedor durante esa prueba y la grabación de respaldo aún aparecen pendientes. Este resumen se basa en los archivos del proyecto y el estado del checkout; no se ejecutaron pruebas durante su preparación.

## Estado por área

| Área | Estado actual | Notas |
|---|---|---|
| Portal ciudadano | Implementado | Orientación, recepción de reportes con saneamiento de datos y rutas guiadas. |
| Análisis de SMS | Implementado para demostración | Reglas, dominios y fixtures locales; no recibe SMS reales ni abre enlaces. |
| Gobierno | Implementado | Acceso con credenciales locales; dashboard, escenarios e historial son privados. |
| Simulación de llamadas | Implementada | Escenarios sintéticos, voces locales, transcripción en vivo y controles para contestar, rechazar y cancelar. No usa telefonía real ni requiere micrófono. |
| Inteligencia, evidencia y atribución | Implementadas para datos sintéticos | Incluye siembra, indicadores, campañas, niveles de confianza y referencias/hash de evidencia. Los resultados no confirman delitos. |
| Reportes e historial | Implementados | Reportes con transcripción saneada guardados en SQLite; el bus y las sesiones en vivo permanecen en memoria. |
| Avisos y mapa | Implementados | Información pública agregada, con supresión de grupos pequeños según la documentación. |
| Eventos Android | Parcial / integración separada | Hay fuentes y guías de bridge/monitor; no equivale a recepción de llamadas reales ni a una app lista para instalar desde este repositorio. |
| Contenedorización | Preparada | Hay `Dockerfile` y `compose.yaml`, además de instrucciones para persistencia local. |
| Aceptación automatizada | Documentada como aprobada | `docs/aceptacion_demo_dos_pantallas.md` registra 1 prueba aprobada el 28/11/2026. No se volvió a ejecutar para este resumen. |
| Ensayo manual y materiales | Pendientes | Falta registrar la prueba LAN en los dispositivos del equipo y crear el video local de respaldo. |

## Estado del checkout

- Rama: `main`, alineada con `origin/main` según el estado observado.
- Hay cambios locales sin commit en múltiples áreas de la aplicación, documentación y monitor Android, además de archivos nuevos sin seguimiento. Conviene revisarlos antes de preparar una entrega o sincronizar cambios.
- Existe `.env` local. No se copiaron ni incluyeron sus valores en este documento.
- No se encontró `artifacts/demo-respaldo.mp4` en la ruta revisada.
- Se encontraron 15 archivos de pruebas y escenarios que cubren casos identificados hasta E14; la cobertura completa no se verificó en esta revisión.

## Siguientes pasos recomendados

### 1. Revisar el trabajo local

Inspeccionar `git diff` y los archivos nuevos, confirmar que los cambios intencionales estén completos y que no se incluyan credenciales, datos personales o artefactos temporales. Después, acordar qué cambios deben formar parte de la entrega.

### 2. Revalidar el flujo automatizado

Ejecutar la prueba de aceptación de dos pantallas y la suite completa desde `Proyecto/` con el entorno del equipo. Registrar resultados y atender fallos o avisos que afecten el recorrido. La aprobación mencionada arriba corresponde a lo que ya registra el documento de aceptación, no a una ejecución de este resumen.

### 3. Completar el ensayo manual en LAN

Con el contenedor y las credenciales de demo configurados:

1. Abrir `/gobierno` en la laptop y `/gobierno/simulador` en el celular conectado a la misma red.
2. Recorrer un escenario E01 de inicio a fin y comprobar que ambas pantallas reflejan la transcripción saneada.
3. Probar rechazo, cancelación durante la llamada, cierre normal y recuperación ante un fallo de turno.
4. Reiniciar el contenedor y comprobar que el reporte sigue disponible desde el historial.
5. Registrar incidencias, duración observada y capturas sin presentar resultados sintéticos como métricas reales.

Actualizar el resultado manual en `docs/aceptacion_demo_dos_pantallas.md`.

### 4. Preparar respaldo de presentación

Ensayar el guion de tres minutos y grabar el flujo en dispositivos de prueba. Guardar el respaldo en `artifacts/demo-respaldo.mp4` y comprobar que se reproduce sin conexión. Mantener visible que el contenido es simulado y evitar mostrar `.env` o credenciales.

### 5. Cerrar alcance y entrega

Confirmar que todos los escenarios E01–E14 previstos cargan y que los estados de rechazo, cancelación y error liberan la sesión. Revisar que las rutas de Gobierno permanezcan protegidas y que las superficies públicas solo expongan información agregada. Alinear README, plan de demo y evidencia con el resultado manual final.

## Límites del prototipo

- Números, personas, llamadas, mensajes, copias, ubicaciones y atribuciones de la demo son ficticios.
- La aplicación no recibe ni inicia llamadas reales, no envía reportes a autoridades y no acredita delitos.
- El panel utiliza autenticación local y está pensado para una red controlada; no es un servicio operativo listo para exposición pública.
- La persistencia de reportes no implica persistencia de sesiones ni eventos en vivo, que se guardan en memoria.

## Documentos de referencia

- [README.md](README.md): instalación, recorridos y módulos.
- [PRODUCT.md](PRODUCT.md): propósito, usuarios y límites del producto.
- [INTEGRACION.md](INTEGRACION.md): acceso, flujos y modo local.
- [docs/aceptacion_demo_dos_pantallas.md](docs/aceptacion_demo_dos_pantallas.md): prueba automatizada y lista de verificación manual.
- [docs/guion_respaldo_demo.md](docs/guion_respaldo_demo.md): guion y plan de respaldo.
- [planes_trabajo/06_demo_dual_pantalla_local.md](planes_trabajo/06_demo_dual_pantalla_local.md): alcance y brechas de cierre.
- [DECISIONES_ARQUITECTURA.md](DECISIONES_ARQUITECTURA.md): contratos y decisiones técnicas.
