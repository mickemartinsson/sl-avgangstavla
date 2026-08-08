# SL-avgångstavla — migration Loopia → edge-a24-1 (design)

**Datum:** 2026-06-22
**Status:** Godkänd design, ej implementerad
**Repo:** `Produktion/sl-avgangstavla` (Gitea `micke/sl-avgangstavla`, GitHub-mirror)
**Branch:** `feat/edge-migration`

## Bakgrund & problem

5 Vaka F100-info-skärmar i BRF Himmelsbågen visar SL-avgångar via
`https://slinfo.brfhimmelsbagen.se/display.html`. Produktionen kör idag på
**Loopia shared hosting**: en `update.php` triggas av Loopia-cron var 5:e minut,
hämtar SL:s öppna API och skriver en statisk `display.html`.

Skärmarna har återkommande hängt sig på **502-fel**. Hela fix-historiken
(502-fix v1, DOM-swap v2, jitter, self-healing) är **klient-sidiga plåster** för
att överleva Loopias 502:or. Datakällan (SL:s API) och skärmarna är friska —
**roten är Loopia shared hosting.**

## Mål

Flytta hostingen bakom **samma URL** till egen, frisk infra så att 502-problemet
försvinner vid roten, med absolut minsta möjliga felyta mellan skärm och fil.
Trafiken är försumbar (5 skärmar, en liten statisk fil var 5:e minut).

## Icke-mål

- Ingen ändring av skärmarnas Vaka-config (URL behålls).
- Ingen ändring av utseende eller beteende för tittaren.
- V2-spåret (konfigurerbar `settings.php`/`search.php`) tas **inte** vidare.

## Värd: edge-a24-1 (statslös edge)

VPS:en är `edge-a24-1` (HostUp, publik `64.112.127.253`, tailnet
`100.76.88.121`, tag:edge, Debian 13). Den är byggd som en **ren, statslös
Caddy-proxy** (publik TLS via Let's Encrypt TLS-ALPN-01 → proxar över tailnet
till A24). Principen *"datan stannar på A24, edgen är statslös"* finns för att
skydda SM2026:s deltagar-PII/tokens.

**SL-tavlan har ingen sådan data** — det är SL:s publika öppna API renderat till
en statisk HTML-fil. Ingen PII, inga secrets, ingen databas. Därför väljs en
självständig lösning på edgen (alternativ B nedan): den minsta felytan vinner
när datan ändå är publik och fullt reproducerbar från repot.

### Övervägda alternativ

- **A) Standard edge-mönster — generator på A24, edge `reverse_proxy` (live).**
  Trogen arkitekturen, men serve-vägen beror live på tailnet + A24-container =
  fler 502-källor, tvärtemot målet. Avfärdad.
- **B) Självständigt på edgen — VALD.** Generator (systemd-timer) skriver statisk
  fil på edgen; Caddy `file_server` serverar den. Noll live-beroenden mellan
  skärm och fil. Liten "state" på edgen, men 100% publik data, reproducerbar.
- **C) Hybrid — generator på A24, pushar filen till edgen via rsync.** Kulsäker
  serve-väg + logik på A24, men en push-kanal (SSH-nyckel A24→edge) till. Inte
  värt extra-delarna när datan är publik. Avfärdad.

## Arkitektur (alternativ B)

```
SL öppna API ──(var 5:e min, på edgen)──► generate_slinfo.py ──► /var/www/slinfo/display.html (atomisk write)
                                                                          │
slinfo.brfhimmelsbagen.se (A → 64.112.127.253) ──► edge Caddy file_server ─┘
                                                                          │
                                          5 Vaka-skärmar ──(DOM-swap var 5:e min, oförändrat)──► renderar
```

Två oberoende 5-min-loopar (server-regen + klient-fetch) — exakt nuvarande
modell. Ingen live-proxy, inget tailnet-/A24-beroende i serve-vägen.

## Komponenter

### 1. `edge/generate_slinfo.py`
Python stdlib (inga deps, ingen PHP på edgen). Porterar `web/update.php`:

- Hämtar de två SL-site-URL:erna:
  - Nacka Trafikplats: `https://transport.integration.sl.se/v1/sites/4062/departures?transport=BUS&direction=2&forecast=90`
  - Nacka Strand: `https://transport.integration.sl.se/v1/sites/4031/departures?direction=2&forecast=90`
- Parsar avgångar (tid `expected`/`scheduled`, destination, linje, typ Buss/Båt).
- Renderar `display.html` från **exakt samma HTML/CSS/DOM-swap-mall som idag**
  (byte-för-byte; bara fetch+parse översatt från PHP). Mallen är tunad för
  Axema C205 med inline-stilar — får inte ändras.
- **Atomisk write**: skriv temp-fil + `os.replace()` till målet.
- Körs som oprivilegierad användare `slinfo`.

### 2. `systemd/slinfo-generator.service` + `.timer`
- `oneshot`-service som kör generatorn.
- Timer var 5:e minut: `OnCalendar=*:0/5` + `RandomizedDelaySec=20`
  (liten spridning så vi inte slår SL exakt på minutgränsen), `Persistent=true`.
- `User=slinfo`.
- (Valfritt senare: `OnFailure=` → Bark.)

### 3. Caddy-vhost
`slinfo.brfhimmelsbagen.se` → `file_server` mot `/var/www/slinfo`. Auto-TLS via
Let's Encrypt TLS-ALPN-01 (samma mönster som edgens övriga vhosts). Läggs i
edgens versionshanterade Caddy-config (exakt placering bekräftas mot edgens
repo/Caddyfile vid implementation, jämför `a24-offsite-edge`).

### 4. DNS
Repointa A-posten `slinfo.brfhimmelsbagen.se` hos Loopia → `64.112.127.253`.
Via Loopia DNS-API (creds BW "Martinsson API" / `~/.config/loopia/env`) eller
Loopia-panelen. Zonen `brfhimmelsbagen.se` är en annan zon än `pistolsm2026.nu`
— verifiera att samma API-creds har rättigheter på den, annars panelen.

## Filsystem & behörigheter

- Output-mapp: `/var/www/slinfo/`, ägd av `slinfo`-användaren; Caddy läser den.
- Senaste goda filen ligger kvar mellan körningar (se felhantering).

## Felhantering (här löses 502 vid roten)

- **Per-site last-good (beslut 2026-06-22):** de två hållplatserna hämtas
  **oberoende av varandra**. Varje lyckad hämtning cachas (rader per site) i
  `/var/lib/slinfo/cache.json`. Faller en site (timeout / non-200 / JSON-fel)
  renderas den **friska siten live** medan den fallna visar sina **senaste goda
  rader ur cachen**; servicen loggar warning + exit 1. En ihållande outage av
  *en* site gör alltså inte den andra inaktuell. (Detta fixar samtidigt den
  latenta bug i nuvarande `update.php` som blankar skärmen vid API-fel.)
- **Båda faller, cache finns** → båda visar last-good (giltig sida), exit 1.
- **Båda faller, ingen cache (t.ex. allra första körningen)** → minimal giltig
  sida så skärmen alltid har något att visa, exit 1.
- **Caddy/host** → statisk fil + systemd-managed Caddy; en frisk `file_server`
  502:ar inte.
- **Klient** → DOM-swap-self-healing (jitter 30–90s retry) behålls oförändrat i
  mallen.

## Övervakning

Befintlig `slinfo-probe.sh` på pve12 (var 2:e min → Bark vid incident, grupp
`SL-Avgangstavla`) funkar oförändrat — den testar publika URL:en, host-agnostiskt.

Valfritt senare (YAGNI nu): färskhetskoll på "Uppdaterad"-timestampen i filen +
`OnFailure=`-Bark på timern.

## Testning

- **Enhet:** `parse_rows`/render mot infångade SL-API-JSON-fixtures +
  golden-HTML-jämförelse → bevisar att Python-porten ger mall-identisk output
  mot nuvarande PHP (regression-skydd för C205-mallen; timestamp maskeras).
- **Smoke (på edgen):** kör generatorn en gång → `curl` publika URL → assert
  200 + förväntad markup + färsk timestamp + giltigt TLS-cert.
- **Cutover-validering:** efter DNS+cert, ladda om EN skärm via Vaka
  Informationscenter → bekräfta render + self-heal → sen alla 5.

## Cutover

1. Deploya generator + timer på edgen (producerar filen lokalt direkt).
2. Repointa A-posten hos Loopia → vänta tills DNS är konsistent över
   **ns1 + ns2 + 1.1.1.1** *innan* Caddy-vhosten läggs (annars bränns
   LE rate-limit — känd edge-gotcha).
3. Lägg Caddy-vhosten → cert provisioneras (~10–15 s) → verifiera publika URL.
4. Tvinga EN skärm att ladda om (Vaka Informationscenter → ta bort + återlägg
   webresursen → dra in i spellistor). Skärmarna sitter idag fast på Loopias
   502-felsida och behöver EN manuell omladdning; därefter self-healing.
   Sen alla 5.
5. **Soak:** låt Loopia-filerna ligga kvar orörda som rollback i ~några dygn;
   stoppa Loopia-cronen. Riv Loopia-delen när edge är bevisat stabilt.

## Rollback

Repointa A-posten tillbaka till Loopia-IP (Loopia-filerna + cert kvar under
soak) → snabb revert. Vaka-config oförändrad i båda riktningar.

## Repo / branch

- Generator, systemd-units, denna spec + runbook: `Produktion/sl-avgangstavla`,
  branch `feat/edge-migration`. Merge till prod-branch (`prod-sync`) efter
  validerad cutover — inte före.
- Caddy-vhosten: edgens config (`a24-offsite-edge` eller motsvarande). Exakt
  placering bekräftas mot edgens Caddyfile vid implementation.

## Öppna punkter att bekräfta vid implementation

- Edgens Caddyfile-struktur/repo (hur befintliga vhosts är organiserade).
- Att tag:edge-noden får nå utåt mot SL-API:t (ska fungera; ren utgående HTTPS).
- Att BW "Martinsson API"-creds har DNS-rättigheter på zonen
  `brfhimmelsbagen.se` (annars Loopia-panelen).
