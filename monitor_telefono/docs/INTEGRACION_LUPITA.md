# Posible integración futura con Protocolo Lupita

Esta nota describe una alternativa de diseño; **no implementa ni habilita una integración**. `monitor_telefono/` permanece aislado: no importa módulos de voz, no modifica `/app` y no añade dependencias al monitor.

## Idea

Una futura función podría mostrar al administrador una lista de eventos seleccionados o permitir una lectura manual de texto. El usuario tendría que elegir explícitamente qué evento compartir, confirmar el propósito y revisar el contenido antes de enviarlo al módulo de voz. No se deberían reproducir mensajes automáticamente ni iniciar llamadas, contestar remitentes o generar respuestas a partir de ellos.

## Requisitos previos de seguridad y privacidad

- Definir finalidad, consentimiento, retención y responsables para el nuevo flujo; el consentimiento de notificaciones no debe suponerse como consentimiento para análisis por voz.
- Minimizar campos y permitir excluir dispositivos, aplicaciones y eventos; mantener una opción de revocación y borrado.
- Autenticar el acceso entre servicios con credenciales distintas a `X-Device-Key`. El token de ingesta identifica un dispositivo y no debe reutilizarse para leer eventos.
- Diseñar autorización de solo lectura y auditoría que no almacene tokens ni copie el contenido de mensajes a logs.
- Mantener la integración opcional, con límites de acceso, revisión humana y pruebas aisladas.

Actualmente `GET /api/eventos` y `/ws/eventos` requieren una sesión autenticada del monitor. Antes de integrar un consumidor servidor-a-servidor habría que definir expresamente una identidad de servicio de mínimo privilegio; no se debe compartir la cookie de administrador.

## Fuera de alcance

No se incorpora aquí una ruta nueva, cliente, puente, automatización, análisis de audio, transcripción, síntesis de voz ni transferencia de eventos a Protocolo Lupita. El monitor continúa funcionando y probándose de forma independiente.
