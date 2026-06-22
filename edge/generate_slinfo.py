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
