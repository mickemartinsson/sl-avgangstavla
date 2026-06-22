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
