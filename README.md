# LTI Chat Scala

Herramienta LTI 1.3 para Canvas, en Django, que embebe el chat de Clara
(agente de IA orquestado en n8n) dentro de cada página/unidad de un curso:
al abrir el chat se le muestra directamente la pregunta de apertura de esa
unidad (sin selector), se guarda por estudiante y por página para no
volver a pedirla, y se mantiene el historial de esa conversación — todo
con control de consumo de tokens por estudiante y curso.

Este repo es el MVP descrito en el documento de alcance del proyecto
(fases 0 y 1 del roadmap): lanzamiento LTI 1.3, modelo de datos, control de
tokens, cliente hacia el webhook de n8n, y un widget de chat embebido.
Falta lo de fase 2+ (panel de reporting, multi-flujo configurable desde
admin más allá de lo básico, streaming) — ver la sección "Qué falta" al
final.

## Arquitectura en una línea

`Canvas (iframe)` → `Django` valida el lanzamiento LTI, sirve el widget,
autentica con un token corto propio, aplica el límite de tokens → `n8n`
(`POST /webhook/clara` u otro flujo) resuelve la respuesta del agente y
reporta los tokens reales consumidos → Django los acumula en un ledger.

## Requisitos

- Python 3.11+
- PostgreSQL 15+ en producción (SQLite funciona out-of-the-box para desarrollo local)
- Redis en producción (nonce/state del login OIDC — ver más abajo por qué)
- Una cuenta de administrador de Canvas con permisos para crear un Developer Key (LTI 1.3)
- Al menos un webhook de n8n accesible por HTTP (ver sección 6 del documento de alcance)

## Puesta en marcha local (sin Canvas real)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # para entrar a /admin/

# Crea un curso, estudiante, plantillas y un N8nFlow de ejemplo,
# e imprime un token de sesión listo para usar:
python manage.py seed_demo --n8n-webhook-url "https://tu-n8n/webhook/clara" --n8n-secret "loquesea"

python manage.py runserver
```

Con el token que imprime `seed_demo` puedes probar la API directamente,
sin pasar por un lanzamiento real de Canvas:

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/templates/
```

### Probar sin depender de un n8n real

`tools/mock_n8n.py` levanta un servidor HTTP mínimo que responde como lo
hace hoy el webhook `/clara` (incluye el campo `tokens_used` en vez del
desglose `tokens.{prompt,completion,total}`, para probar también la
compatibilidad hacia atrás):

```bash
python tools/mock_n8n.py &
# apunta el N8nFlow de prueba a http://127.0.0.1:9000/webhook/clara desde /admin/
```

## Variables de entorno

Copiar `.env.example` a `.env` y completar. Lo importante:

- `DATABASE_URL`: en local puede omitirse (usa SQLite); en producción, la cadena de PostgreSQL.
- `REDIS_URL`: **requerido en producción** si Gunicorn corre con más de un worker. pylti1p3 guarda el `nonce`/`state` del login OIDC en el cache de Django — si cada worker tuviera su propia memoria (`LocMemCache`), el login podría iniciar en un worker y el launch validarse en otro, y fallar. Con `REDIS_URL` sin configurar, el proyecto cae a memoria local (solo válido con `--workers 1`, es decir, para desarrollo).
- `LTI_FRAME_ANCESTORS`: dominio(s) de Canvas que pueden embeber el chat en un iframe.
- `LAUNCH_TOKEN_SECRET`: secreto distinto de `DJANGO_SECRET_KEY` para firmar el token corto del widget.
- `CLARA_APERTURA_URL` / `CLARA_RESPONDER_URL`: los dos webhooks fijos de n8n que abren el momento y procesan cada turno de la conversación (ver `apps/chat/services/clara_client.py`).
- `CLARA_COURSE_ID`: el `course_id` que se manda a esos webhooks — hoy es un slug de contenido sembrado en Supabase (`toma_decisiones`, el curso piloto), no el `canvas_course_id` de Canvas.

## Configurar el Developer Key en Canvas (LTI 1.3)

1. En Canvas: **Admin → Developer Keys → + LTI Key**.
2. **Redirect URIs / Target Link URI**: `https://tu-dominio/lti/launch/`
3. **OpenID Connect Initiation Url**: `https://tu-dominio/lti/login/`
4. **JWK Method**: "Public JWK URL" → `https://tu-dominio/lti/jwks/`
5. Habilitar los claims/placements que necesites (como mínimo, el `context` claim para tener `course_id`).
6. Copiar el `Client ID` y los datos de la plataforma que Canvas te muestra (issuer, auth login url, auth token url, JWKS de la plataforma).
7. En `/admin/` de Django, crear:
   - Una **LTI Tool Key** (clave RSA propia de la herramienta — puedes generarla con `openssl genrsa 2048`, o dejar que `seed_demo` la genere si estás probando).
   - Un **LTI Tool** con el issuer/client_id/URLs del paso 6, la key anterior, y el/los `deployment_id` que Canvas asigna al instalar la herramienta en un curso.
8. **Por cada página/unidad de Canvas** donde se inserte el link de la herramienta (asignación, página, o item de módulo de tipo "External Tool"), la URL de lanzamiento debe llevar `?momento=<valor>` al final, con uno de estos valores: `bienvenida`, `unidad_1`, `unidad_2` o `cierre`. Por ejemplo:

   ```
   https://tu-dominio/lti/launch/?momento=bienvenida
   https://tu-dominio/lti/launch/?momento=unidad_1
   https://tu-dominio/lti/launch/?momento=unidad_2
   https://tu-dominio/lti/launch/?momento=cierre
   ```

   Django lo usa para saber qué pregunta de apertura de Clara pedirle a n8n y para guardar el historial de chat por separado en cada página — si falta o no es uno de esos valores, el lanzamiento falla con un error explicativo. (Se usa el query param y no un Custom Parameter LTI porque estos últimos se configuran a nivel del Developer Key en Canvas —global— y no varían por página sin Deep Linking.)
9. Instalar la herramienta en un curso de prueba y abrirla — debería aterrizar en `chat_frame.html`.

## Panel de administración (`/admin/`)

Desde ahí se gestiona todo lo que no requiere tocar código:

- **ClaraMoment / ClaraMessage** (solo lectura): la pregunta de apertura, el contador de mensajes/tokens y el historial de cada estudiante por página/unidad — lo que hoy consume el widget.
- **ClaraMomentLimit** (inline dentro de cada **Course**, o standalone): cuántos **mensajes** y cuántos **tokens** puede consumir el estudiante en cada momento (`bienvenida`/`unidad_1`/`unidad_2`/`cierre`) de ese curso, y el mensaje de cierre que ve al alcanzar cualquiera de los dos. Sin configurar nada, se usa el default (8 mensajes, sin tope propio de tokens). **Importante**: el webhook `/clara/responder` de n8n tiene su propio tope fijo de 8 mensajes en su lógica interna — un `message_limit` **menor** a 8 aquí sí corta antes (Django deja de llamar a n8n); uno **mayor** a 8 no tiene efecto porque n8n corta primero. El mensaje que hace llegar el contador al límite sí se manda a n8n y obtiene una respuesta real; los intentos siguientes ya no se envían y el estudiante ve directamente el mensaje de cierre configurado.
- **N8nFlow** / **PromptTemplate**: el mecanismo genérico y configurable del flujo anterior (selector de plantillas + webhook por curso). El widget ya no los usa — los webhooks fijos de Clara (`/clara/apertura` y `/clara/responder`, ver `CLARA_APERTURA_URL`/`CLARA_RESPONDER_URL`) los reemplazaron —, pero se dejan por si se necesita un flujo configurable a futuro.
- **Course**: límite de tokens del curso completo, sumando todos los momentos (vacío = usa `DEFAULT_COURSE_TOKEN_LIMIT`). Es un tope aparte y adicional al de `ClaraMomentLimit` por unidad — se evalúan los dos.
- **CourseEnrollment**: aquí se ve si el chat de un estudiante está deshabilitado por límite, y hay una acción para reactivarlo manualmente.

## Despliegue en la VPS (sin Docker)

Ver `deploy/lti-chat.service` (unidad de systemd) y `deploy/nginx.conf`
(server block). Resumen de los pasos en la VPS:

```bash
# Paquetes del sistema
sudo apt update && sudo apt install -y python3-venv postgresql nginx redis-server certbot python3-certbot-nginx

# Base de datos
sudo -u postgres createuser lti_chat -P
sudo -u postgres createdb lti_chat_scala -O lti_chat

# Código
sudo mkdir -p /srv/lti-chat && sudo chown $USER: /srv/lti-chat
git clone <tu-repo> /srv/lti-chat
cd /srv/lti-chat
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completar con los valores reales
mkdir -p keys run
openssl genrsa -out keys/lti_tool_private.pem 2048
openssl rsa -in keys/lti_tool_private.pem -pubout -out keys/lti_tool_public.pem

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser

# Servicio
sudo cp deploy/lti-chat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lti-chat

# Nginx + TLS
sudo cp deploy/nginx.conf /etc/nginx/sites-available/lti-chat.conf
sudo ln -s /etc/nginx/sites-available/lti-chat.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d lti-chat.tudominio.com
sudo nginx -t && sudo systemctl reload nginx

# Firewall
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

Para despliegues siguientes: `./deploy/deploy.sh` (git pull + migrate +
collectstatic + reinicio del servicio).

## Qué falta (ver el documento de alcance para el detalle completo)

- **En n8n** (no es código de este repo, pero es un prerrequisito): agregar
  la validación del header `X-Internal-Token` a `/clara`, conectar WF4
  (RAG real) vía `Execute Workflow`, y devolver el desglose
  `tokens.{prompt,completion,total}` en vez de `tokens_used` — este
  proyecto ya funciona con cualquiera de las dos formas (ver
  `apps/chat/services/n8n_client.py`), pero el desglose da mejor
  trazabilidad.
- **Migrar Supabase → PostgreSQL propio** del lado de n8n (sección 9 del alcance).
- **Fase 2**: panel de reporting para docentes/coordinación, aviso previo
  al estudiante al acercarse al límite (ya se calcula `usage.warning` en
  la API; falta la UI), reintentos/circuit-breaker si n8n está caído.
- **Fase 3**: streaming de la respuesta (SSE/WebSockets) si la latencia
  síncrona resulta un problema, soporte a más de una institución/`LtiTool`.
- Tests automatizados: el proyecto se probó manualmente end-to-end
  (lanzamiento simulado, plantillas, mensajes, bloqueo por límite) pero
  no trae un test suite todavía.
