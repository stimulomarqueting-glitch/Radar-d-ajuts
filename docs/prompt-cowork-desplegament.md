# Prompt para Cowork: desplegar el Radar en el VPS de Hostinger con el dominio de SiteGround

Copia el bloque de abajo en una sesión de Claude Cowork con los paneles de Hostinger, SiteGround y
GitHub abiertos y la sesión iniciada en los tres. Ten a mano:
- una contraseña nueva para el radar, de 12 caracteres o más;
- la clave de la API de Claude;
- los datos del correo que enviará los avisos;
- la clave de la API de Holded;
- el fichero `socis.yaml`.

```text
Objetivo: dejar el Radar de ayudas de Stimulo funcionando en el VPS de Hostinger, accesible solo para mí con contraseña en https://radar.stimulo.com (si el dominio principal de Stimulo no es stimulo.com, usa el que sea y dímelo). El DNS del dominio está en SiteGround; el VPS está en Hostinger. Tengo abiertos y con sesión iniciada hPanel de Hostinger, Site Tools de SiteGround y GitHub.

Qué es: una aplicación Python (FastAPI) con tres servicios en Docker Compose: «app» (web), «programador» (revisión diaria a las 07:30 que envía un correo si hay novedades) y «caddy» (HTTPS automático con Let's Encrypt). Repositorio: https://github.com/stimulomarqueting-glitch/Radar-d-ajuts, rama claude/determined-edison-ovjuoj. La guía de referencia está en docs/desplegament.md del repositorio: síguela si algo de este prompt no encaja.

Reglas:
- Secretos: nunca elijas, inventes ni escribas tú contraseñas ni claves, y no las repitas en el chat. Cuando haga falta una (contraseña del radar, ANTHROPIC_API_KEY, SMTP, HOLDED_API_KEY, token de GitHub), para y pídeme que la escriba yo en el terminal o en el campo.
- DNS: no modifiques ni borres ningún registro existente en SiteGround; solo añade el nuevo. No toques la web actual de Stimulo.
- Pide confirmación antes de cualquier acción destructiva o de pago: reinstalar el sistema del VPS, cambiar de plan, borrar ficheros o contenedores que ya existan, cambiar nameservers.
- Si algo no coincide con lo que espera este prompt (otro sistema operativo, puertos ocupados, DNS en otro proveedor), para y explícame qué has encontrado y qué propones.

Pasos:

1. Hostinger (hPanel → VPS):
   - Anota la IP pública (IPv4) y el sistema operativo.
   - Abre el terminal del navegador (o SSH) como root.
   - Comprueba que es Ubuntu o Debian: `cat /etc/os-release`.
   - Comprueba si algo ocupa los puertos web: `ss -tlnp | grep -E ':(80|443) '`. Si hay algún panel o servidor web usándolos, para y pregúntame (la guía tiene una alternativa con proxy).
   - Si el VPS tiene cortafuegos en hPanel, permite TCP 22, 80 y 443, y UDP 443.

2. SiteGround (Site Tools del dominio → Dominio → Editor de zona DNS):
   - Confirma que el dominio usa los nameservers de SiteGround. Si no, dime dónde está la zona DNS y para.
   - Añade un registro A: nombre «radar», valor = IP del VPS, TTL 1 hora. Si el VPS tiene IPv6, añade también el AAAA.
   - Mira los registros MX y dime dónde está el correo del dominio (SiteGround, Google Workspace u otro): lo necesitaremos en el paso 5.
   - Desde el VPS, espera hasta que `getent hosts radar.stimulo.com` devuelva la IP del VPS (puede tardar unos minutos).

3. VPS: Docker y cortafuegos:
   - Docker: `curl -fsSL https://get.docker.com | sh`, y después `docker compose version` para comprobarlo.
   - Cortafuegos (si ufw está activo o se puede activar sin cortar la sesión): `ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable`.

4. VPS: código:
   - `git clone -b claude/determined-edison-ovjuoj https://github.com/stimulomarqueting-glitch/Radar-d-ajuts.git /opt/radar && cd /opt/radar`.
   - Si el repositorio es privado y el clon falla, crea en GitHub un token de acceso «fine-grained», solo lectura (Contents: Read) y solo para este repositorio, y pídeme que lo pegue yo cuando git pida la contraseña.
   - Prepara las carpetas: `mkdir -p privat && chown -R 1000:1000 privat`, y luego `cp .env.example .env && chmod 600 .env`.

5. VPS: fichero .env:
   - Abre .env con nano. Pon RADAR_DOMINI=radar.stimulo.com y RADAR_USUARI=xavi (o el usuario que yo te diga).
   - Contraseña: ejecuta `docker compose build`, y después `docker compose run --rm app python -m radar contrasenya`. La contraseña la escribo yo (dos veces). Cuando pregunte por el segundo factor, pregúntame si lo quiero.
   - Copia las líneas que salen (RADAR_CONTRASENYA_HASH, RADAR_SECRET y, si lo activo, RADAR_TOTP_SECRET) al .env tal cual, con las comillas simples: el hash contiene «$» y sin comillas se rompe.
   - Pídeme que pegue yo en el .env:
     - ANTHROPIC_API_KEY;
     - HOLDED_API_KEY;
     - RADAR_DESTINATARI (mi correo).
   - Correo de salida SMTP:
     - Si el correo está en SiteGround, busca en Site Tools → Email la configuración SMTP (servidor y puerto 465 SSL) y propónme crear una cuenta para el envío, por ejemplo radar@stimulo.com. La contraseña de esa cuenta la escribo yo.
     - Si está en Google Workspace: smtp.gmail.com, puerto 587 y una contraseña de aplicación que genero yo.
     - Rellena SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_FROM; SMTP_PASSWORD lo escribo yo.
   - Deja RADAR_HORA=07:30 y RADAR_ZONA_HORARIA=Europe/Madrid.

6. VPS: socios (opcional): crea /opt/radar/privat/socis.yaml con nano y pídeme que pegue el contenido del fichero socis.yaml que tengo. Después: `chown 1000:1000 privat/socis.yaml && chmod 600 privat/socis.yaml`.

7. Arrancar:
   - `docker compose up -d --build`.
   - `docker compose ps`: los tres servicios deben estar «running», y «app» debe acabar en «healthy».
   - `docker compose logs caddy --tail 50`: espera a ver que ha obtenido el certificado de radar.stimulo.com. Si falla, normalmente es el DNS (aún no propagado) o el puerto 80 cerrado.
   - `curl -s https://radar.stimulo.com/salut` debe responder «ok».
   - `docker compose logs programador --tail 20` debe mostrar «Programador actiu: revisió diària a les 07:30».

8. Comprobar en el navegador:
   - Abre https://radar.stimulo.com. Debe redirigir a la página de acceso con candado HTTPS válido. Yo escribo la contraseña.
   - Configuración: no debe aparecer ningún aviso rojo. Si aparece alguno, dime cuál.
   - Avisos: pulsa «Revisar ara» sin marcar «Enviar el correo». Espera 1–2 minutos, recarga y anota los errores de fuentes de la tabla (BDNS, Funding & Tenders, PSCP, PLACSP, TED). Son las primeras pruebas reales de estas fuentes: copia el texto de cada error en el informe final.
   - Licitacions: comprueba que salen anuncios. Si no sale ninguno, dime qué indica la revisión.
   - Pregúntame si quiero probar el envío del correo («Revisar ara» marcando «Enviar el correo») y el asistente (un mensaje corto en una solicitud de prueba).

9. GitHub (repositorio → Settings → Secrets and variables → Actions → Variables): crea la variable RADAR_PROGRAMADOR con valor «vps». Así GitHub Actions deja de enviar el correo de la mañana y no llegan duplicados.

10. Copias de seguridad:
   - Crea /root/copia-radar.sh. Debe hacer un tar.gz de /opt/radar/privat y otro del volumen radar_estat con: `docker run --rm -v radar_estat:/e -v /root/copias:/c alpine tar czf /c/estat-FECHA.tgz -C /e .`.
   - Las copias van a /root/copias. Se borran las de más de 14 días.
   - Prográmalo con crontab a las 02:15.
   - Ejecútalo una vez para comprobar que funciona.

11. Informe final. Escríbeme un resumen con:
   - la URL;
   - la IP del VPS;
   - el registro DNS creado;
   - qué variables del .env están rellenadas (solo los nombres, nunca los valores);
   - la salida de `docker compose ps`;
   - los errores de fuentes de la primera revisión;
   - qué ha quedado pendiente.
   Recuérdame cómo actualizar: `cd /opt/radar && git pull && docker compose up -d --build`.
```
