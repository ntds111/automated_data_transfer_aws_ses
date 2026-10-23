"""Environment-backed configuration shared by local and Lambda entry points."""

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Reporting settings; defaults retain the original example configuration."""

    region: str
    role_arn: str
    ses_email_source: str
    athena_database: str
    athena_output_location: str
    athena_query: str
    shop_recipients: dict[int, list[str]]


def get_settings() -> Settings:
    """Load configuration at invocation time without accessing AWS."""
    default_recipients = [
        "dummyemail1@gmail.com",
        "dummyemail2@gmail.com",
        "dummyemail3@gmail.com",
    ]
    raw_shops = os.environ.get("SHOP_RECIPIENTS")
    if raw_shops is None:
        shops = {12345: default_recipients.copy(), 67890: default_recipients.copy()}
    else:
        parsed = json.loads(raw_shops)
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError("SHOP_RECIPIENTS must be a nonempty JSON object")
        shops = {}
        for shop_id, recipients in parsed.items():
            if not isinstance(recipients, list) or not recipients:
                raise ValueError("Each shop must have a nonempty recipient list")
            if any(
                not isinstance(recipient, str)
                or "@" not in recipient
                or "\r" in recipient
                or "\n" in recipient
                for recipient in recipients
            ):
                raise ValueError("Recipients must be single-line email addresses")
            shops[int(shop_id)] = recipients

    return Settings(
        region=os.environ.get("AWS_REGION", "eu-central-1"),
        role_arn=os.environ.get(
            "AWS_ROLE_ARN", "arn:aws:iam::1234567890:role/your-role-name"
        ),
        ses_email_source=os.environ.get(
            "SES_EMAIL_SOURCE", "someemail.aws.yourcompanyhostname.cloud"
        ),
        athena_database=os.environ.get("ATHENA_DATABASE", "default"),
        athena_output_location=os.environ.get(
            "ATHENA_OUTPUT_LOCATION", "s3://s3_bucket_folder/output_folder_name"
        ),
        athena_query=os.environ.get("ATHENA_QUERY", "your query here"),
        shop_recipients=shops,
    )
