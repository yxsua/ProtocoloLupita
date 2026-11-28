# Piloto rápido con Tailscale Funnel

Esta alternativa sirve para validar el flujo HTTPS de enrolamiento sin contratar un VPS. **Tailscale Funnel publica el servicio en Internet**: no es una VPN privada ni debe usarse como sustituto de un despliegue revisado.

## Preparación

1. Instala y autentica Tailscale en el equipo que ejecuta el monitor.
2. Define una contraseña fuerte y una `SECRET_KEY` aleatoria en `monitor_telefono/.env`.
3. Arranca el servidor local con `server/run.ps1` o `sh server/run.sh`. Debe escuchar en `127.0.0.1:8100`, no en `0.0.0.0`.
4. Consulta el nombre HTTPS público que Tailscale asignó al equipo y configúralo exactamente como origen:

```dotenv
BASE_URL_PUBLICA=https://nombre-equipo.nombre-tailnet.ts.net
COOKIE_SECURE=true
```

5. En una terminal del mismo equipo, publica el puerto local:

```sh
tailscale funnel --bg 8100
tailscale funnel status
```

El host público debe mostrar el servicio HTTPS. No abras el puerto `8100` en el router o firewall.

## Prueba

1. Abre el host HTTPS desde una red externa y comprueba `/api/salud`.
2. Inicia sesión en el panel y crea un QR desde **Dispositivos > Agregar teléfono**.
3. Instala la app release firmada que tenga ese host en `BuildConfig`, escanea el QR, comprueba la lista sugerida y acepta el consentimiento.
4. Verifica el primer evento, el latido y la opción de desvinculación; revoca y elimina los datos de prueba al terminar.

La app release no permite cambiar el dominio. Si el host de Funnel cambia, recompila y firma una versión nueva con `MONITOR_SERVER_URL` actualizado; no distribuyas un build debug para resolverlo.

## Riesgos y cierre

- Cualquier persona con la URL pública puede intentar abrir el panel o probar códigos. El login bloquea temporalmente una IP después de cinco errores, y el endpoint de enrolamiento tiene su propio límite; esto no sustituye controles de acceso a nivel de organización.
- Funnel expone el panel y el feed en Internet. No uses mensajes de terceros, información sensible ni cuentas de producción durante el piloto.
- Protege el equipo, `.env`, la base SQLite, los respaldos y el archivo APK. No compartas códigos de enrolamiento ni capturas con mensajes.
- El equipo debe permanecer encendido y conectado. Cerrar Funnel deja inaccesibles el panel y los latidos.
- Al terminar, desvincula el teléfono, revoca/elimina su registro según la política, borra los datos de prueba, despublica Funnel con `tailscale funnel reset` y confirma que no quede una ruta pública activa.

Para uso continuado, prefiere el despliegue con dominio, Caddy, actualizaciones, respaldos y controles operativos descritos en [DESPLIEGUE_VPS.md](DESPLIEGUE_VPS.md).
