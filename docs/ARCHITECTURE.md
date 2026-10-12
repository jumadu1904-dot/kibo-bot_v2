# Kibo Bot V2: Arquitectura

Complementa [SCOPE.md](SCOPE.md) (què fa el bot). Aquest document descriu **com** està construït.

## Stack
| Peça | Tria |
|---|---|
| Llenguatge | Python 3.12 |
| Bot | python-telegram-bot 21, en mode webhook (sense JobQueue: vegeu "Planificador") |
| Servidor web | FastAPI + Uvicorn (webhook de Telegram, `/check-reminders`, callback d'OAuth, health check) |
| Base de dades | Postgres (Neon, pla gratuït) + SQLAlchemy 2 (async, asyncpg) + Alembic. En local, SQLite (aiosqlite) per no necessitar cap servei extern |
| Configuració | pydantic-settings (`.env`) |
| IA | Gemini (text i àudio en una sola crida, sortida estructurada), darrere d'una interfície |
| Temps i geocodificació | Open-Meteo (sense clau; també retorna la zona horària) |
| Notícies | Google News RSS per tema i idioma (parsejat amb `xml.etree`, no `feedparser`, per no afegir una dependència només per llegir `<title>`/`<link>` — igual que la resta de `clients/`, sense SDKs) |
| Google | Calendar API + Tasks API, amb OAuth per usuari |
| Hosting | Render (pla gratuït, *Web Service*), HTTPS. Cron extern (cron-job.org) cada 5 min → `GET /check-reminders` |

## Principis (el que va fallar a la V1)
1. **Capes separades**: els `handlers` (Telegram) només parlen amb els `services`. Els `services` parlen amb `repositories` (BD) i amb `clients` (APIs externes). Cap handler crida una API ni toca la BD directament.
2. **Multiusuari des del primer dia**: res de `token.json` global. Cada usuari té les seves dades i els seus tokens.
3. **Tot el que s'ha d'enviar més tard viu a la BD** (recordatoris i hores del briefing). Cap temporitzador intern de Python: el pla gratuït de Render adorm el procés als 15 minuts d'inactivitat, així que qualsevol `JobQueue` o `asyncio.sleep` en segon pla simplement no s'executaria mentre el bot dorm. Un cron extern desperta el bot i li fa mirar la BD (vegeu "Planificador").
4. **Cap text hardcoded**: tots els missatges surten dels fitxers d'`i18n`.
5. **Cap secret al repositori**: només `.env` (i `.env.example` com a plantilla) i un `.gitignore` des del primer commit.

## Estructura de carpetes
```
kibo-bot-V2/
├── docs/                    SCOPE.md, ARCHITECTURE.md
├── src/kibo/
│   ├── main.py              App FastAPI; el lifespan arrenca i atura la Application de PTB
│   ├── config.py            Settings (pydantic-settings)
│   ├── web/                 routes: /telegram/webhook, /check-reminders, /oauth/google/callback, /health
│   ├── bot/
│   │   ├── app.py           Construeix la Application (concurrent_updates=True) i registra els handlers
│   │   ├── handlers/        start (onboarding), menu, agenda, reminders, tasks,
│   │   │                    briefing, settings, smart_input (text lliure i veu)
│   │   ├── keyboards/       Constructors d'inline keyboards
│   │   └── callbacks.py     Format dels callback_data (p. ex. "menu:agenda", "task:done:<id>")
│   ├── services/            onboarding, calendar, tasks, reminders, briefing,
│   │                        weather, news, interpreter (IA), google_auth,
│   │                        reminders_cron (la feina que dispara el cron extern)
│   ├── clients/             gemini, google_api, open_meteo, google_news
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── repositories/
│   └── i18n/                en.json, es.json, ca.json + helper t(key, lang, **kwargs)
├── migrations/              Alembic
├── tests/
├── .env.example  .gitignore  pyproject.toml  requirements.txt  render.yaml  README.md
```

## Model de dades
- **User**: `telegram_id`, `lang`, `city`, `lat`, `lon`, `timezone`, `briefing_time` (hora local o null), `briefing_blocks` (JSON), `news_topics` (JSON), `onboarding_step`, `created_at`
- **GoogleAccount**: `user_id`, `refresh_token` (xifrat amb Fernet), `scopes`, `connected_at`
- **Reminder**: `id`, `user_id`, `text`, `due_at` (UTC), `status` (pending/sent/cancelled), `google_event_id` (nullable)
- **LocalTask**: les tasques i notes quan Google no està connectat
- **PendingAction**: el contingut de les targetes de confirmació de la IA (`payload` JSON i `expires_at`)

## Fluxos clau
**OAuth de Google (per usuari)**
1. L'usuari prem "Connecta Google". El bot genera una URL de Google amb un `state` signat (HMAC de `telegram_id` + nonce, amb caducitat).
2. Google redirigeix a `/oauth/google/callback`. Allà es verifica el `state`, es canvia el codi per tokens i es desa el refresh token xifrat.
3. El servidor envia per Telegram el missatge "✅ Google connectat" i torna el menú.
- L'app de Google Cloud queda en mode *Testing*, amb fins a 100 usuaris de prova. És suficient per a ús propi i per a la demo.

**Entrada intel·ligent (text o veu)**
1. `smart_input` rep el text o l'àudio i crida `interpreter.parse(input, context_usuari)`.
2. Gemini retorna una llista d'accions tipades amb Pydantic: `CreateEvent`, `CreateReminder`, `CreateTask`, `CreateNote`, `Query`. Les dates es resolen amb la zona horària de l'usuari.
3. Es desa una `PendingAction` i es mostra la targeta [✅ Confirmar] [✏️ Editar] [❌ Cancel·lar].
4. En confirmar, els services escriuen a Google (o a la BD local) i programen el recordatori.

**Planificador: cron extern en lloc de temporitzadors interns**
- Res de `JobQueue` ni de `scheduler.rehydrate()` a l'arrencada: amb el pla gratuït de Render, el procés s'adorm als 15 minuts sense trànsit HTTP, així que qualsevol temporitzador viu dins del procés simplement no dispararia mentre dorm.
- Un servei extern (**cron-job.org**) fa un `GET /check-reminders?token=<CRON_SECRET>` cada 5 minuts. Aquesta trucada, a més de comprovar els recordatoris, manté el servei despert (l'interval és més curt que els 15 minuts d'inactivitat que calen perquè s'adormi).
- L'endpoint respon **de seguida** (`{"ok": true, "status": "queued"}`) i llança el treball pesant (`services.reminders_cron.run_due_checks`, que consultarà recordatoris i briefings pendents a la BD i cridarà les APIs) com a tasca en segon pla (`asyncio.create_task`), perquè el cron no faci `timeout` i perquè aquesta trucada no bloquegi el processament d'altres missatges de Telegram.
- Un `asyncio.Lock` evita que dues execucions se solapin si una comprovació (temps + calendari + notícies de tots els usuaris) triga més de 5 minuts.
- Amb una sola instància (com al pla gratuït) no hi ha risc d'enviaments duplicats.

**Mode d'execució: sempre webhook**
- El *long polling* no serveix a Render: el pla gratuït adorm el servei quan no rep trànsit HTTP, i un bucle de polling intern no compta com a trànsit HTTP entrant, així que no evitaria l'adormiment.
- En producció (`BOT_MODE=webhook`), Telegram truca a `POST /telegram/webhook`, que confirma a l'instant i deixa el processament (que pot trigar per les crides a Gemini o Google) al bucle intern de PTB, ja en marxa gràcies a `concurrent_updates=True`.
- En desenvolupament local es pot seguir fent servir `BOT_MODE=polling` (és més senzill perquè no cal exposar cap URL pública), però l'entorn de Render sempre és `webhook`.

**Persistència: Postgres extern (Neon), no SQLite**
- El pla gratuït de Render **no té disc persistent**: el sistema de fitxers és efímer i es reinicia a cada desplegament. Un fitxer SQLite no hi sobreviuria.
- En producció fem servir **Neon** (Postgres gratuït, sense caducitat): es connecta amb `DATABASE_URL=postgresql+asyncpg://<usuari>:<contrasenya>@<host>/<bd>?ssl=require`. Neon "pausa" el projecte si no té activitat i es desperta sol a la primera consulta, cosa que encaixa amb un bot que també es pot adormir.
- En **desenvolupament local** es continua fent servir SQLite (`sqlite+aiosqlite:///./kibo.db`, el valor per defecte) perquè no calgui cap servei extern només per provar el bot. El codi (SQLAlchemy + Alembic) és el mateix per als dos casos; només canvia `DATABASE_URL`.

## Variables d'entorn (`.env.example`)
`TELEGRAM_TOKEN`, `BOT_MODE`, `PUBLIC_URL`, `WEBHOOK_SECRET`, `DATABASE_URL`, `CRON_SECRET`, `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ENCRYPTION_KEY`, `STATE_SECRET`

## Fases d'implementació
| Fase | Contingut | Com es comprova |
|---|---|---|
| F0: Esquelet | Repositori, config, FastAPI + PTB (webhook o polling), `/check-reminders`, BD + Alembic, i18n, `/start` bàsic | El bot respon en mode polling en local |
| F1: Onboarding i menú | Idioma, ubicació (Open-Meteo), briefing, temes, menú inline que s'edita a si mateix, Configuració | Un usuari nou completa el flux i les dades queden a la BD |
| F2: Google | OAuth per usuari, Agenda (avui i setmana), Tasques (llistar, afegir, feta) | Es connecta el compte i es veuen els esdeveniments i tasques reals |
| F3: IA i recordatoris | Interpreter de Gemini (text i veu), targeta de confirmació, recordatoris i `reminders_cron.run_due_checks` | **El guió del vídeo demo funciona de principi a fi** |
| F4: Briefing | Temps, agenda, tasques i notícies RSS, enviament diari via `/check-reminders` i `/briefing_now` de depuració | El briefing arriba a l'hora correcta |
| F5: Producció | Crear el projecte a Neon, desplegament a Render (webhook + cron-job.org), README per a Fiverr, tests, gravació del vídeo | El bot funciona 24/7 i el vídeo està gravat |
