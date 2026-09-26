# Kibo Bot V2: Arquitectura

Complementa [SCOPE.md](SCOPE.md) (què fa el bot). Aquest document descriu **com** està construït.

## Stack
| Peça | Tria |
|---|---|
| Llenguatge | Python 3.12 |
| Bot | python-telegram-bot 21 (amb JobQueue) |
| Servidor web | FastAPI + Uvicorn (webhook de Telegram, callback d'OAuth, health check) |
| Base de dades | SQLite + SQLAlchemy 2 (async, aiosqlite) + Alembic per a les migracions |
| Configuració | pydantic-settings (`.env`) |
| IA | Gemini (text i àudio en una sola crida, sortida estructurada), darrere d'una interfície |
| Temps i geocodificació | Open-Meteo (sense clau; també retorna la zona horària) |
| Notícies | Google News RSS per tema i idioma (feedparser) |
| Google | Calendar API + Tasks API, amb OAuth per usuari |
| Hosting | Railway: 1 rèplica, volum persistent per a SQLite, HTTPS |

## Principis (el que va fallar a la V1)
1. **Capes separades**: els `handlers` (Telegram) només parlen amb els `services`. Els `services` parlen amb `repositories` (BD) i amb `clients` (APIs externes). Cap handler crida una API ni toca la BD directament.
2. **Multiusuari des del primer dia**: res de `token.json` global. Cada usuari té les seves dades i els seus tokens.
3. **Tot el que s'ha d'enviar més tard viu a la BD** (recordatoris i hores del briefing). El planificador es reconstrueix a partir de la BD cada vegada que el bot arrenca.
4. **Cap text hardcoded**: tots els missatges surten dels fitxers d'`i18n`.
5. **Cap secret al repositori**: només `.env` (i `.env.example` com a plantilla) i un `.gitignore` des del primer commit.

## Estructura de carpetes
```
kibo-bot-V2/
├── docs/                    SCOPE.md, ARCHITECTURE.md
├── src/kibo/
│   ├── main.py              App FastAPI; el lifespan arrenca i atura la Application de PTB
│   ├── config.py            Settings (pydantic-settings)
│   ├── web/                 routes: /telegram/webhook, /oauth/google/callback, /health
│   ├── bot/
│   │   ├── app.py           Construeix la Application i registra els handlers
│   │   ├── handlers/        start (onboarding), menu, agenda, reminders, tasks,
│   │   │                    briefing, settings, smart_input (text lliure i veu)
│   │   ├── keyboards/       Constructors d'inline keyboards
│   │   └── callbacks.py     Format dels callback_data (p. ex. "menu:agenda", "task:done:<id>")
│   ├── services/            onboarding, calendar, tasks, reminders, briefing,
│   │                        weather, news, interpreter (IA), google_auth, scheduler
│   ├── clients/             gemini, google_api, open_meteo, google_news
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── repositories/
│   └── i18n/                en.json, es.json, ca.json + helper t(key, lang, **kwargs)
├── migrations/              Alembic
├── tests/
├── .env.example  .gitignore  pyproject.toml  Procfile / railway.json  README.md
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

**Planificador**
- Fa servir el JobQueue de PTB. En arrencar, `scheduler.rehydrate()` carrega els recordatoris pendents i un job diari per usuari per al briefing (a l'hora local de cada usuari).
- Requereix **una sola rèplica** a Railway, perquè si n'hi ha més els recordatoris s'envien per duplicat.

**Mode d'execució**
- En desenvolupament: *polling* (sense webhook). El callback d'OAuth va a `http://localhost:8000`, que Google accepta.
- En producció: *webhook* a Railway. El mode es tria amb la variable `BOT_MODE=polling|webhook`.

## Variables d'entorn (`.env.example`)
`TELEGRAM_TOKEN`, `BOT_MODE`, `PUBLIC_URL`, `WEBHOOK_SECRET`, `DATABASE_URL`, `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ENCRYPTION_KEY`, `STATE_SECRET`

## Fases d'implementació
| Fase | Contingut | Com es comprova |
|---|---|---|
| F0: Esquelet | Repositori, config, FastAPI + PTB, BD + Alembic, i18n, `/start` bàsic | El bot respon en mode polling |
| F1: Onboarding i menú | Idioma, ubicació (Open-Meteo), briefing, temes, menú inline que s'edita a si mateix, Configuració | Un usuari nou completa el flux i les dades queden a la BD |
| F2: Google | OAuth per usuari, Agenda (avui i setmana), Tasques (llistar, afegir, feta) | Es connecta el compte i es veuen els esdeveniments i tasques reals |
| F3: IA i recordatoris | Interpreter de Gemini (text i veu), targeta de confirmació, recordatoris i planificador | **El guió del vídeo demo funciona de principi a fi** |
| F4: Briefing | Temps, agenda, tasques i notícies RSS, enviament diari i `/briefing_now` de depuració | El briefing arriba a l'hora correcta |
| F5: Producció | Desplegament a Railway (webhook, volum), README per a Fiverr, tests, gravació del vídeo | El bot funciona 24/7 i el vídeo està gravat |
