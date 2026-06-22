#!/usr/bin/env python3
"""Generera SL-avgångstavlans display.html på edge-a24-1.

Port av web/update.php. Hämtar SL:s öppna API för två hållplatser
(oberoende av varandra), renderar en statisk HTML-sida (mall identisk med
Loopia-versionen) och skriver den atomiskt. Faller en hållplats visas dess
senaste goda rader ur en cache (CACHE_FILE) — den friska siten fortsätter
uppdateras live. Tavlan blankas eller 502:ar därför aldrig.
"""
import html
import datetime
import json
import os
import sys
import tempfile
import urllib.request
from zoneinfo import ZoneInfo


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


def render_page(nt_rows, ns_rows, updated):
    """Rendera sidan från färdiga rad-dictar (live eller cachade)."""
    return (TEMPLATE
            .replace("__TH__", _TH)
            .replace("__NT_ROWS__", rows_html(nt_rows))
            .replace("__NS_ROWS__", rows_html(ns_rows, with_type=True))
            .replace("__UPDATED__", html.escape(updated)))


def build_page(nt_data, ns_data, updated):
    """Tunn wrapper: parsa rå API-data och rendera (används av golden-testet)."""
    return render_page(parse_rows(nt_data, 8),
                       parse_rows(ns_data, 8, with_type=True),
                       updated)


OUT_DIR = "/var/www/slinfo"
OUT_FILE = os.path.join(OUT_DIR, "display.html")
STATE_DIR = "/var/lib/slinfo"
CACHE_FILE = os.path.join(STATE_DIR, "cache.json")
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
        # mkstemp ger 0600 — Caddy körs som annan användare och måste kunna läsa.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cache(cache):
    try:
        atomic_write(CACHE_FILE, json.dumps(cache, ensure_ascii=False))
    except OSError as e:
        print(f"VARNING: kunde inte spara cache ({e})", file=sys.stderr)


def _fetch_rows(url, with_type):
    return parse_rows(fetch_sl(url), 8, with_type=with_type)


def main():
    updated = datetime.datetime.now(TZ).strftime("%H:%M")
    cache = load_cache()
    new_cache = dict(cache)
    failures = []

    # Varje hållplats hämtas oberoende. Faller en, visas dess senaste goda
    # rader ur cachen — den friska siten fortsätter uppdateras live.
    try:
        nt_rows = _fetch_rows(NT_URL, with_type=False)
        new_cache["nt"] = nt_rows
    except Exception as e:
        failures.append(f"NT ({e})")
        nt_rows = cache.get("nt", [])

    try:
        ns_rows = _fetch_rows(NS_URL, with_type=True)
        new_cache["ns"] = ns_rows
    except Exception as e:
        failures.append(f"NS ({e})")
        ns_rows = cache.get("ns", [])

    atomic_write(OUT_FILE, render_page(nt_rows, ns_rows, updated))
    save_cache(new_cache)

    if failures:
        print(f"VARNING: SL-API-fel [{'; '.join(failures)}] — "
              f"renderade med last-good där tillgängligt", file=sys.stderr)
        return 1
    print(f"OK | {updated} | NT: {len(nt_rows)} avg | NS: {len(ns_rows)} avg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
