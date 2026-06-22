import json
import os

import generate_slinfo as g

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


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


def test_render_matches_golden():
    nt = json.load(open(os.path.join(FIX, "sl_4062_nt.json")))
    ns = json.load(open(os.path.join(FIX, "sl_4031_ns.json")))
    expected = open(os.path.join(FIX, "golden_display.html"), encoding="utf-8").read()
    assert g.build_page(nt, ns, "12:34") == expected


def _fixed_fetch(mapping):
    """fetch_sl-stub som svarar per URL — ett Exception-värde kastas."""
    def _fetch(url, timeout=10):
        val = mapping[url]
        if isinstance(val, Exception):
            raise val
        return val
    return _fetch


def _patch_paths(tmp_path, monkeypatch):
    out = tmp_path / "display.html"
    cache = tmp_path / "cache.json"
    monkeypatch.setattr(g, "OUT_FILE", str(out))
    monkeypatch.setattr(g, "CACHE_FILE", str(cache))
    return out, cache


def test_main_success_renders_and_caches(tmp_path, monkeypatch):
    out, cache = _patch_paths(tmp_path, monkeypatch)
    nt = {"departures": [{"expected": "2026-06-22T14:05:00", "destination": "Slussen",
                          "line": {"designation": "401", "transport_mode": "BUS"}}]}
    ns = {"departures": [{"expected": "2026-06-22T14:10:00", "destination": "Nybroplan",
                          "line": {"designation": "80", "transport_mode": "SHIP"}}]}
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch({g.NT_URL: nt, g.NS_URL: ns}))
    rc = g.main()
    assert rc == 0
    page = out.read_text(encoding="utf-8")
    assert "Slussen" in page and "Nybroplan" in page
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["nt"][0]["dest"] == "Slussen"
    assert saved["ns"][0]["dest"] == "Nybroplan"


def test_main_partial_failure_uses_cached_for_failed_site(tmp_path, monkeypatch):
    out, cache = _patch_paths(tmp_path, monkeypatch)
    cache.write_text(json.dumps({
        "nt": [{"time": "07:00", "dest": "GammalNT", "line": "1", "type": ""}],
        "ns": [{"time": "07:05", "dest": "CachadNS", "line": "80", "type": "Bat"}],
    }), encoding="utf-8")
    nt = {"departures": [{"expected": "2026-06-22T14:05:00", "destination": "LiveNT",
                          "line": {"designation": "401", "transport_mode": "BUS"}}]}
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch(
        {g.NT_URL: nt, g.NS_URL: RuntimeError("502 NS nere")}))
    rc = g.main()
    assert rc == 1
    page = out.read_text(encoding="utf-8")
    assert "LiveNT" in page        # friska siten live
    assert "CachadNS" in page      # fallna siten visar last-good
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["nt"][0]["dest"] == "LiveNT"     # NT uppdaterad i cache
    assert saved["ns"][0]["dest"] == "CachadNS"   # NS bevarad


def test_main_total_failure_with_cache_renders_last_good(tmp_path, monkeypatch):
    out, cache = _patch_paths(tmp_path, monkeypatch)
    cache.write_text(json.dumps({
        "nt": [{"time": "07:00", "dest": "CachadNT", "line": "1", "type": ""}],
        "ns": [{"time": "07:05", "dest": "CachadNS", "line": "80", "type": "Bat"}],
    }), encoding="utf-8")
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch(
        {g.NT_URL: RuntimeError("nere"), g.NS_URL: RuntimeError("nere")}))
    rc = g.main()
    assert rc == 1
    page = out.read_text(encoding="utf-8")
    assert "CachadNT" in page and "CachadNS" in page


def test_main_total_failure_no_cache_writes_minimal(tmp_path, monkeypatch):
    out, cache = _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch(
        {g.NT_URL: RuntimeError("nere"), g.NS_URL: RuntimeError("nere")}))
    rc = g.main()
    assert rc == 1
    assert out.exists()
    assert "Inga avgångar hittades" in out.read_text(encoding="utf-8")


def test_atomic_write_cleans_temp_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "out.html"

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(g.os, "replace", boom)
    try:
        g.atomic_write(str(target), "data")
    except OSError:
        pass
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".display.")]
    assert leftovers == []
    assert not target.exists()
