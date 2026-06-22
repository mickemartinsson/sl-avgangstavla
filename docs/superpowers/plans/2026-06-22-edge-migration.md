# SL-avgångstavla edge-migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flytta SL-avgångstavlan bakom samma URL (`slinfo.brfhimmelsbagen.se`) från Loopia shared hosting till `edge-a24-1`, där en systemd-timer genererar en statisk `display.html` som Caddy serverar via `file_server` — så 502-problemet försvinner vid roten.

**Architecture:** Python-stdlib-generator (port av `web/update.php`) körs var 5:e min av en systemd-timer på edgen, skriver `display.html` atomiskt till `/var/www/slinfo`. Caddy `file_server` serverar filen med auto-TLS. Skärmarnas DOM-swap och Vaka-config rörs inte. Vid SL-API-fel behålls senaste goda filen.

**Tech Stack:** Python 3 (stdlib: `urllib`, `json`, `html`, `zoneinfo`, `tempfile`), pytest (dev), systemd (timer+oneshot), Caddy (file_server + Let's Encrypt), Loopia XML-RPC DNS-API.

**Spec:** `docs/superpowers/specs/2026-06-22-edge-migration-design.md`

**Drift-fakta (från sm2026-bark-handoff, verifiera vid behov):**
- Edge: `edge-a24-1`, publik `64.112.127.253`, tailnet `100.76.88.121`, Debian 13. SSH `ssh mikael@100.76.88.121` (tailnet-only, publik 22 stängd) + NOPASSWD sudo.
- DNS: Loopia XML-RPC, creds BW "Martinsson API" / `~/.config/loopia/env` (user `martinsson@loopiaapi`).
- LE-gotcha: DNS måste vara konsistent över ns1+ns2+1.1.1.1 **innan** Caddy-vhosten läggs (annars bränns rate-limit).

---

## Filstruktur

| Fil | Ansvar |
|---|---|
| `edge/generate_slinfo.py` | Hela generatorn: `fetch_sl`, `parse_rows`, `rows_html`, `build_page`, `atomic_write`, `main`. Mallen (HTML/CSS/DOM-swap) som modul-konstant. |
| `edge/systemd/slinfo-generator.service` | oneshot-service som kör generatorn som user `slinfo`. |
| `edge/systemd/slinfo-generator.timer` | timer var 5:e min. |
| `edge/caddy/slinfo.brfhimmelsbagen.se.caddy` | Caddy site-block (source of truth i repo). |
| `edge/README.md` | Deploy- + drift-runbook för edge-delen. |
| `tests/conftest.py` | Lägg `edge/` på sys.path. |
| `tests/test_generate_slinfo.py` | Enhetstester: parse + render-golden + keep-last-good. |
| `tests/fixtures/sl_4062_nt.json` | Infångat SL-svar, Nacka Trafikplats. |
| `tests/fixtures/sl_4031_ns.json` | Infångat SL-svar, Nacka Strand. |
| `tests/fixtures/golden_display.html` | Förväntad render (timestamp `12:34`). |

Befintlig `web/` (Loopia-PHP) rörs inte — behålls som rollback under soak.

---

## Task 1: Dev-miljö + infångade SL-fixtures

**Files:**
- Create: `tests/fixtures/sl_4062_nt.json`, `tests/fixtures/sl_4031_ns.json`
- Modify: `.gitignore`

- [ ] **Step 1: Skapa dev-venv med pytest**

```bash
cd ~/workspace/Produktion/sl-avgangstavla
python3 -m venv .venv-dev
.venv-dev/bin/pip install -q -U pip pytest
```

- [ ] **Step 2: Lägg dev-venv i .gitignore**

Lägg till raden `.venv-dev/` i `.gitignore`:

```bash
grep -qxF '.venv-dev/' .gitignore || echo '.venv-dev/' >> .gitignore
```

- [ ] **Step 3: Fånga riktiga SL-svar som fixtures**

```bash
mkdir -p tests/fixtures
curl -s "https://transport.integration.sl.se/v1/sites/4062/departures?transport=BUS&direction=2&forecast=90" -o tests/fixtures/sl_4062_nt.json
curl -s "https://transport.integration.sl.se/v1/sites/4031/departures?direction=2&forecast=90" -o tests/fixtures/sl_4031_ns.json
```

- [ ] **Step 4: Verifiera att fixtures är giltig JSON med departures**

Run:
```bash
.venv-dev/bin/python -c "import json; [print(f, len(json.load(open(f)).get('departures',[])), 'avgångar') for f in ['tests/fixtures/sl_4062_nt.json','tests/fixtures/sl_4031_ns.json']]"
```
Expected: båda filerna skriver ut ett antal avgångar (>0 under trafiktid; 0 är OK nattetid men kör helst dagtid så golden blir meningsfull).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/sl_4062_nt.json tests/fixtures/sl_4031_ns.json .gitignore
git commit -m "test: fånga SL-API-fixtures för generator-tester"
```

---

## Task 2: `parse_rows` (TDD)

**Files:**
- Create: `edge/generate_slinfo.py`, `tests/conftest.py`, `tests/test_generate_slinfo.py`

- [ ] **Step 1: conftest så `edge/` är importerbar**

Create `tests/conftest.py`:

```python
import os
import sys

EDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "edge")
sys.path.insert(0, EDGE_DIR)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_generate_slinfo.py`:

```python
import generate_slinfo as g


def test_parse_rows_basic():
    data = {"departures": [
        {"expected": "2026-06-22T14:05:00",
         "destination": "Slussen",
         "line": {"designation": "401", "transport_mode": "BUS"}},
    ]}
    rows = g.parse_rows(data, 8)
    assert rows[0] == {"time": "14:05", "dest": "Slussen", "line": "401", "type": ""}


def test_parse_rows_uses_scheduled_when_no_expected():
    data = {"departures": [
        {"scheduled": "2026-06-22T09:00:00", "destination": "Nybroplan",
         "line": {"designation": "80", "transport_mode": "SHIP"}},
    ]}
    rows = g.parse_rows(data, 8, with_type=True)
    assert rows[0]["time"] == "09:00"
    assert rows[0]["type"] == "Bat"


def test_parse_rows_bus_type():
    data = {"departures": [
        {"expected": "2026-06-22T08:00:00", "destination": "Centrum",
         "line": {"designation": "71", "transport_mode": "BUS"}},
    ]}
    rows = g.parse_rows(data, 8, with_type=True)
    assert rows[0]["type"] == "Buss"


def test_parse_rows_escapes_html():
    data = {"departures": [
        {"expected": "2026-06-22T08:00:00", "destination": "A & B",
         "line": {"designation": "1", "transport_mode": "BUS"}},
    ]}
    rows = g.parse_rows(data, 8)
    assert rows[0]["dest"] == "A &amp; B"


def test_parse_rows_count_and_empty():
    assert g.parse_rows({"departures": []}, 8) == []
    assert g.parse_rows(None, 8) == []
    many = {"departures": [
        {"expected": f"2026-06-22T08:0{i}:00", "destination": "X",
         "line": {"designation": "1", "transport_mode": "BUS"}} for i in range(5)
    ]}
    assert len(g.parse_rows(many, 3)) == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'generate_slinfo'`

- [ ] **Step 4: Implement `parse_rows`**

Create `edge/generate_slinfo.py`:

```python
#!/usr/bin/env python3
"""Generera SL-avgångstavlans display.html på edge-a24-1.

Port av web/update.php. Hämtar SL:s öppna API för två hållplatser,
renderar en statisk HTML-sida (mall identisk med Loopia-versionen) och
skriver den atomiskt. Vid API-fel behålls senaste goda filen.
"""
import html


def parse_rows(data, count, with_type=False):
    rows = []
    deps = (data or {}).get("departures", []) or []
    for i in range(count):
        if i >= len(deps):
            break
        d = deps[i]
        mode = (d.get("line") or {}).get("transport_mode", "")
        ts = d.get("expected") or d.get("scheduled") or ""
        rows.append({
            "time": html.escape(ts[11:16]),
            "dest": html.escape(d.get("destination") or ""),
            "line": html.escape((d.get("line") or {}).get("designation") or ""),
            "type": (("Bat" if mode == "SHIP" else "Buss") if with_type else ""),
        })
    return rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add edge/generate_slinfo.py tests/conftest.py tests/test_generate_slinfo.py
git commit -m "feat: parse_rows för SL-generator (port av update.php)"
```

---

## Task 3: `rows_html` + `build_page` + mall + golden (TDD)

**Files:**
- Modify: `edge/generate_slinfo.py`
- Modify: `tests/test_generate_slinfo.py`
- Create: `tests/fixtures/golden_display.html`

- [ ] **Step 1: Write failing tests for rows_html + build_page**

Lägg till i `tests/test_generate_slinfo.py`:

```python
def test_rows_html_empty_has_placeholder():
    out = g.rows_html([])
    assert 'colspan="3"' in out
    assert "Inga avgångar hittades" in out


def test_rows_html_empty_with_type_colspan4():
    out = g.rows_html([], with_type=True)
    assert 'colspan="4"' in out


def test_build_page_inserts_data_and_timestamp():
    nt = {"departures": [
        {"expected": "2026-06-22T14:05:00", "destination": "Slussen",
         "line": {"designation": "401", "transport_mode": "BUS"}}]}
    page = g.build_page(nt, {"departures": []}, "12:34")
    assert page.startswith("<!DOCTYPE html>")
    assert "Slussen" in page
    assert "Uppdaterad 12:34" in page
    # DOM-swap-scriptet måste finnas oförändrat i <head>
    assert "fetch('display.html?_=' + Date.now())" in page
    # NS tom → placeholder
    assert "Inga avgångar hittades" in page
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: FAIL — `AttributeError: module 'generate_slinfo' has no attribute 'rows_html'`

- [ ] **Step 3: Implement rows_html, TEMPLATE, build_page**

Lägg till i `edge/generate_slinfo.py` (efter `parse_rows`). **OBS:** mallen får inte ändras från `web/update.php` — bara `{$th}` inlinat och PHP-variabler → tokens `__UPDATED__`, `__NT_ROWS__`, `__NS_ROWS__`. JS-blocket innehåller `{}` och får INTE köras genom f-string/.format — därför `.replace()`.

```python
_BORDER = "border-bottom:1px solid #dde3ea;"
_TH = ('style="padding:7px 14px;font-size:12px;font-weight:bold;'
       'text-transform:uppercase;letter-spacing:0.8px;color:#005AA0;'
       'text-align:left;"')


def rows_html(rows, with_type=False):
    if not rows:
        cols = 4 if with_type else 3
        return (f'<tr><td colspan="{cols}" style="padding:16px;text-align:center;'
                f'color:#666;font-style:italic;">Inga avgångar hittades</td></tr>\n')
    out = []
    for i, r in enumerate(rows):
        bg = "background-color:#f0f4f8;" if i % 2 != 0 else "background-color:#ffffff;"
        s = f'<tr style="{bg}">'
        s += (f'<td style="{_BORDER}padding:10px 14px;font-size:20px;font-weight:bold;'
              f'color:#005AA0;width:90px;white-space:nowrap;">{r["time"]}</td>')
        s += f'<td style="{_BORDER}padding:10px 14px;font-size:18px;">{r["dest"]}</td>'
        s += (f'<td style="{_BORDER}padding:10px 14px;font-size:18px;font-weight:bold;'
              f'width:80px;">{r["line"]}</td>')
        if with_type:
            s += (f'<td style="{_BORDER}padding:10px 14px;font-size:14px;color:#666;'
                  f'width:60px;">{r["type"]}</td>')
        s += "</tr>\n"
        out.append(s)
    return "".join(out)


TEMPLATE = '''<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SL Avgångar</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, Helvetica, sans-serif; background: #f5f7fa; color: #1a2433; }
    table { width: 100%; border-collapse: collapse; }
  </style>
  <script>
    // DOM-swap istället för navigation: skärmen lämnar aldrig sidan och kan
    // aldrig fastna på browserns 502-felsida. Detta script lever i <head> och
    // ersätts aldrig — bara innehållet i #content byts.
    (function () {
      var RELOAD_MS = 5 * 60 * 1000;
      function jitter(min, max) { return min + Math.floor(Math.random() * (max - min)); }
      function schedule(ms) { setTimeout(tick, ms); }
      function tick() {
        fetch('display.html?_=' + Date.now())
          .then(function (r) {
            if (!r.ok) { schedule(jitter(30000, 90000)); return; }
            return r.text().then(function (txt) {
              try {
                var doc = new DOMParser().parseFromString(txt, 'text/html');
                var fresh = doc.getElementById('content');
                var cur = document.getElementById('content');
                if (fresh && cur) {
                  cur.innerHTML = fresh.innerHTML;
                  schedule(RELOAD_MS + jitter(0, 60000));
                } else {
                  schedule(jitter(30000, 90000));
                }
              } catch (e) {
                schedule(jitter(30000, 90000));
              }
            });
          })
          .catch(function () { schedule(jitter(30000, 90000)); });
      }
      schedule(RELOAD_MS + jitter(0, 60000));
    })();
  </script>
</head>
<body>

<div id="content">
  <!-- TOPPMENY -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#005AA0;">
    <tr>
      <td style="padding:12px 20px;">
        <table cellpadding="0" cellspacing="0">
          <tr>
            <td style="background-color:#ffffff;color:#005AA0;font-family:Arial,Helvetica,sans-serif;font-weight:900;font-size:20px;width:40px;height:40px;text-align:center;vertical-align:middle;">SL</td>
            <td style="padding-left:14px;">
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#ffffff;">Avgångar mot centrum</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#cce0f0;margin-top:2px;">Nacka Trafikplats &amp; Nacka Strand</div>
            </td>
          </tr>
        </table>
      </td>
      <td style="padding:12px 20px;text-align:right;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#cce0f0;vertical-align:middle;">
        Uppdaterad __UPDATED__
      </td>
    </tr>
  </table>

  <!-- INNEHÅLL -->
  <div style="padding:16px;">

    <!-- NACKA TRAFIKPLATS -->
    <div style="background-color:#ffffff;border:1px solid #dde3ea;margin-bottom:16px;">
      <div style="background-color:#005AA0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;padding:10px 16px;font-size:15px;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">
        Nacka Trafikplats
      </div>
      <table>
        <thead>
          <tr style="background-color:#e6eff7;border-bottom:2px solid #005AA0;">
            <th __TH__ width="90">Tid</th>
            <th __TH__>Destination</th>
            <th __TH__ width="80">Linje</th>
          </tr>
        </thead>
        <tbody>
__NT_ROWS__        </tbody>
      </table>
    </div>

    <!-- NACKA STRAND -->
    <div style="background-color:#ffffff;border:1px solid #dde3ea;">
      <div style="background-color:#005AA0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;padding:10px 16px;font-size:15px;font-weight:bold;text-transform:uppercase;letter-spacing:0.5px;">
        Nacka Strand
      </div>
      <table>
        <thead>
          <tr style="background-color:#e6eff7;border-bottom:2px solid #005AA0;">
            <th __TH__ width="90">Tid</th>
            <th __TH__>Destination</th>
            <th __TH__ width="80">Linje</th>
            <th __TH__ width="60">Typ</th>
          </tr>
        </thead>
        <tbody>
__NS_ROWS__        </tbody>
      </table>
    </div>

  </div>

  <div style="padding:8px 16px 14px;font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#999;text-align:center;">
    Data hämtad __UPDATED__ &nbsp;&middot;&nbsp; Sidan laddas om automatiskt var 5:e minut
  </div>
</div>

</body>
</html>
'''


def build_page(nt_data, ns_data, updated):
    nt = rows_html(parse_rows(nt_data, 8))
    ns = rows_html(parse_rows(ns_data, 8, with_type=True))
    return (TEMPLATE
            .replace("__TH__", _TH)
            .replace("__NT_ROWS__", nt)
            .replace("__NS_ROWS__", ns)
            .replace("__UPDATED__", html.escape(updated)))
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: PASS (alla tester)

- [ ] **Step 5: Generera golden-fil från fixtures**

```bash
.venv-dev/bin/python -c "
import json, sys; sys.path.insert(0,'edge')
import generate_slinfo as g
nt=json.load(open('tests/fixtures/sl_4062_nt.json'))
ns=json.load(open('tests/fixtures/sl_4031_ns.json'))
open('tests/fixtures/golden_display.html','w').write(g.build_page(nt,ns,'12:34'))
print('golden skriven')
"
```

- [ ] **Step 6: Ögna golden-filen (sanity)**

Run: `.venv-dev/bin/python -c "h=open('tests/fixtures/golden_display.html').read(); print(len(h),'bytes'); assert h.startswith('<!DOCTYPE html>'); assert 'Uppdaterad 12:34' in h; print('OK')"`
Expected: rimlig storlek (>2000 bytes) + `OK`. Öppna den gärna i en browser och bekräfta att den ser identisk ut med dagens tavla.

- [ ] **Step 7: Lägg till golden-regressionstest**

Lägg till i `tests/test_generate_slinfo.py`:

```python
import json
import os

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_render_matches_golden():
    nt = json.load(open(os.path.join(FIX, "sl_4062_nt.json")))
    ns = json.load(open(os.path.join(FIX, "sl_4031_ns.json")))
    expected = open(os.path.join(FIX, "golden_display.html"), encoding="utf-8").read()
    assert g.build_page(nt, ns, "12:34") == expected
```

- [ ] **Step 8: Run to verify pass**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add edge/generate_slinfo.py tests/test_generate_slinfo.py tests/fixtures/golden_display.html
git commit -m "feat: rows_html + build_page + mall (byte-identisk med update.php) + golden-test"
```

---

## Task 4: `fetch_sl` + `main` med keep-last-good (TDD)

**Files:**
- Modify: `edge/generate_slinfo.py`
- Modify: `tests/test_generate_slinfo.py`

- [ ] **Step 1: Write failing tests for main**

Lägg till i `tests/test_generate_slinfo.py`:

```python
def test_main_writes_page_on_success(tmp_path, monkeypatch):
    out = tmp_path / "display.html"
    monkeypatch.setattr(g, "OUT_FILE", str(out))
    monkeypatch.setattr(g, "fetch_sl",
                        lambda url, timeout=10: {"departures": []})
    rc = g.main()
    assert rc == 0
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_main_keeps_last_good_on_api_failure(tmp_path, monkeypatch):
    out = tmp_path / "display.html"
    out.write_text("OLD-GOOD", encoding="utf-8")
    monkeypatch.setattr(g, "OUT_FILE", str(out))

    def boom(url, timeout=10):
        raise RuntimeError("502 simulated")

    monkeypatch.setattr(g, "fetch_sl", boom)
    rc = g.main()
    assert rc == 1
    assert out.read_text(encoding="utf-8") == "OLD-GOOD"


def test_main_writes_minimal_page_when_no_previous(tmp_path, monkeypatch):
    out = tmp_path / "display.html"
    monkeypatch.setattr(g, "OUT_FILE", str(out))

    def boom(url, timeout=10):
        raise RuntimeError("502 simulated")

    monkeypatch.setattr(g, "fetch_sl", boom)
    rc = g.main()
    assert rc == 1
    assert out.exists()
    assert "Inga avgångar hittades" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: FAIL — `AttributeError: module 'generate_slinfo' has no attribute 'OUT_FILE'`

- [ ] **Step 3: Implement fetch_sl, atomic_write, main + constants**

Lägg till imports högst upp i `edge/generate_slinfo.py` (efter `import html`):

```python
import datetime
import json
import os
import sys
import tempfile
import urllib.request
from zoneinfo import ZoneInfo
```

Lägg till i slutet av `edge/generate_slinfo.py`:

```python
OUT_DIR = "/var/www/slinfo"
OUT_FILE = os.path.join(OUT_DIR, "display.html")
NT_URL = ("https://transport.integration.sl.se/v1/sites/4062/departures"
          "?transport=BUS&direction=2&forecast=90")
NS_URL = ("https://transport.integration.sl.se/v1/sites/4031/departures"
          "?direction=2&forecast=90")
TZ = ZoneInfo("Europe/Stockholm")


def fetch_sl(url, timeout=10):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "SL-Avgangar/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} för {url}")
        return json.loads(resp.read().decode("utf-8"))


def atomic_write(path, content):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".display.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main():
    updated = datetime.datetime.now(TZ).strftime("%H:%M")
    try:
        nt = fetch_sl(NT_URL)
        ns = fetch_sl(NS_URL)
    except Exception as e:
        if os.path.exists(OUT_FILE):
            print(f"VARNING: SL-API-fel ({e}); behåller senaste display.html",
                  file=sys.stderr)
            return 1
        print(f"VARNING: SL-API-fel ({e}) och ingen tidigare fil; "
              f"skriver minimal sida", file=sys.stderr)
        atomic_write(OUT_FILE, build_page(None, None, updated))
        return 1
    atomic_write(OUT_FILE, build_page(nt, ns, updated))
    print(f"OK | {updated} | NT: {len(parse_rows(nt, 8))} avg | "
          f"NS: {len(parse_rows(ns, 8, True))} avg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv-dev/bin/pytest tests/test_generate_slinfo.py -q`
Expected: PASS (alla tester gröna)

- [ ] **Step 5: Smoke-test mot riktiga SL-API:t lokalt (skriver till tmp)**

Run:
```bash
.venv-dev/bin/python -c "
import sys; sys.path.insert(0,'edge')
import tempfile, os
import generate_slinfo as g
d=tempfile.mkdtemp(); g.OUT_FILE=os.path.join(d,'display.html')
rc=g.main(); print('rc',rc); print('bytes', os.path.getsize(g.OUT_FILE))
"
```
Expected: `rc 0` (dagtid) + en filstorlek >2000 bytes. (Nattetid kan API ge 0 avgångar men rc ska ändå vara 0.)

- [ ] **Step 6: Commit**

```bash
git add edge/generate_slinfo.py tests/test_generate_slinfo.py
git commit -m "feat: fetch_sl + main med atomisk write och keep-last-good vid API-fel"
```

---

## Task 5: systemd-units + Caddy-vhost (source of truth i repo)

**Files:**
- Create: `edge/systemd/slinfo-generator.service`, `edge/systemd/slinfo-generator.timer`, `edge/caddy/slinfo.brfhimmelsbagen.se.caddy`

- [ ] **Step 1: Skapa service-unit**

Create `edge/systemd/slinfo-generator.service`:

```ini
[Unit]
Description=Generera SL-avgångstavla display.html
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=slinfo
Group=slinfo
ExecStart=/usr/bin/python3 /opt/slinfo/generate_slinfo.py
# Härdning
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/www/slinfo
ProtectHome=true
PrivateTmp=true
```

- [ ] **Step 2: Skapa timer-unit**

Create `edge/systemd/slinfo-generator.timer`:

```ini
[Unit]
Description=Kör SL-generatorn var 5:e minut

[Timer]
OnCalendar=*:0/5
RandomizedDelaySec=20
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Skapa Caddy site-block**

Create `edge/caddy/slinfo.brfhimmelsbagen.se.caddy`:

```caddy
slinfo.brfhimmelsbagen.se {
	root * /var/www/slinfo
	file_server
	encode gzip
	header Cache-Control "no-cache"
	log {
		output file /var/log/caddy/slinfo.log
	}
}
```

- [ ] **Step 4: Commit**

```bash
git add edge/systemd/ edge/caddy/
git commit -m "feat: systemd-timer + Caddy file_server-vhost för slinfo på edge"
```

---

## Task 6: Edge-runbook

**Files:**
- Create: `edge/README.md`

- [ ] **Step 1: Skriv runbook**

Create `edge/README.md`:

```markdown
# SL-avgångstavla — edge-deploy (edge-a24-1)

Generatorn körs som systemd-timer på edge-a24-1 och skriver en statisk
`display.html` som Caddy serverar via `file_server`. Ingen PHP, inga deps
(Python stdlib). Ersätter Loopia shared hosting.

## Komponenter på edgen
- `/opt/slinfo/generate_slinfo.py` — generatorn (körs av timern).
- `/var/www/slinfo/display.html` — output (ägd av user `slinfo`, läst av Caddy).
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
Vid SL-API-fel behålls senaste goda `display.html` (servicen loggar VARNING
och exitar 1; syns i journal). Skärmen blankas aldrig av en transient blipp.

## Rollback till Loopia
Repointa A-posten `slinfo.brfhimmelsbagen.se` → Loopia-IP (Loopia-filerna i
`web/` ligger kvar). Vaka-config oförändrad.
```

- [ ] **Step 2: Commit**

```bash
git add edge/README.md
git commit -m "docs: edge-runbook för slinfo-deploy och diagnostik"
```

---

## Task 7: Deploy till edgen + verifiera lokalt på edgen

**Förkrav:** Tailscale uppe på Mini (`tailscale status` visar edge `100.76.88.121`). Allt nedan körs av Mikael/operatör — `ssh mikael@100.76.88.121` har NOPASSWD sudo.

- [ ] **Step 1: Verifiera edge-åtkomst + egress mot SL-API**

```bash
ssh mikael@100.76.88.121 'echo OK; python3 --version; curl -s -o /dev/null -w "SL-API: %{http_code}\n" "https://transport.integration.sl.se/v1/sites/4062/departures?forecast=90"'
```
Expected: `OK`, en Python 3-version, `SL-API: 200`.

- [ ] **Step 2: Skapa användare + kataloger på edgen**

```bash
ssh mikael@100.76.88.121 'sudo useradd --system --no-create-home --shell /usr/sbin/nologin slinfo 2>/dev/null; sudo mkdir -p /opt/slinfo /var/www/slinfo /var/log/caddy; sudo chown slinfo:slinfo /opt/slinfo /var/www/slinfo; id slinfo'
```
Expected: `id slinfo` skriver ut uid/gid (idempotent — `useradd` kan säga "already exists", OK).

- [ ] **Step 3: Kopiera generator + units**

```bash
cd ~/workspace/Produktion/sl-avgangstavla
scp edge/generate_slinfo.py mikael@100.76.88.121:/tmp/
scp edge/systemd/slinfo-generator.service edge/systemd/slinfo-generator.timer mikael@100.76.88.121:/tmp/
ssh mikael@100.76.88.121 'sudo install -o slinfo -g slinfo -m 0755 /tmp/generate_slinfo.py /opt/slinfo/generate_slinfo.py && sudo install -m 0644 /tmp/slinfo-generator.service /tmp/slinfo-generator.timer /etc/systemd/system/ && sudo systemctl daemon-reload'
```

- [ ] **Step 4: Verifiera units + kör generatorn en gång**

```bash
ssh mikael@100.76.88.121 'sudo systemd-analyze verify /etc/systemd/system/slinfo-generator.service; sudo systemctl start slinfo-generator.service; journalctl -u slinfo-generator.service -n 5 --no-pager; ls -l /var/www/slinfo/display.html'
```
Expected: ingen verify-output (=OK), journal visar `OK | HH:MM | NT: … | NS: …`, filen finns och ägs av `slinfo`.

- [ ] **Step 5: Aktivera timern**

```bash
ssh mikael@100.76.88.121 'sudo systemctl enable --now slinfo-generator.timer; systemctl list-timers slinfo-generator.timer --no-pager'
```
Expected: timern listad med nästa körning inom 5 min.

- [ ] **Step 6: Verifiera lokalt serve (innan publik DNS) via curl med Host-header**

```bash
ssh mikael@100.76.88.121 'curl -s -H "Host: slinfo.brfhimmelsbagen.se" http://127.0.0.1/display.html | head -3'
```
Expected: Detta kan ge 404/anslutningsfel tills Caddy-vhosten finns (Task 9) — om så, hoppa till Task 8. (Om edgens Caddy har en catch-all kan det ge annat innehåll; det är OK, vi bekräftar riktigt i Task 9.)

---

## Task 8: DNS — repointa A-posten hos Loopia

**Förkrav:** BW upplåst (`~/.cache/bw/session.env`), Loopia-creds i `~/.config/loopia/env` (eller BW "Martinsson API").

- [ ] **Step 1: Ladda Loopia-creds + inspektera nuvarande post**

Bekräfta först variabelnamnen i env-filen (förväntat `LOOPIA_USER` + `LOOPIA_PASSWORD`; justera nedan om de heter annat):
```bash
grep -oE '^[A-Z_]+=' ~/.config/loopia/env
```

```bash
set -a; source ~/.config/loopia/env; set +a
python3 - <<'PY'
import os, xmlrpc.client
u, p = os.environ["LOOPIA_USER"], os.environ["LOOPIA_PASSWORD"]
c = xmlrpc.client.ServerProxy("https://api.loopia.se/RPCSERV", encoding="utf-8")
recs = c.getZoneRecords(u, p, "brfhimmelsbagen.se", "slinfo")
print("Nuvarande slinfo-poster:", recs)
PY
```
Expected: en lista med minst en A-post (nuvarande Loopia-IP) + dess `record_id`. **Notera nuvarande rdata (Loopia-IP) för rollback.**
Om anropet ger auth-fel/tom: zonen hanteras inte av dessa creds → gör A-posten i **Loopia-panelen** istället och hoppa till Step 3.

- [ ] **Step 2: Uppdatera A-posten → 64.112.127.253**

```bash
set -a; source ~/.config/loopia/env; set +a
python3 - <<'PY'
import os, xmlrpc.client
u, p = os.environ["LOOPIA_USER"], os.environ["LOOPIA_PASSWORD"]
c = xmlrpc.client.ServerProxy("https://api.loopia.se/RPCSERV", encoding="utf-8")
recs = c.getZoneRecords(u, p, "brfhimmelsbagen.se", "slinfo")
a = [r for r in recs if r["type"] == "A"]
assert len(a) == 1, f"förväntade exakt en A-post, fick {recs}"
rec = a[0]
rec["rdata"] = "64.112.127.253"
rec["ttl"] = 300
print("Uppdaterar:", c.updateZoneRecord(u, p, "brfhimmelsbagen.se", "slinfo", rec))
PY
```
Expected: `OK`.

- [ ] **Step 3: Verifiera propagering över ns1 + ns2 + 1.1.1.1**

```bash
for ns in ns1.loopia.se ns2.loopia.se 1.1.1.1; do echo -n "$ns: "; dig +short @$ns slinfo.brfhimmelsbagen.se A; done
```
Expected: **alla tre** svarar `64.112.127.253`. Om de inte är konsistenta — **vänta och upprepa**, gå INTE vidare till Caddy-vhosten (LE rate-limit-risk). TTL var 300s; räkna med några minuter.

---

## Task 9: Lägg Caddy-vhosten live + cert + verifiera publik URL

- [ ] **Step 1: Inspektera edgens Caddy-struktur**

```bash
ssh mikael@100.76.88.121 'sudo head -20 /etc/caddy/Caddyfile; echo "---"; grep -n "import" /etc/caddy/Caddyfile; ls -la /etc/caddy/'
```
Förväntan: avgör om edgens Caddyfile använder `import` av en sites-katalog (t.ex. `/etc/caddy/sites/*.caddy`) eller har site-block direkt. **Placera vhosten enligt befintligt mönster** (jämför `a24-offsite-edge`-repot om det finns).

- [ ] **Step 2: Installera vhost-blocket**

Om edgen importerar en sites-katalog (vanligast), kopiera dit:
```bash
cd ~/workspace/Produktion/sl-avgangstavla
scp edge/caddy/slinfo.brfhimmelsbagen.se.caddy mikael@100.76.88.121:/tmp/
ssh mikael@100.76.88.121 'sudo install -m 0644 /tmp/slinfo.brfhimmelsbagen.se.caddy /etc/caddy/sites/ && sudo mkdir -p /var/log/caddy'
```
Om Caddyfile har block direkt: lägg innehållet i `edge/caddy/slinfo.brfhimmelsbagen.se.caddy` sist i `/etc/caddy/Caddyfile` (via `sudoedit`).

- [ ] **Step 3: Validera config + reload**

```bash
ssh mikael@100.76.88.121 'sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy'
```
Expected: `Valid configuration` + ren reload.

- [ ] **Step 4: Verifiera cert + publik HTTPS (retry-loop för cert-provisioning)**

```bash
for i in $(seq 1 12); do
  code=$(curl -s -o /dev/null -w "%{http_code}" https://slinfo.brfhimmelsbagen.se/display.html)
  echo "försök $i: HTTP $code"; [ "$code" = "200" ] && break; sleep 10
done
curl -sI https://slinfo.brfhimmelsbagen.se/display.html | grep -iE "HTTP|cache-control"
curl -s https://slinfo.brfhimmelsbagen.se/display.html | grep -i "Uppdaterad"
```
Expected: HTTP 200, `cache-control: no-cache`, och en färsk `Uppdaterad HH:MM`. (Cert tar ~10–15s första gången.)

---

## Task 10: Skärm-cutover via Vaka (Mikael)

Skärmarna sitter idag fast på Loopias 502-felsida → behöver EN manuell omladdning. URL:en är oförändrad.

- [ ] **Step 1: Tvinga omladdning på EN skärm**

I Axema Vaka PC Client → **Informationscenter → Filer**: ta bort webbresursen `SL-info direkt` (pekar på `https://slinfo.brfhimmelsbagen.se/display.html`), lägg till den igen, och dra in den i den uppgångens spellista. Skärmen laddar om URL:en.

- [ ] **Step 2: Bekräfta render + self-heal på testskärmen**

Titta på skärmen: SL-tavlan ska visas korrekt. Vänta ≥6 min och bekräfta att den uppdateras av sig själv (DOM-swap), utan 502.

- [ ] **Step 3: Rulla ut på resterande 4 skärmar**

Upprepa Step 1 för spellistorna A24–A32 (skärm 2, 5, 8, 11, 14). Bekräfta alla 5.

- [ ] **Step 4: Bekräfta uptime-probe grön**

```bash
ssh root@<pve12> 'tail -5 /var/lib/slinfo-uptime/probe.log; cat /var/lib/slinfo-uptime/incident.state'
```
Expected: `OK`-state, inga aktiva incidenter. (Proben testar publika URL:en, host-agnostiskt — ingen ändring krävdes.)

---

## Task 11: Soak + avveckla Loopia

- [ ] **Step 1: Stoppa Loopia-cronen (men behåll filerna)**

SSH Loopia (`2r8w99@ssh.loopia.se`) och ta bort cron-raden `*/5 * * * * curl … update.php`. Behåll `update.php` + `display.html` orörda som rollback.

- [ ] **Step 2: Soak ~3–5 dygn**

Övervaka: inga Bark-incidenter från `SL-Avgangstavla`, skärmarna stabila. Kontroll: `journalctl -u slinfo-generator.service --since "1 day ago" | grep -c VARNING` på edgen (enstaka VARNING vid SL-blipp är OK — skärmen ska ändå vara grön).

- [ ] **Step 3: Efter godkänd soak — avveckla Loopia-webroot**

Ta bort Loopia-filerna när edge är bevisat stabilt (behåll repo-historiken). A-posten kvar mot edgen.

- [ ] **Step 4: Merge feature-branch → prod-branch**

```bash
cd ~/workspace/Produktion/sl-avgangstavla
git checkout prod-sync && git merge --no-ff feat/edge-migration -m "feat: edge-migration driftsatt — Loopia avvecklad"
git push origin prod-sync && git push github prod-sync
```

- [ ] **Step 5: Uppdatera minnet**

Uppdatera `project_sl_avgangstavla.md`: produktionen kör nu på edge-a24-1 (statisk fil + Caddy), Loopia avvecklad, 502-roten löst. Notera generator-path `/opt/slinfo/`, timer, och rollback-väg.

---

## Self-review-anteckningar

- **Spec-täckning:** Alternativ B (Task 2–9), keep-last-good (Task 4), C205-mall byte-för-byte + golden (Task 3), Caddy auto-TLS + LE-gotcha (Task 8–9), behåll URL/repointa A (Task 8), oförändrad probe (Task 10), soak+rollback (Task 11). ✓
- **Tidszon:** `updated` använder `Europe/Stockholm` (Task 4) — avgångstider kommer redan lokala från SL (substring), bara "Uppdaterad" beror på serverklockan.
- **JS-braces:** mallen byggs med `.replace()`, aldrig f-string/.format, så DOM-swap-scriptets `{}` överlever (Task 3, explicit not).
- **Namnkonsistens:** `OUT_FILE`, `fetch_sl`, `build_page`, `parse_rows`, `rows_html`, `atomic_write` används identiskt i kod och tester.
```
