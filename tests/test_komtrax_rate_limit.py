"""Local mock tests for Komtrax Fleet HTTP 429 handling."""

from unittest.mock import Mock

import pytest
import requests


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise AssertionError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def compare_module(monkeypatch, tmp_path):
    """Provide the komtrax module with mocked transport and tmp state."""
    import komtrax

    get = Mock()
    post = Mock()
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(
        komtrax, "KOMTRAX_TOKEN_CACHE", str(tmp_path / "komtrax_token.txt")
    )
    monkeypatch.setattr(komtrax, "KOMTRAX_TOKEN_TTL_SECONDS", 7000)
    monkeypatch.setattr(
        komtrax, "KOMTRAX_FLEET_STATE", str(tmp_path / "komtrax_fleet_state.txt")
    )
    monkeypatch.setattr(komtrax, "KOMTRAX_FLEET_MIN_INTERVAL_SECONDS", 300)
    return komtrax, get


def test_fracttal_token_reuses_canonical_api_token():
    import api
    import _compare_hours

    assert callable(getattr(_compare_hours, "get_fracttal_token", None))
    assert _compare_hours.get_fracttal_token is api.get_access_token


def test_rate_limited_response_raises_komtrax_fleet_error(compare_module):
    module, get = compare_module
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(
        429,
        {"statusCode": 429, "message": "Try again in 293 seconds."},
    )

    with pytest.raises(module.KomtraxFleetError, match="RATE_LIMITED"):
        module.get_komtrax_fleet("test-token")


def test_rate_limited_response_makes_exactly_one_request(compare_module):
    module, get = compare_module
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(
        429,
        {"statusCode": 429, "message": "Try again in 293 seconds."},
    )

    with pytest.raises(module.KomtraxFleetError):
        module.get_komtrax_fleet("test-token")

    assert get.call_count == 1


def test_http_200_returns_xml(compare_module):
    module, get = compare_module
    get.reset_mock(side_effect=True)
    xml = "<Fleet><Equipment /></Fleet>"
    get.return_value = FakeResponse(200, text=xml)

    assert module.get_komtrax_fleet("test-token") == xml


def test_fleet_get_requests_xml(compare_module):
    module, get = compare_module
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(200, text="<Fleet />")

    module.get_komtrax_fleet("test-token")

    request_headers = get.call_args.kwargs["headers"]
    assert request_headers["Accept"] == "application/xml"
    assert "Content-Type" not in request_headers


def test_http_200_json_is_non_xml_and_skips_parser(compare_module, monkeypatch):
    module, get = compare_module
    parser = Mock()
    monkeypatch.setattr(module, "parse_fleet_xml", parser)
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(
        200,
        {"statusCode": 200, "message": "unexpected payload"},
        headers={"Content-Type": "application/json"},
        text='{"statusCode": 200, "message": "unexpected payload"}',
    )

    def acquire_and_parse():
        xml = module.get_komtrax_fleet("test-token")
        return module.parse_komtrax_hours(xml)

    with pytest.raises(module.KomtraxFleetError, match="NON_XML_RESPONSE"):
        acquire_and_parse()

    parser.assert_not_called()


def test_http_200_html_is_non_xml_and_skips_parser(compare_module, monkeypatch):
    module, get = compare_module
    parser = Mock()
    monkeypatch.setattr(module, "parse_fleet_xml", parser)
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(
        200,
        headers={"Content-Type": "text/html"},
        text="<html><body>Service response</body></html>",
    )

    def acquire_and_parse():
        xml = module.get_komtrax_fleet("test-token")
        return module.parse_komtrax_hours(xml)

    with pytest.raises(module.KomtraxFleetError, match="NON_XML_RESPONSE"):
        acquire_and_parse()

    parser.assert_not_called()


def test_http_non_success_is_controlled(compare_module):
    module, get = compare_module
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(503, text="temporarily unavailable")

    with pytest.raises(module.KomtraxFleetError, match="HTTP_ERROR: 503"):
        module.get_komtrax_fleet("test-token")


def test_retry_after_is_preserved(compare_module):
    module, get = compare_module
    response = FakeResponse(
        429,
        {"message": "Rate limit exceeded."},
        headers={"Retry-After": "293"},
    )
    response.json = Mock(side_effect=AssertionError("JSON must not be read"))
    get.reset_mock(side_effect=True)
    get.return_value = response

    with pytest.raises(module.KomtraxFleetError) as error:
        module.get_komtrax_fleet("test-token")

    assert error.value.retry_after == "293"
    assert "Retry-After: 293" in str(error.value)
    response.json.assert_not_called()


def test_cached_token_reuses_valid_token_without_post(
    compare_module, tmp_path, monkeypatch
):
    import api

    module, _ = compare_module
    cache = tmp_path / "komtrax_token.txt"
    cache.write_text("cached-token\n2026-09-24T00:00:00+00:00\n", encoding="utf-8")
    monkeypatch.setattr(module, "KOMTRAX_TOKEN_CACHE", str(cache))
    monkeypatch.setattr(module, "KOMTRAX_TOKEN_TTL_SECONDS", 7000)
    post = Mock()
    monkeypatch.setattr(api.requests, "post", post)

    from datetime import datetime, timezone

    token = module.get_komtrax_token_cached(
        now=datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc)
    )

    assert token == "cached-token"
    post.assert_not_called()


def test_expired_token_triggers_single_post(compare_module, tmp_path, monkeypatch):
    import api

    module, _ = compare_module
    cache = tmp_path / "komtrax_token.txt"
    cache.write_text("old-token\n2026-09-23T00:00:00+00:00\n", encoding="utf-8")
    monkeypatch.setattr(module, "KOMTRAX_TOKEN_CACHE", str(cache))
    monkeypatch.setattr(module, "KOMTRAX_TOKEN_TTL_SECONDS", 7000)
    post = Mock(return_value=FakeResponse(200, {"access_token": "new-token"}))
    monkeypatch.setattr(api.requests, "post", post)

    from datetime import datetime, timezone

    token = module.get_komtrax_token_cached(
        now=datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc)
    )

    assert token == "new-token"
    assert post.call_count == 1


def test_fleet_quota_guard_blocks_second_fetch_without_get(
    compare_module, tmp_path, monkeypatch
):
    from datetime import datetime, timezone

    module, get = compare_module
    state = tmp_path / "komtrax_fleet_state.txt"
    now = datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc)
    state.write_text("2026-09-24T00:29:00+00:00\n", encoding="utf-8")
    monkeypatch.setattr(module, "KOMTRAX_FLEET_STATE", str(state))
    monkeypatch.setattr(module, "KOMTRAX_FLEET_MIN_INTERVAL_SECONDS", 300)
    get.reset_mock(side_effect=True)

    with pytest.raises(module.KomtraxFleetError, match="RATE_LIMITED_LOCAL"):
        module.get_komtrax_fleet("test-token", now=now)

    get.assert_not_called()


def test_fleet_fetch_records_state_on_success(
    compare_module, tmp_path, monkeypatch
):
    from datetime import datetime, timezone

    module, get = compare_module
    state = tmp_path / "komtrax_fleet_state.txt"
    now = datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "KOMTRAX_FLEET_STATE", str(state))
    monkeypatch.setattr(module, "KOMTRAX_FLEET_MIN_INTERVAL_SECONDS", 300)
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(200, text="<Fleet />")

    assert module.get_komtrax_fleet("test-token", now=now) == "<Fleet />"
    assert get.call_count == 1
    assert state.read_text(encoding="utf-8").strip() == now.isoformat()


KOMTRAX_NS = "http://www.jcmanet.or.jp/english2017/ISO/15143/-3/20190501"


def _gap_fleet_doc(*bodies):
    return (
        '<?xml version="1.0"?>'
        f'<Fleet xmlns="{KOMTRAX_NS}" snapshotTime="2026-09-24T00:00:00Z">'
        + "".join(bodies)
        + "</Fleet>"
    )


def _gap_equipment(serial, hour_block):
    return (
        "<Equipment><EquipmentHeader>"
        "<OEMName>KOMATSU</OEMName><Model>SYNTH</Model>"
        f"<EquipmentID>UNIT-{serial}</EquipmentID>"
        f"<SerialNumber>{serial}</SerialNumber>"
        "</EquipmentHeader>"
        + hour_block
        + "</Equipment>"
    )


def test_parse_preserves_error_flag_for_malformed_hour(compare_module):
    module, _ = compare_module
    doc = _gap_fleet_doc(
        _gap_equipment(
            "SN-BAD",
            '<CumulativeOperatingHours datetime="2026-09-24T00:00:00Z">'
            "<Hour>N/A</Hour></CumulativeOperatingHours>",
        )
    )

    entry = module.parse_komtrax_hours(doc)["SN-BAD"]

    assert entry["hours"] is None
    assert entry.get("_parse_error") is not None


def test_parse_marks_missing_node_without_error_flag(compare_module):
    module, _ = compare_module
    doc = _gap_fleet_doc(_gap_equipment("SN-EMPTY", ""))

    entry = module.parse_komtrax_hours(doc)["SN-EMPTY"]

    assert entry["hours"] is None
    assert entry.get("_parse_error") is None


def test_classify_komtrax_gap_distinguishes_states(compare_module):
    module, _ = compare_module

    assert module.classify_komtrax_gap(None) == "ABSENT"
    assert (
        module.classify_komtrax_gap(
            {"hours": None, "datetime": None, "_parse_error": "bad float"}
        )
        == "PARSE_ERROR"
    )
    assert (
        module.classify_komtrax_gap({"hours": None, "datetime": None})
        == "NO_HOURS"
    )
    assert (
        module.classify_komtrax_gap({"hours": 10.5, "datetime": "x"})
        == "OK"
    )


def test_decide_equal_values_skips(compare_module):
    module, _ = compare_module

    assert (
        module.decide_comparison(100.0, 100.0, "2026-09-24T00:00:00+00:00", "2026-09-24T00:00:00")
        == "SKIP_EQUAL"
    )


def test_decide_greater_and_newer_updates(compare_module):
    module, _ = compare_module

    assert (
        module.decide_comparison(101.0, 100.0, "2026-09-24T00:00:00+00:00", "2026-09-23T00:00:00")
        == "UPDATE"
    )


def test_decide_greater_but_older_reviews(compare_module):
    module, _ = compare_module

    assert (
        module.decide_comparison(101.0, 100.0, "2026-09-22T00:00:00+00:00", "2026-09-23T00:00:00")
        == "REVIEW_OLD_SOURCE"
    )


def test_decide_greater_with_unknown_dates_updates(compare_module):
    module, _ = compare_module

    assert module.decide_comparison(101.0, 100.0, None, None) == "UPDATE"
    assert module.decide_comparison(101.0, 100.0, "not-a-date", None) == "UPDATE"


def test_decide_smaller_value_reviews(compare_module):
    module, _ = compare_module

    assert (
        module.decide_comparison(99.0, 100.0, "2026-09-24T00:00:00+00:00", "2026-09-23T00:00:00")
        == "REVIEW_OLD_SOURCE"
    )


def _paged_doc(serial, hour, next_url=None):
    links = ""
    if next_url:
        links = (
            "<Links><rel>next</rel>"
            f"<href>{next_url}</href></Links>"
        )
    return (
        '<?xml version="1.0"?>'
        f'<Fleet xmlns="{KOMTRAX_NS}" snapshotTime="2026-09-24T00:00:00Z">'
        f"{links}"
        "<Equipment><EquipmentHeader>"
        "<OEMName>KOMATSU</OEMName><Model>SYNTH</Model>"
        f"<EquipmentID>UNIT-{serial}</EquipmentID>"
        f"<SerialNumber>{serial}</SerialNumber>"
        "</EquipmentHeader>"
        '<CumulativeOperatingHours datetime="2026-09-24T00:00:00Z">'
        f"<Hour>{hour}</Hour></CumulativeOperatingHours>"
        "</Equipment></Fleet>"
    )


def test_fleet_all_follows_next_link(compare_module):
    module, get = compare_module
    page1 = _paged_doc("SN-P1", "10.0", next_url="https://fleet.test/Fleet/2")
    page2 = _paged_doc("SN-P2", "20.0")

    def route(url, headers=None, timeout=None):
        if url.endswith("/Fleet/1"):
            return FakeResponse(200, text=page1)
        return FakeResponse(200, text=page2)

    get.reset_mock(side_effect=True)
    get.side_effect = route

    pages = module.get_komtrax_fleet_all("test-token")

    assert get.call_count == 2
    serials = {}
    for xml in pages:
        serials.update(module.parse_komtrax_hours(xml))
    assert serials["SN-P1"]["hours"] == 10.0
    assert serials["SN-P2"]["hours"] == 20.0


def test_fleet_all_single_page_makes_one_request(compare_module):
    module, get = compare_module
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(200, text=_paged_doc("SN-ONLY", "5.0"))

    pages = module.get_komtrax_fleet_all("test-token")

    assert get.call_count == 1
    assert module.parse_komtrax_hours(pages[0])["SN-ONLY"]["hours"] == 5.0


def test_fleet_all_does_not_follow_circular_next(compare_module):
    module, get = compare_module
    page = _paged_doc(
        "SN-LOOP",
        "7.0",
        next_url="https://isoapi.komtrax.komatsu/provider/v1/385177/Fleet/1",
    )
    get.reset_mock(side_effect=True)
    get.return_value = FakeResponse(200, text=page)

    pages = module.get_komtrax_fleet_all("test-token")

    assert len(pages) == 1
    assert get.call_count == 1

