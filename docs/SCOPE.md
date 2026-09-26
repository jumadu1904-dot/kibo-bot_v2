# Kibo Bot V2: Abast funcional i UX (sense codi)

## Context
La V1 tenia una estructura incorrecta i la V2 es reconstrueix des de zero a `kibo-bot-V2/` (la carpeta és buida). Abans de parlar de codi o d'arquitectura, fixem **què** fa el bot i **com** el fa servir l'usuari. És per a ús propi, però serà la "demo estrella" de Fiverr (bots de productivitat per a freelancers i particulars). Més endavant hi podria haver una versió per a petits negocis, que queda fora d'aquest abast.

## Decisions preses
| Tema | Decisió |
|---|---|
| Públic | Freelancers i particulars (i el mateix autor) |
| IA | Sí: un LLM interpreta el text lliure i les notes de veu (transcripció i classificació) |
| Idioma | Anglès per defecte, multiidioma (EN / ES / CA) i es tria a l'onboarding |
| Google | OAuth opcional al final de l'onboarding (també des de Configuració) |
| Font de veritat | Amb Google connectat: les tasques van a Google Tasks i els recordatoris o esdeveniments amb hora a Google Calendar. Sense Google: es desen al bot localment |
| Navegació | Un menú inline que s'edita a si mateix, més text lliure o veu en qualsevol moment |

## 1. Funcions principals (menú)
1. **📅 Agenda (Google Calendar)**: veure avui i la setmana, i crear esdeveniments.
2. **⏰ Recordatoris en llenguatge natural**: *"demà a les 9 trucar al dentista"* per text o per veu. El bot notifica a l'hora indicada.
3. **✅ Tasques / notes (Google Tasks)**: afegir tasques, llistar-les i marcar-les com a fetes amb botons.
4. **☀️ Briefing diari**: un missatge automàtic a l'hora triada amb el temps, l'agenda del dia, les tasques pendents i els titulars de notícies.
5. **⚙️ Configuració**: idioma, ciutat i zona horària, briefing, temes de notícies i connexió amb Google.

**Entrada intel·ligent**: qualsevol text o nota de veu fora del menú passa per la IA, que la classifica com a esdeveniment, recordatori, tasca o nota (una frase pot generar-ne diverses). El bot sempre mostra una **targeta de confirmació** amb [✅ Confirmar] [✏️ Editar] [❌ Cancel·lar] abans d'escriure res a Google.

## 2. Flux de l'usuari (/start)
1. Salutació i **idioma** (🇬🇧 🇪🇸 🇨🇦).
2. **Ubicació**: botó "Comparteix la ubicació" (que dedueix la ciutat i la zona horària) o escriure la ciutat.
3. **Briefing**: 7:00 / 8:00 / 9:00 / Personalitzada / Desactivat, i després els temes de notícies (selecció múltiple amb ✔️).
4. **Google**: [Connectar Google Calendar i Tasks] o [Més tard].
5. **Menú principal**: un únic missatge que s'edita en navegar. Cada submenú té [⬅️ Enrere] i [🏠 Menú].
- Tots els passos es poden saltar amb valors per defecte. Un `/start` posterior porta directament al menú.
- Comandes de drecera: `/menu`, `/today`, `/tasks`, `/settings`.

## 3. Dades de l'usuari
- Idioma
- Ciutat, coordenades i zona horària
- Hora del briefing i blocs activats (temps, agenda, tasques, notícies)
- Temes de notícies
- Tokens de Google (xifrats) i l'estat de la connexió
- Recordatoris locals i pendents d'enviar (els que no depenen de Google)

## 4. Vídeo demo de 30 segons: nota de veu → Google
- **0-5s**: `/start`, amb el menú ja configurat.
- **5-18s**: nota de veu: *"Tomorrow at 10 meeting with Laura, and remind me to buy milk"*. El bot transcriu i mostra una targeta amb 📅 un esdeveniment i ✅ una tasca, i l'usuari prem **Confirmar**.
- **18-25s**: pantalla partida en què l'esdeveniment apareix a Google Calendar i la tasca a Google Tasks.
- **25-30s**: arriba la notificació del recordatori. Tancament amb el logo i un "Custom bots on Fiverr".

## Fora d'abast (V2)
Funcions per a negocis (reserves, multiusuari o equips), pagaments i altres integracions (Notion, Todoist).

## Següent pas
Amb aquest abast tancat, passem a l'arquitectura: stack, estructura de carpetes, base de dades, planificador de recordatoris, proveïdors d'IA, del temps i de notícies, i desplegament.

## Verificació (quan hi hagi codi)
Es provarà el guió del vídeo de principi a fi en un bot de proves: l'onboarding complet, una nota de veu que generi un esdeveniment i una tasca visibles a Google, la notificació del recordatori a l'hora correcta segons la zona horària, i el briefing forçat amb una comanda de depuració.
