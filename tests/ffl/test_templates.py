import pytest

from ffl.services.templates import publish_signal_template, validate_signal_payload


def test_published_exception_template_rejects_missing_required_photo(ffl_db, owner):
    template = publish_signal_template(
        ffl_db,
        "crop_exception",
        1,
        [
            {
                "key": "severity",
                "type": "choice",
                "required": True,
                "options": ["low", "medium", "high", "critical"],
            },
            {"key": "photo_url", "type": "photo", "required": True},
        ],
        owner.id,
    )

    with pytest.raises(ValueError, match="photo_url is required"):
        validate_signal_payload(template, {"severity": "high"})


def test_payload_rejects_choice_outside_template_options(ffl_db, owner):
    template = publish_signal_template(
        ffl_db,
        "crop_exception",
        1,
        [{"key": "severity", "type": "choice", "required": True, "options": ["low"]}],
        owner.id,
    )

    with pytest.raises(ValueError, match="severity must be one of"):
        validate_signal_payload(template, {"severity": "high"})


def test_payload_returns_only_declared_keys(ffl_db, owner):
    template = publish_signal_template(
        ffl_db,
        "crop_exception",
        1,
        [{"key": "severity", "type": "choice", "required": True, "options": ["high"]}],
        owner.id,
    )

    assert validate_signal_payload(template, {"severity": "high", "ignored": "value"}) == {
        "severity": "high"
    }
