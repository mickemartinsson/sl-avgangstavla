# Produktionsnoteringar — slinfo.brfhimmelsbagen.se

## Deploy 2026-04-23: 502-fix på produktionens hårdkodade update.php

### Bakgrund

- Loopia-produktionen kör en **hårdkodad** version av `update.php` (NT+NS URLs
  i koden), inte den konfigurerbara v2 som finns på `main` (commit 1f01d6a).
- Den konfigurerbara v2 (`settings.php` + `search.php` + `config.json`) har
  aldrig deployats på brfhimmelsbagen.
- Efter ca 1 månads drift återkom 502-problem från Loopia shared hosting.

### Den här branchen (prod-sync)

`prod-sync` speglar det som faktiskt kör i produktion PLUS 502-fixen.
Använd den här branchen som referens vid framtida ändringar mot produktionen
tills v2 migreras.

### 502-fix i `<script>`-blocket

Två minimala ändringar utan utseende-/funktionspåverkan för tittaren:

1. `fetch('display.html', { cache:'no-cache' })` → `fetch('display.html', { method:'HEAD', cache:'no-cache' })`
   - HEAD drar bara headers, inte hela display.html. Halverar serverlast per reload.
2. `setTimeout(reload, 10000)` → `setTimeout(reload, retryDelay())` där
   `retryDelay()` ger 10–30 s slumpad väntetid.
   - Förhindrar att alla 5 skärmar retryer en 502:ande server i lockstep.

### Deploy-sekvens

```bash
# SSH: 2r8w99@ssh.loopia.se  (nyckel: ~/.ssh/id_ed25519, fingerprint kZoM…EVuE)
scp /tmp/slinfo-prod/update.php \
    2r8w99@ssh.loopia.se:slinfo.brfhimmelsbagen.se/public_html/update.php

# Backup skapas på servern innan skrivning:
# update.php.bak-YYYYMMDD-HHMMSS
```

### Cron-jobb på Loopia

```
*/5 * * * *   curl -s https://slinfo.brfhimmelsbagen.se/update.php > /dev/null
```

### Skärmar (Axema C205)

5 skärmar i spellistor som visar `https://slinfo.brfhimmelsbagen.se/`
(index.php redirectar till display.html).

## Loopia-PHP rollback saknar deviations (sedan 2026-06-24)

`edge/generate_slinfo.py` på edge-a24-1 har stöd för system-störningar
(STOPP/INFO-rutor överst, hämtade från SL:s deviations-API, filter
`importance_level >= 6`). `web/update.php` (Loopia-versionen som är
*dormant rollback*) har **inte** detta stöd.

Om rollback till Loopia behövs:
1. Tavlan kommer förlora STOPP-rutorna (avgångstabellerna kvar)
2. Portning av `filter_alerts` + `alerts_html` + `__ALERTS__` till PHP
   krävs innan rollback är funktionellt likvärdig
3. SL API:t som används: `https://deviations.integration.sl.se/v1/messages?future=true&transport_mode=METRO&transport_mode=TRAIN&transport_mode=TRAM&transport_mode=SHIP`
