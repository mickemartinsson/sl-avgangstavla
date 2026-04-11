# SL Avgångstavla

Konfigurerbar avgångstavla som visar SL-avgångar i realtid. Designad för informationsskärmar som Axema C205, men fungerar i alla webbläsare.

Via en lösenordsskyddad inställningssida kan du välja vilka hållplatser (2-3 st), riktning och trafikslag som ska visas — utan att behöva ändra i koden.

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

Skärmar
  └── hämtar display.html  (ingen PHP körs per visning)
      JavaScript laddar om sidan var 5:e minut
```

Skärmarna laddar alltid en **statisk HTML-fil** — ingen PHP körs per visning. Det eliminerar 502-fel som kan uppstå när PHP-processpoolen töms av många samtidiga anslutningar.

## Installation

### 1. Ladda upp filer via FTP

Anslut till ditt webbhotell med en FTP-klient (t.ex. [FileZilla](https://filezilla-project.org/)) och ladda upp innehållet i `web/`-mappen till din webbkatalog:

```
Lokal:  web/*
Server: /public_html/avgangstavla/     (eller valfri underkatalog)
```

Filer som ska laddas upp:
| Fil | Beskrivning |
|-----|-------------|
| `index.php` | Redirectar besökare till avgångstavlan |
| `update.php` | Hämtar SL-data och genererar tavlan |
| `settings.php` | Lösenordsskyddad inställningssida |
| `config.json` | Konfigurationsfil (skapas/uppdateras automatiskt) |
| `.htaccess` | Apache-inställningar och säkerhet |

### 2. Konfigurera hållplatser

Öppna inställningssidan i din webbläsare:

```
https://dindomän.se/avgangstavla/settings.php
```

1. Logga in med standardlösenordet: **admin**
2. **Byt lösenord** direkt (längst ner på sidan)
3. Ange rubrik och konfigurera dina hållplatser:
   - **Namn** — Visningsnamn, t.ex. "Nacka Trafikplats"
   - **Site-ID** — SL:s hållplats-ID (se nedan)
   - **Riktning** — Mot centrum (2), Från centrum (1), eller Båda
   - **Trafikslag** — Buss, båt, tunnelbana, etc. (eller alla)
   - **Antal avgångar** — Hur många rader som visas (1-20)
   - **Visa typ-kolumn** — Kryssas i om hållplatsen har blandade trafikslag
4. Klicka **Spara inställningar**

### 3. Hitta Site-ID för din hållplats

Öppna SL Transport API i webbläsaren för att söka:

```
https://transport.integration.sl.se/v1/sites?expand=true
```

Sök (Ctrl+F) efter din hållplats. Fältet `id` är ditt Site-ID.

Dokumentation: https://www.trafiklab.se/api/trafiklab-apis/sl/transport/

### 4. Skapa cron-jobb

I webbhotellets kontrollpanel (t.ex. Loopia → Cron), skapa ett jobb som körs var 5:e minut:

```
*/5 * * * *   curl -s https://dindomän.se/avgangstavla/update.php > /dev/null
```

### 5. Första körningen

Öppna `update.php` manuellt i webbläsaren en gång:

```
https://dindomän.se/avgangstavla/update.php
```

Det genererar `display.html` direkt utan att vänta på cron.

### 6. Peka skärmarna

Ställ in dina informationsskärmar på:

```
https://dindomän.se/avgangstavla/
```

## Filer

| Fil | Syfte |
|-----|-------|
| `web/update.php` | Hämtar SL-data via API, genererar `display.html`. Körs av cron. |
| `web/settings.php` | Lösenordsskyddad inställningssida. |
| `web/config.json` | Sparar hållplatser, lösenord m.m. Skyddad från webbåtkomst via `.htaccess`. |
| `web/index.php` | Redirectar till `display.html`. Visar väntsida om cron inte kört. |
| `web/.htaccess` | Apache-regler: redirect, cache, skydd av `config.json`. |
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
