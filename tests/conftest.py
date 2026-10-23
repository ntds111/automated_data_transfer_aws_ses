"""Keep unit tests independent of local configuration and real AWS services."""

from unittest.mock import Mock

import pytest

import main


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Clear reporting overrides and fail immediately on unmocked AWS calls."""
    for name in (
        "AWS_REGION",
        "AWS_ROLE_ARN",
        "SES_EMAIL_SOURCE",
        "ATHENA_DATABASE",
        "ATHENA_OUTPUT_LOCATION",
        "ATHENA_QUERY",
        "SHOP_RECIPIENTS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(
        main.boto3,
        "client",
        Mock(side_effect=AssertionError("AWS calls must be mocked")),
    )
