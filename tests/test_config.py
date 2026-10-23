"""Configuration defaults, overrides, and validation."""

import pytest

from config import get_settings


def test_defaults():
    settings = get_settings()
    assert settings.region == "eu-central-1"
    assert settings.athena_database == "default"
    assert set(settings.shop_recipients) == {12345, 67890}
    assert len(settings.shop_recipients[12345]) == 3


def test_environment_overrides(monkeypatch):
    overrides = {
        "AWS_REGION": "us-east-1",
        "AWS_ROLE_ARN": "arn:aws:iam::123456789012:role/reporting",
        "SES_EMAIL_SOURCE": "reports@example.com",
        "ATHENA_DATABASE": "reports",
        "ATHENA_OUTPUT_LOCATION": "s3://reports/results/",
        "ATHENA_QUERY": "SELECT {shop_id}",
        "SHOP_RECIPIENTS": '{"42": ["recipient@example.com"]}',
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)
    settings = get_settings()
    assert settings.region == "us-east-1"
    assert settings.role_arn == overrides["AWS_ROLE_ARN"]
    assert settings.ses_email_source == "reports@example.com"
    assert settings.athena_database == "reports"
    assert settings.athena_output_location == "s3://reports/results/"
    assert settings.athena_query == "SELECT {shop_id}"
    assert settings.shop_recipients == {42: ["recipient@example.com"]}
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    assert get_settings().region == "eu-west-1"


@pytest.mark.parametrize(
    "value",
    [
        "not json",
        "[]",
        "{}",
        '{"42": []}',
        '{"42": "recipient@example.com"}',
        '{"42": [123]}',
        '{"42": ["invalid"]}',
        '{"42": ["a@example.com\\nBcc: b@example.com"]}',
        '{"42": ["a@example.com\\rBcc: b@example.com"]}',
        '{"not-an-id": ["recipient@example.com"]}',
    ],
)
def test_invalid_shop_configuration(monkeypatch, value):
    monkeypatch.setenv("SHOP_RECIPIENTS", value)
    with pytest.raises(ValueError):
        get_settings()
