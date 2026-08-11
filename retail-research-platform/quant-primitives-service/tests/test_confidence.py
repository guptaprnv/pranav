from quant_primitives.confidence import confidence_from_sample_size
from quant_primitives.models import ConfidenceLevel


def test_high_confidence_at_and_above_one_year():
    level, reason = confidence_from_sample_size(252)
    assert level == ConfidenceLevel.HIGH
    assert "252" in reason

    level, _ = confidence_from_sample_size(500)
    assert level == ConfidenceLevel.HIGH


def test_medium_confidence_between_three_months_and_one_year():
    level, reason = confidence_from_sample_size(60)
    assert level == ConfidenceLevel.MEDIUM
    assert "60" in reason

    level, _ = confidence_from_sample_size(251)
    assert level == ConfidenceLevel.MEDIUM


def test_low_confidence_below_three_months():
    level, reason = confidence_from_sample_size(59)
    assert level == ConfidenceLevel.LOW
    assert "caution" in reason

    level, _ = confidence_from_sample_size(0)
    assert level == ConfidenceLevel.LOW
