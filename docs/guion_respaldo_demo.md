# Guion y respaldo de la demostración

Este guion deja preparado un recorrido breve y repetible para la presentación. La grabación de video debe realizarse en los dispositivos/red del equipo y guardarse como `artifacts/demo-respaldo.mp4`; el video no está incluido todavía en el repositorio.

## Guion de 3 minutos

| Tiempo | Pantalla y acción | Mensaje clave |
|---|---|---|
| 0:00–0:25 | Mostrar la portada pública y el acceso separado de Gobierno. | La ciudadanía recibe orientación y reporta de forma saneada; los resultados internos permanecen privados. |
| 0:25–0:45 | En Gobierno, mostrar dashboard y abrir el simulador en el segundo dispositivo. | El escenario es enteramente local y sintético; no se marca un número real. |
| 0:45–1:40 | Seleccionar E01, contestar la llamada y dejar avanzar la conversación. | El sistema reproduce ambos roles y comparte la transcripción saneada entre el simulador y el dashboard. |
| 1:40–2:15 | Mostrar atribución por número receptor, CLABE enmascarada, estado y evidencia. | Una señal es un indicio revisable; el prototipo no afirma fraude confirmado por una fuente aislada. |
| 2:15–2:40 | Abrir Reportes y métricas; consultar el detalle E01 guardado. | El cierre conserva la cronología y el reporte sigue consultable después de reiniciar el servidor. |
| 2:40–3:00 | Mostrar análisis de un SMS sintético desde la sección pública y cerrar. | La misma plataforma incorpora señales de distintos canales; las acciones a terceros son simuladas. |

## Grabación del respaldo

1. Ejecutar la prueba automatizada documentada en [aceptacion_demo_dos_pantallas.md](aceptacion_demo_dos_pantallas.md).
2. Ensayar el recorrido LAN y guardar las capturas que enumera esa prueba.
3. Cerrar notificaciones y otras ventanas; usar datos sintéticos y no mostrar `.env` ni credenciales en el video.
4. Grabar la pantalla de la laptop con el dashboard y la del celular con el simulador. Si solo se dispone de un equipo de captura, grabar ambas ventanas del navegador en una composición lado a lado.
5. Incluir el historial y abrir el detalle guardado; no terminar el video inmediatamente al colgar.
6. Guardar el archivo en `artifacts/demo-respaldo.mp4` y comprobar que se reproduce sin conexión.

## Plan de respaldo durante la presentación

- **El celular no conecta a la LAN:** continuar con el simulador en otra pestaña autenticada de la laptop; conservar dashboard e historial visibles.
- **El navegador no reproduce voz:** dejar avanzar el escenario y mostrar la transcripción de ambos roles en el simulador y el dashboard.
- **La sesión quedó ocupada:** usar el control de recuperación/cancelación, comprobar el cierre y volver a iniciar E01.
- **El servidor se reinicia tras la llamada:** ingresar de nuevo a Gobierno y abrir el historial; consultar el reporte persistido desde SQLite/volumen.
- **La demo en vivo no está disponible:** reproducir `artifacts/demo-respaldo.mp4` y explicar que muestra el mismo flujo local y sintético.

No presentar capturas o video como evidencia de detección en producción. Son respaldo visual de una demostración reproducible.
