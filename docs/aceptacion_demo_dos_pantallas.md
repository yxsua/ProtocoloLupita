# Prueba de aceptación — demo privada en dos pantallas

**Alcance:** llamada sintética E01, una pantalla de simulación y otra de monitoreo en Gobierno.  
**Fecha de verificación automatizada:** 28 de noviembre de 2026  
**Datos:** fixtures sintéticos. No se usa telefonía real, micrófono ni servicios externos.

## Resultado automatizado

Estado: **APROBADA**.

La prueba automatizada `tests/test_two_screen_acceptance.py` abre la vista de simulación y el dashboard mediante dos clientes independientes con credenciales de Gobierno; inicia E01; avanza todos sus turnos; confirma eventos de inicio y fin desde el monitor; consulta el reporte guardado; elimina el bus de eventos en memoria y vuelve a consultar el detalle desde SQLite. También confirma que el reporte contiene transcripción de ambos participantes y no contiene la CLABE en claro.

Ejecutar desde la raíz del proyecto:

```powershell
uv run pytest -q tests/test_two_screen_acceptance.py
```

Resultado observado: **1 passed**. La ejecución reportó avisos de deprecación de Starlette/Pydantic y del reloj UTC en el módulo de voz; no afectaron esta aceptación.

## Comprobación manual en la red local

Esta parte verifica navegador, síntesis de voz y conectividad física del celular. No está sustituida por el test automatizado.

### Preparación

1. Configura `GOV_PANEL_USERNAME` y `GOV_PANEL_PASSWORD` en `.env`.
2. Para Docker, configura `APP_BIND_ADDRESS=0.0.0.0` y arranca:

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

3. Confirma que `http://127.0.0.1:8000/api/health` devuelve `{"status":"ok"}`.
4. En la laptop, abre `http://127.0.0.1:8000/gobierno` e inicia sesión.
5. En el celular conectado a la misma LAN, abre `http://<IP-local-de-la-laptop>:8000/gobierno/simulador` e inicia sesión con las credenciales locales de Gobierno.
6. Deja el dashboard visible en la laptop y el simulador visible en el celular.

### Recorrido de aceptación

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | En el celular, seleccionar E01 y pulsar **Contestar**. | Aparece la llamada entrante y después el estado conectado. No se solicita micrófono. |
| 2 | Mantener ambas pantallas visibles durante los turnos. | Se oyen las voces sintéticas del atacante y Doña Lupita; cada intercambio aparece en la transcripción del simulador y en la línea de tiempo del dashboard. |
| 3 | Observar número receptor, atribución e indicadores. | Son ficticios; las cuentas aparecen enmascaradas; el origen está marcado como simulado/no verificado. |
| 4 | Esperar el fin normal del escenario. | La sesión termina, el dashboard muestra el cierre y permite preparar el borrador. |
| 5 | En laptop, abrir **Reportes y métricas** y elegir **Consultar** en el registro E01. | El detalle conserva el escenario, cronología/transcripción saneada, duración, atribución e indicadores; la vista indica que es una simulación. |
| 6 | Reiniciar el contenedor con `docker compose restart app`, volver a entrar y consultar E01 desde el historial. | El registro y el detalle siguen disponibles desde el volumen local aunque los eventos en vivo se hayan reiniciado. |

### Ciclo de rechazo y cancelación

- Selecciona un escenario y pulsa **Rechazar**. La conversación no debe iniciarse ni dejar una sesión activa.
- Inicia E01, pulsa **Cancelar llamada** durante la conversación y confirma que el dashboard recibe el cierre.
- Desde **Reportes y métricas**, consulta el reporte cancelado. Debe conservar únicamente los turnos alcanzados antes de cancelar y permitir comenzar otro escenario.

### Evidencia que conviene guardar durante el ensayo

- Captura de la pantalla del celular con la llamada conectada y la transcripción.
- Captura de la laptop con los mismos turnos y las señales del dashboard.
- Captura del detalle E01 consultado desde el historial después de reiniciar el servicio.
- Duración medida del recorrido y cualquier incidencia observada. No convertir estos resultados de demo en métricas de efectividad real.

**Resultado manual:** pendiente de registrar por el equipo en los dispositivos y la red que se usarán el día de la presentación.
