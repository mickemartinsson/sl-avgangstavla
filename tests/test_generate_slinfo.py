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
    assert rows[0]["type"] == "Båt"


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
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch(
        {g.NT_URL: nt, g.NS_URL: ns, g.DEVIATIONS_URL: []}))
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
        "ns": [{"time": "07:05", "dest": "CachadNS", "line": "80", "type": "Båt"}],
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
        "ns": [{"time": "07:05", "dest": "CachadNS", "line": "80", "type": "Båt"}],
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


def test_atomic_write_makes_file_world_readable(tmp_path):
    import stat
    target = tmp_path / "x.html"
    g.atomic_write(str(target), "hi")
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o644


import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")
NOW = datetime.datetime(2026, 6, 24, 12, 0, tzinfo=TZ)


def _msg(case_id, importance, header, *, alias="Linje X",
         influence=5, pub_from="2020-01-01T00:00:00+02:00"):
    return {
        "deviation_case_id": case_id,
        "priority": {"importance_level": importance, "influence_level": influence},
        "publish": {"from": pub_from},
        "message_variants": [{"header": header, "scope_alias": alias}],
    }


def test_filter_alerts_drops_below_importance_threshold():
    msgs = [_msg(1, 5, "Försening")]   # imp=5 < 6
    assert g.filter_alerts(msgs, now=NOW) == []


def test_filter_alerts_accepts_importance_6_and_up():
    msgs = [_msg(1, 6, "Försening")]
    out = g.filter_alerts(msgs, now=NOW)
    assert len(out) == 1
    assert out[0]["level"] == "INFO"     # 6 → INFO


def test_filter_alerts_marks_importance_7_as_stopp():
    msgs = [_msg(1, 7, "Inställd trafik")]
    out = g.filter_alerts(msgs, now=NOW)
    assert out[0]["level"] == "STOPP"


def test_filter_alerts_blocklist_skips_hiss_and_skylt():
    msgs = [
        _msg(1, 7, "Avstängd hiss vid Slussen"),
        _msg(2, 6, "Skylt ur funktion vid Igelboda"),
        _msg(3, 6, "Inställd trafik mellan A och B"),
    ]
    out = g.filter_alerts(msgs, now=NOW)
    assert len(out) == 1
    assert "Inställd" in out[0]["header"]


def test_filter_alerts_skips_future_publish():
    future = "2099-01-01T00:00:00+02:00"
    msgs = [
        _msg(1, 7, "Kommande arbete", pub_from=future),
        _msg(2, 6, "Aktiv störning"),
    ]
    out = g.filter_alerts(msgs, now=NOW)
    assert len(out) == 1
    assert out[0]["header"] == "Aktiv störning"


def test_filter_alerts_dedupes_on_case_id():
    msgs = [_msg(1, 7, "Försening"), _msg(1, 7, "Försening")]
    assert len(g.filter_alerts(msgs, now=NOW)) == 1


def test_filter_alerts_caps_at_max_rows():
    msgs = [_msg(i, 7, f"Störning {i}") for i in range(10)]
    assert len(g.filter_alerts(msgs, now=NOW)) == g.ALERT_MAX_ROWS


def test_filter_alerts_sorts_high_importance_first():
    msgs = [
        _msg(1, 6, "Lägre", influence=3),
        _msg(2, 7, "Högre", influence=7),
    ]
    out = g.filter_alerts(msgs, now=NOW)
    assert out[0]["header"] == "Högre"


def test_filter_alerts_handles_unparseable_publish_date():
    msgs = [_msg(1, 7, "Aktiv", pub_from="kaputt")]
    # Ej parsebart → visa hellre än gömma
    assert len(g.filter_alerts(msgs, now=NOW)) == 1


def test_alerts_html_empty_returns_empty_string():
    assert g.alerts_html([]) == ""


def test_alerts_html_renders_level_marker_and_text():
    alerts = [{"level": "STOPP", "alias": "Gröna linjen", "header": "Stopp"}]
    out = g.alerts_html(alerts)
    assert "[STOPP]" in out
    assert "Gröna linjen" in out
    assert "Stopp" in out


def test_alerts_html_escapes_html_in_alias_and_header():
    alerts = [{"level": "INFO", "alias": "A & B", "header": "<script>"}]
    out = g.alerts_html(alerts)
    assert "A &amp; B" in out
    assert "&lt;script&gt;" in out
    assert "<script>" not in out


def test_main_writes_alerts_when_deviations_present(tmp_path, monkeypatch):
    out, cache = _patch_paths(tmp_path, monkeypatch)
    nt = {"departures": []}
    ns = {"departures": []}
    devs = [_msg(99, 7, "Inställd trafik", alias="Gröna linjen")]
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch(
        {g.NT_URL: nt, g.NS_URL: ns, g.DEVIATIONS_URL: devs}))
    rc = g.main()
    assert rc == 0
    page = out.read_text(encoding="utf-8")
    assert "[STOPP]" in page
    assert "Gröna linjen" in page
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["alerts"][0]["alias"] == "Gröna linjen"


def test_main_deviations_failure_uses_cached_alerts(tmp_path, monkeypatch):
    out, cache = _patch_paths(tmp_path, monkeypatch)
    cache.write_text(json.dumps({
        "nt": [], "ns": [],
        "alerts": [{"level": "STOPP", "alias": "Cached", "header": "Cachad störning"}],
    }), encoding="utf-8")
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch({
        g.NT_URL: {"departures": []},
        g.NS_URL: {"departures": []},
        g.DEVIATIONS_URL: RuntimeError("dev-api nere"),
    }))
    rc = g.main()
    assert rc == 1                # rc=1 pga deviations-fel
    page = out.read_text(encoding="utf-8")
    assert "Cachad störning" in page   # last-good visad


def test_main_no_deviations_renders_no_alert_section(tmp_path, monkeypatch):
    out, _ = _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(g, "fetch_sl", _fixed_fetch({
        g.NT_URL: {"departures": []},
        g.NS_URL: {"departures": []},
        g.DEVIATIONS_URL: [],
    }))
    assert g.main() == 0
    page = out.read_text(encoding="utf-8")
    assert "[STOPP]" not in page
    assert "[INFO]" not in page


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
