# Instal·lar el radar al VPS

Al VPS hi viuran tres serveis (Docker Compose):

| Servei | Què fa |
|---|---|
| `app` | Aplicació web: tauler, sol·licituds amb l'assistent, socis i avisos |
| `programador` | Revisió de cada matí (07:30): fonts oficials, informe i correu si hi ha novetats o terminis |
| `caddy` | HTTPS automàtic (Let's Encrypt) per al vostre domini |

Requisits: un VPS amb Linux (Ubuntu o Debian), 1 GB de RAM com a mínim, els ports 80 i 443 lliures i
accés SSH.

## 1. Domini

Al panell del hosting on teniu el domini, crea un registre DNS:

| Tipus | Nom | Valor |
|---|---|---|
| A | `radar` (o el subdomini que vulguis) | IP pública del VPS |

Per exemple, `radar.stimulo.com`. Pot trigar uns minuts a propagar-se: comprova-ho amb
`ping radar.stimulo.com`.

## 2. Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # tanca la sessió SSH i torna a entrar
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```

## 3. Codi

Recomanat: fes el repositori **privat** abans de continuar (GitHub → Settings → General → Danger
Zone → Change visibility). Per clonar-lo des del VPS, crea una *deploy key* de només lectura
(GitHub → Settings → Deploy keys) o fes servir un token personal.

```bash
git clone git@github.com:stimulomarqueting-glitch/Radar-d-ajuts.git radar
cd radar
mkdir -p privat && sudo chown -R 1000:1000 privat
cp .env.example .env && chmod 600 .env
```

Si tens la classificació de socis (`privat/socis.yaml`), copia-la a `privat/` del VPS:

```bash
scp privat/socis.yaml usuari@vps:radar/privat/
```

## 4. Claus d'accés

```bash
docker compose build
docker compose run --rm app python -m radar contrasenya
```

Et demana una contrasenya (mínim 12 caràcters; millor una frase llarga) i si vols el segon factor.
Copia les línies que surten al fitxer `.env` **tal com surten, amb les cometes simples**. Si actives
el segon factor, afegeix la clau a Google Authenticator, 1Password o similar.

## 5. Fitxer `.env`

Omple la resta de valors (vegeu els comentaris de `.env.example`):

- `RADAR_DOMINI`: el domini del pas 1.
- `ANTHROPIC_API_KEY`: clau de l'API de Claude (console.anthropic.com), per a l'assistent.
- `SMTP_*` i `RADAR_DESTINATARI`: correu dels avisos del matí.
- `HOLDED_API_KEY`: Holded → Configuració → Desenvolupadors. Només es fa servir per llegir contactes.

## 6. Arrencar

```bash
docker compose up -d --build
docker compose logs -f            # Ctrl+C per sortir
```

Obre `https://radar.stimulo.com`, entra amb l'usuari (`xavi` per defecte) i la contrasenya, i revisa
la pàgina **Configuració**: no hi ha d'haver cap avís. A **Avisos → Revisar ara** pots provar el
correu.

## 7. Desactivar la revisió de GitHub

Perquè no arribin dos correus cada matí: GitHub → Settings → Secrets and variables → Actions →
Variables → **New repository variable** `RADAR_PROGRAMADOR` = `vps`.

## Feina habitual

| Què | Ordre (a la carpeta `radar` del VPS) |
|---|---|
| Actualitzar el catàleg o l'aplicació | `git pull && docker compose up -d --build` |
| Veure què fa la revisió del matí | `docker compose logs --tail 50 programador` |
| Canviar la contrasenya | `docker compose run --rm app python -m radar contrasenya`, edita `.env` i `docker compose up -d` |
| Tancar totes les sessions obertes | Canvia `RADAR_SECRET` a `.env` i `docker compose up -d` |
| Canviar l'hora de la revisió | `RADAR_HORA=07:00` a `.env` i `docker compose up -d` |

## Còpies de seguretat

Tot el que és vostre és a `privat/` (base de dades d'expedients i converses, fitxers adjunts, avisos
desats i classificació de socis) i al volum `estat` (convocatòries ja avisades):

```bash
tar czf ~/radar-$(date +%F).tgz -C ~/radar privat
docker run --rm -v radar_estat:/estat -v ~/:/copia alpine tar czf /copia/radar-estat-$(date +%F).tgz -C /estat .
```

Programa-ho amb `crontab -e` (per exemple, cada nit a les 2:00) i guarda les còpies fora del VPS.

## Si el VPS ja té un servidor web

Si els ports 80 i 443 ja els fa servir un altre servidor (nginx, Apache, Plesk…), treu el servei
`caddy` del `docker-compose.yml`, publica el port de l'aplicació només en local
(`ports: ["127.0.0.1:8000:8000"]` al servei `app`) i afegeix un *proxy invers* cap a
`http://127.0.0.1:8000` al servidor existent, amb HTTPS. Cal que el proxy passi la capçalera `Host`
original i que no guardi a la memòria cau les respostes `text/event-stream` (el xat).

## Seguretat

- Només hi pot entrar l'usuari de `RADAR_USUARI` amb la contrasenya. Després de 5 intents fallits, la
  IP queda bloquejada 15 minuts.
- La galeta de sessió és `HttpOnly`, `Secure` i caduca a les 12 hores (`RADAR_HORES_SESSIO`).
- El fitxer `.env` conté totes les claus: `chmod 600 .env` i no el copiïs mai al repositori.
- Les converses amb l'assistent s'envien a l'API d'Anthropic; la resta de dades no surt del VPS
  (excepte els correus d'avís).
