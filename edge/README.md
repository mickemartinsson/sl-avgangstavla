# SL-avgångstavla — edge-deploy (edge-a24-1)

Generatorn körs som systemd-timer på edge-a24-1 och skriver en statisk
`display.html` som Caddy serverar via `file_server`. Ingen PHP, inga deps
(Python stdlib). Ersätter Loopia shared hosting.

## Komponenter på edgen
- `/opt/slinfo/generate_slinfo.py` — generatorn (körs av timern).
- `/var/www/slinfo/display.html` — output (ägd av user `slinfo`, läst av Caddy).
- `/var/lib/slinfo/cache.json` — senaste goda rader **per hållplats** (för
  last-good vid partiellt API-fel; ägd av `slinfo`, utanför webroot).
- `slinfo-generator.service` + `.timer` — var 5:e min.
- Caddy site-block `slinfo.brfhimmelsbagen.se`.

## Deploy / uppdatering av generatorn
    scp edge/generate_slinfo.py mikael@100.76.88.121:/tmp/generate_slinfo.py
    ssh mikael@100.76.88.121 'sudo install -o slinfo -g slinfo -m 0755 /tmp/generate_slinfo.py /opt/slinfo/generate_slinfo.py && sudo systemctl start slinfo-generator.service && systemctl status slinfo-generator.service --no-pager'

## Diagnostik
- Senaste körning: `journalctl -u slinfo-generator.service -n 20 --no-pager`
- Timer-status: `systemctl list-timers slinfo-generator.timer`
- Färskhet: `curl -s https://slinfo.brfhimmelsbagen.se/display.html | grep Uppdaterad`

## Felhantering
Hållplatserna hämtas oberoende. Faller en (timeout/non-200/JSON-fel) visas
dess senaste goda rader ur `cache.json` medan den friska siten fortsätter
live; servicen loggar VARNING och exitar 1 (syns i journal). Faller båda utan
cache skrivs en minimal giltig sida. Tavlan blankas eller 502:ar aldrig.

## Rollback till Loopia
Repointa A-posten `slinfo.brfhimmelsbagen.se` → Loopia-IP (Loopia-filerna i
`web/` ligger kvar). Vaka-config oförändrad.
