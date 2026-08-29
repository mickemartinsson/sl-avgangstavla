# SL Avgångstavla

Konfigurerbar avgångstavla som visar SL-avgångar i realtid. Designad för informationsskärmar som Axema C205, men fungerar i alla webbläsare.

Via en lösenordsskyddad inställningssida kan du välja vilka hållplatser (2-3 st), riktning och trafikslag som ska visas — utan att behöva ändra i koden.

## Två uppsättningar i repot

| Katalog | Vad | Status |
|---|---|---|
| `edge/` | Python-generator + systemd-timer + Caddy-vhost. Statisk `display.html`, ingen PHP. | **Produktion** för `slinfo.brfhimmelsbagen.se` sedan juni 2026 (`edge.a24.martinsson.eu`) |
| `web/` | PHP-varianten nedan (`update.php` + `settings.php`), för webbhotell. | Dormant rollback — se [PROD_NOTES.md](PROD_NOTES.md) |

Driftsdetaljer, rollback-läge och skärmkonfiguration: **[PROD_NOTES.md](PROD_NOTES.md)**.

Resten av det här dokumentet beskriver **PHP-varianten** (`web/`).

## Krav

Du behöver ett **webbhotell med PHP-stöd** (PHP 7.4+) och möjlighet att skapa **cron-jobb**, t.ex:

- [Loopia](https://www.loopia.se) (Webbhotell Standard eller högre)
- [One.com](https://www.one.com/sv)
- [Binero](https://www.binero.se)
- Liknande webbhotell som erbjuder **PHP med curl-extension** och **cron-jobb**

Webbhotellet måste stödja:
- **PHP 7.4 eller nyare** med `curl`-extension aktiverad
- **Cron-jobb** (schemalagda uppgifter)
- **Apache** med `mod_rewrite` och `.htaccess`-stöd

## Hur det fungerar

```
Cron (var 5:e minut)
  └── update.php  →  läser config.json
                 →  anropar SL Transport API
                 →  skriver display.html  (statisk)
                 →  skriver cache.json    (backup)

Skärmar (t.ex. 5 st Axema C205)
  └── hämtar display.html  (ingen PHP körs per visning)
      JavaScript laddar om sidan var 10:e minut + slumpmässig förskjutning
```

### Varför statisk HTML och låg anropsfrekvens?

Avgångstavlan är medvetet byggd för att klara **flera Axema-skärmar samtidigt** utan problem:

- **Cron-jobbet** körs var 5:e minut och genererar en **statisk HTML-fil** (`display.html`). Ingen PHP-process startas när en skärm hämtar sidan.
- **Browsercache** (4 min) gör att de flesta omladdningar serveras lokalt utan serveranrop.
- **Skärmarnas reload-intervall** är 10 minuter — SL-tider är prognosticerade ~90 minuter framåt så det räcker väl, och halverar trafiken jämfört med 5 minuter.
- **Slumpmässig förskjutning** (0–60 sekunder) sprider ut skärmarnas omladdningar så att de inte alla träffar servern exakt samtidigt.
- **HEAD-request vid liveness-koll** — JS:en gör först en HEAD-förfrågan (~200 byte) för att verifiera att servern svarar, innan navigation. Slipper ladda hela sidan i onödan om servern är nere.
- **Retry-logik med jitter** — om en skärm får 502 eller nätverksfel försöker den igen efter 10–20 sekunder (slumpat). Sprider ut retries så 5 skärmar inte slår servern samtidigt.

Utan denna arkitektur kan delat webbhotell (som Loopia) returnera **502-fel** när PHP-processpoolen töms av många samtidiga keep-alive-anslutningar. Den statiska modellen eliminerar detta problem helt.

## Installation

### 1. Skapa subdomän

Skapa en subdomän hos ditt webbhotell, t.ex:

```
slinfo.dinbrf.se
```

I Loopia: **Domäner → Din domän → Subdomäner → Lägg till** och ange `slinfo`. Peka subdomänen till en egen webbkatalog (t.ex. `/public_html/slinfo/`).

### 2. Ladda upp filer via FTP

Anslut till ditt webbhotell med en FTP-klient (t.ex. [FileZilla](https://filezilla-project.org/)) och ladda upp innehållet i `web/`-mappen till subdomänens webbkatalog:

```
Lokal:  web/*
Server: /public_html/slinfo/
```

Filer som ska laddas upp:

| Fil | Beskrivning |
|-----|-------------|
| `index.php` | Redirectar besökare till avgångstavlan |
| `update.php` | Hämtar SL-data och genererar tavlan (körs av cron) |
| `settings.php` | Lösenordsskyddad inställningssida |
| `search.php` | API-proxy för hållplatssökning i inställningssidan |
| `config.json` | Konfigurationsfil (skapas/uppdateras automatiskt) |
| `.htaccess` | Apache-inställningar och säkerhet |

### 3. Konfigurera hållplatser

Öppna inställningssidan i din webbläsare:

```
https://slinfo.dinbrf.se/settings.php
```

1. Logga in med standardlösenordet: **admin**
2. **Byt lösenord** direkt (längst ner på sidan)
3. Ange rubrik och konfigurera dina hållplatser:
   - **Sök hållplats** — Börja skriva namn, välj från listan. Site-ID fylls i automatiskt.
   - **Riktning** — Mot centrum (2), Från centrum (1), eller Båda
   - **Trafikslag** — Buss, båt, tunnelbana, etc. (eller alla)
   - **Antal avgångar** — Hur många rader som visas (1-20)
   - **Visa typ-kolumn** — Kryssas i om hållplatsen har blandade trafikslag
4. Klicka **Spara inställningar**

### 4. Skapa cron-jobb

I webbhotellets kontrollpanel (t.ex. Loopia → Cron), skapa ett jobb som körs var 5:e minut:

```
*/5 * * * *   curl -s https://slinfo.dinbrf.se/update.php > /dev/null
```

### 5. Första körningen

Öppna `update.php` manuellt i webbläsaren en gång:

```
https://slinfo.dinbrf.se/update.php
```

Det genererar `display.html` direkt utan att vänta på cron.

### 6. Konfigurera Axema-skärmarna

I **Axema Kontrollpanel**, skapa en spellista för informationstavlorna:

1. Gå till **Spellistor** → **Skapa ny spellista**
2. Lägg till ett nytt objekt av typen **Länk** (eller **Webbsida**)
3. Ange adressen:
   ```
   https://slinfo.dinbrf.se
   ```
4. Tilldela spellistan till de informationstavlor (Axema C205) som ska visa avgångstavlan

Skärmarna hämtar den statiska HTML-sidan och laddar om automatiskt var 5:e minut. Ingen ytterligare konfiguration behövs på skärmarna.

## Filer

| Fil | Syfte |
|-----|-------|
| `web/update.php` | Hämtar SL-data via API, genererar `display.html`. Körs av cron. |
| `web/settings.php` | Lösenordsskyddad inställningssida med hållplatssökning. |
| `web/search.php` | API-proxy — söker hållplatser via SL Transport API. |
| `web/config.json` | Sparar hållplatser, lösenord m.m. Skyddad från webbåtkomst via `.htaccess`. |
| `web/index.php` | Redirectar till `display.html`. Visar väntsida om cron inte kört. |
| `web/.htaccess` | Apache-regler: redirect, cache, `Connection: close`, skydd av `config.json`. |
| `web/display.html` | **Genererad** — checkas inte in. |
| `web/cache.json` | **Genererad** — backup av senaste API-svar. |

## Säkerhet

- **Lösenordsskydd** — Inställningssidan kräver inloggning. Lösenordet lagras som bcrypt-hash.
- **config.json skyddad** — `.htaccess` blockerar direkt åtkomst till konfigurationsfilen.
- **Standardlösenord** — Vid nyinstallation är lösenordet `admin`. Byt det omedelbart.

## SL Transport API

| Parameter | Beskrivning |
|-----------|-------------|
| `site_id` | Hållplatsens ID hos SL |
| `direction` | `1` = Från centrum, `2` = Mot centrum, tomt = båda |
| `transport` | `BUS`, `SHIP`, `METRO`, `TRAM`, `TRAIN`, tomt = alla |
| `forecast` | Minuter framåt (standard: 90) |

API-bas: `https://transport.integration.sl.se/v1/sites/{site_id}/departures`

Dokumentation: https://www.trafiklab.se/api/trafiklab-apis/sl/transport/

## Lokal utveckling

```bash
# Kräver PHP med curl-extension
php -S localhost:8080 -t web/

# Kör update.php för att generera display.html
curl http://localhost:8080/update.php

# Öppna inställningssidan
open http://localhost:8080/settings.php
```

## Licens

MIT
