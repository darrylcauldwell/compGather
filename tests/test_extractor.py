from app.services.extractor import _parse_response


def test_parse_valid_json_array():
    text = """[
        {
            "name": "Spring Show",
            "date_start": "2026-04-15",
            "date_end": null,
            "venue_name": "Hickstead",
            "venue_postcode": "RH17 5NZ",
            "has_pony_classes": true,
            "classes": ["Pony Newcomers", "1.00m Open"],
            "url": null
        }
    ]"""
    result = _parse_response(text)
    assert len(result) == 1
    assert result[0].name == "Spring Show"
    assert result[0].has_pony_classes is True
    assert result[0].classes == ["Pony Newcomers", "1.00m Open"]


def test_parse_json_with_surrounding_text():
    text = """Here are the competitions:
    [{"name": "Test Show", "date_start": "2026-05-01", "venue_name": "Arena UK", "has_pony_classes": false, "classes": []}]
    That's all."""
    result = _parse_response(text)
    assert len(result) == 1
    assert result[0].name == "Test Show"


def test_parse_empty_array():
    result = _parse_response("[]")
    assert result == []


def test_parse_no_json():
    result = _parse_response("No competitions found on this page.")
    assert result == []


def test_parse_invalid_json():
    result = _parse_response("[{invalid json}]")
    assert result == []


def test_parse_skips_invalid_entries():
    text = """[
        {"name": "Good Show", "date_start": "2026-06-01", "venue_name": "Test Venue"},
        {"bad_field": "missing required fields"}
    ]"""
    result = _parse_response(text)
    assert len(result) == 1
    assert result[0].name == "Good Show"
