"""Unit tests for Command Parser inference service, validation logic, and pipeline cleaning."""
import json
from service.app import validate_prediction


def test_validation_success():
    """Test 1: Valid 4-key JSON with correct intent and slots succeeds."""
    valid_output = json.dumps({
        "intent": "alarm_set",
        "date": "tomorrow",
        "time": "seven am",
        "place": None
    })
    ok, parsed = validate_prediction(valid_output)
    assert ok is True
    assert parsed["intent"] == "alarm_set"
    assert parsed["date"] == "tomorrow"
    assert parsed["time"] == "seven am"
    assert parsed["place"] is None


def test_validation_invalid_intent():
    """Test 2: Output with an invalid or hallucinated intent fails validation."""
    invalid_intent_output = json.dumps({
        "intent": "unknown_intent_action",
        "date": None,
        "time": None,
        "place": None
    })
    ok, parsed = validate_prediction(invalid_intent_output)
    assert ok is False
    assert parsed is None


def test_validation_missing_keys():
    """Test 3: Output missing one of the four required keys fails validation."""
    missing_key_output = json.dumps({
        "intent": "weather_query",
        "date": None,
        "place": "london"
        # missing "time"
    })
    ok, parsed = validate_prediction(missing_key_output)
    assert ok is False
    assert parsed is None


def test_validation_extra_keys():
    """Test 4: Output containing unauthorized extra keys fails validation."""
    extra_key_output = json.dumps({
        "intent": "datetime_query",
        "date": None,
        "time": "now",
        "place": "tokyo",
        "confidence": 0.99
    })
    ok, parsed = validate_prediction(extra_key_output)
    assert ok is False
    assert parsed is None


def test_validation_malformed_json():
    """Test 5: Broken or truncated JSON string fails validation."""
    broken_output = '{"intent": "alarm_set", "date": "tomorrow", "time":'
    ok, parsed = validate_prediction(broken_output)
    assert ok is False
    assert parsed is None
