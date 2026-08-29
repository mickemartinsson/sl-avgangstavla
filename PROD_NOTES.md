# Produktionsnoteringar — slinfo.brfhimmelsbagen.se

> **Produktion är `edge.a24.martinsson.eu` sedan juni 2026.** Loopia är avvecklat
> som produktionsplattform. `web/`-katalogen finns kvar som dormant rollback —
> se [Rollback till Loopia](#rollback-till-loopia-dormant).

## Så ser produktionen ut

| | |
|---|---|
| Värd | `edge.a24.martinsson.eu` (`64.112.127.253`) — se [a24-offsite-edge](https://gitea.a24.martinsson.eu/A24/a24-offsite-edge) §5a |
| Serverad fil | `/var/www/slinfo/display.html`, statiskt via Caddy (`edge/caddy/slinfo.brfhimmelsbagen.se.caddy`) |
| Generator | `edge/generate_slinfo.py`, körd av `slinfo-generator.timer` (`OnCalendar=*:0/5`, `RandomizedDelaySec=20`) |
| Publik URL | **`https://slinfo.brfhimmelsbagen.se/display.html`** |
| Bevakning | `a24-infra/services/slinfo-uptime/slinfo-probe.sh` + edge-monitorns `monitor/probes.toml` — **båda probar `/display.html`** |

Mätt 2026-08-29 08:44 CEST: `display.html` HTTP 200, 10 907 byte,
`last-modified` 4 min 43 s gammal. Generatorn ligger i fas med timern.

### URL:er

| URL | Svar |
|---|---|
| `https://slinfo.brfhimmelsbagen.se/` | **200** — serverar `display.html` |
| `https://slinfo.brfhimmelsbagen.se/display.html` | **200** |
| `https://slinfo.brfhimmelsbagen.se/index.php` | 404 — ingen PHP på edgen |

Roten fungerar tack vare `index display.html` i `file_server`-blocket
(satt 2026-08-29). **Mellan juni och 2026-08-29 gav roten 404** — vhosten hade
inget `index`-direktiv och `index.php`-redirecten från Loopia följde inte med
migrationen.

### Skärmar (Axema C205) — verifierade i accessloggen 2026-08-29

Skärmarnas URL ligger i Axemas spellista, inte i något repo. Den lästes därför
**ur Caddys accessloggar** i stället (2 h fönster, 05:06–07:06 UTC):

| | |
|---|---|
| Klient-IP | `84.217.120.115` (BRF:ens publika IP) |
| Requests | 645, sammanhängande — **längsta lucka 28 s** |
| URI | `/display.html?v=2` — **645 av 645. Aldrig roten.** |
| Svar | 525 × `304 Not Modified`, 120 × `200` |
| User-Agent | `…AppleWebKit/538.1 … reservationterminal Safari/538.1` |
| Referer | `https://tvatt.brfhimmelsbagen.se/informationterminal/` |

**Tavlorna fungerar och har gjort det hela tiden.** De sitter inbäddade i
tvättportalens informationsterminal-sida.

Gap-mönstret (par om 5–6 s och 10–11 s, sedan 28 s, ~96 cykler på 2 h) är
konsekvent med **5 klienter som pollar var ~75:e sekund, förskjutna** — men
enheterna ligger bakom NAT och kan inte särskiljas per IP, så antalet är
härlett, inte bevisat.

De många 304:orna betyder att `If-None-Match`/`If-Modified-Since` fungerar:
skärmarna drar inte ner hela sidan varje gång.

> **Not om `index display.html`:** direktivet sattes 2026-08-29 för att roten
> gav 404. Loggen visar att skärmarna aldrig efterfrågat roten — det var alltså
> en latent lucka som stängdes, inte ett avbrott som lagades.

### Loopias cron — avstängd 2026-08-29 ✅

Loopia-erans cron låg kvar och körde mot edgen efter DNS-omläggningen i juni
2026:

```
*/5 * * * *   curl -s https://slinfo.brfhimmelsbagen.se/update.php > /dev/null
```

`update.php` finns inte på edgen, så varje anrop gav `404` — ~288 förgäves
anrop per dygn i drygt två månader. Mikael tog bort jobbet i BRF:ens
Loopia-konto 2026-08-29.

**Verifierat i accessloggen:** sista träffen från `93.188.1.201`
(UA `Loopia Cronrunner v1.2 libwww-perl/6.83`) var `07:05:01 UTC`. Dessförinnan
gick den på sekunden var 5:e minut. Därefter **tre uteblivna cykler i rad**
(07:10, 07:15, 07:20) och noll nya `404` överhuvudtaget.

Kvarvarande 404 i loggen kommer från internetscannrar och manuella prober —
det är brus, inte ett flöde.

## Rollback till Loopia (dormant)

`web/` bär den hårdkodade `update.php` som körde på Loopia, **inklusive
502-fixen** (`git show main:web/update.php` = sha `c3c3ed39…`, byte-identisk med
det som senast låg i produktion där).

Rollback är alltså funktionellt möjlig, med två kända avvikelser:

1. **Trafikstörningar försvinner.** `edge/generate_slinfo.py` visar STOPP/INFO
   ovanför tavlan (SL:s deviations-API, filter `importance_level >= 6`).
   `web/update.php` saknar detta. Portning av `filter_alerts` + `alerts_html` +
   `__ALERTS__` till PHP krävs för likvärdig rollback.
   API: `https://deviations.integration.sl.se/v1/messages?future=true&transport_mode=METRO&transport_mode=TRAIN&transport_mode=TRAM&transport_mode=SHIP`
2. **Loopia flappade 502** i shared hosting — grundskälet till migrationen.

### Historisk deploy-sekvens (Loopia)

```bash
# SSH: 2r8w99@ssh.loopia.se
scp web/update.php 2r8w99@ssh.loopia.se:slinfo.brfhimmelsbagen.se/public_html/update.php
# Backup skapas på servern: update.php.bak-YYYYMMDD-HHMMSS
```

Cron på Loopia: `*/5 * * * * curl -s https://slinfo.brfhimmelsbagen.se/update.php > /dev/null`

> ⚠️ **Vid rollback måste cron-jobbet återskapas.** Det togs bort 2026-08-29
> (se ovan). Utan det uppdateras aldrig `display.html` på Loopia — tavlan
> fryser på sitt sista innehåll i stället för att gå ned, vilket är svårare
> att upptäcka.

502-fixen i `<script>`-blocket, för referens:
`fetch(..., {method:'HEAD'})` i stället för full GET, och `setTimeout(reload, retryDelay())`
med 10–30 s slumpad väntetid så att alla 5 skärmar inte retryar i lockstep.

## Avvecklat

### Branchen `prod-sync` — pensionerad 2026-08-29

`prod-sync` speglade Loopia-produktionen och användes som referens vid ändringar
mot den. När produktionen flyttade till edgen i juni 2026 upphörde det den
speglade att existera, och grenen slutade uppdateras.

Vid pensioneringen låg den 17 commits bakom `main` — de 17 var edge-migrationen
själv. Grenen bar **noll unikt innehåll**: alla sex `web/`-filer byte-identiska
med `main`, och dess tipp `6ae9c90` är förfader till `main`.

Bevarad som taggen `pensionerad/prod-sync`. Återskapa vid behov med
`git checkout -b prod-sync pensionerad/prod-sync`.

### `slinfo-render` (PNG till Loopia) — POC byggd, aldrig driftsatt

Ett tidigare försök att komma runt Loopias 502:or var att rendera tavlan som
960×1080 PNG i en LXC och pusha till Loopia. Ansatsen ersattes av
edge-migrationen.

**Koden finns kvar** som taggen `poc/slinfo-render` (3 commits, 2026-05-02,
pushad till origin) med `render/render.py`, `deploy.sh`, systemd-units och
mall. Hämta med `git checkout -b <namn> poc/slinfo-render`.

Det som aldrig blev av var *driftsättningen*: branchen `pdf-pipeline` skapades
aldrig, LXC:n på pve12 skapades aldrig, och `tavlan.png` har aldrig serverats
(404 än idag). Infra-bootstrappen `a24-infra/services/slinfo-render/` — vars
setup-script klonade just den obefintliga `pdf-pipeline`-branchen — togs bort
2026-08-29.
