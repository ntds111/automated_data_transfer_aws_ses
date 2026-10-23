"""Query Athena and deliver per-shop Excel reports through AWS SES."""

import io
import logging
import time
from email.message import EmailMessage

import boto3
import pandas as pd
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from config import get_settings

logger = logging.getLogger(__name__)
config = Config(
    retries={"max_attempts": 10, "mode": "standard"},
    read_timeout=360,
    connect_timeout=360,
)


def handler(event, context):
    """Generate reports, isolating each shop's failures from other shops."""
    settings = get_settings()
    credentials = assume_role(settings.role_arn)

    for shop_id, recipients in settings.shop_recipients.items():
        query = settings.athena_query.replace("{shop_id}", str(shop_id))
        logger.info("Starting Athena query execution for shop_id %s", shop_id)
        try:
            query_execution_id = run_athena_query(query, credentials)
            output_df = download_athena_results(query_execution_id, credentials)
            split_dfs = split_dataframe(output_df, max_rows=65000)

            for i, df_part in enumerate(split_dfs):
                excel_data = dataframe_to_excel(df_part)
                part_suffix = f"_part{i + 1}" if len(split_dfs) > 1 else ""
                filename = f"athena_query_results_shop_{shop_id}{part_suffix}.xlsx"
                send_email_with_attachment(excel_data, filename, shop_id, recipients)
        except Exception:
            logger.exception("Error for shop_id %s", shop_id)


def assume_role(role_arn: str):
    """Obtain temporary reporting credentials using the caller's identity."""
    sts_client = boto3.client("sts", region_name=get_settings().region)
    try:
        assumed_role = sts_client.assume_role(
            RoleArn=role_arn, RoleSessionName="LambdaSession"
        )
    except (BotoCoreError, ClientError):
        logger.exception("Error assuming reporting role")
        raise
    return assumed_role["Credentials"]


def get_client(service_name: str, credentials: dict):
    """Create a regional AWS client with the assumed role's credentials."""
    return boto3.client(
        service_name,
        region_name=get_settings().region,
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )


def run_athena_query(query: str, credentials: dict):
    """Start an Athena query and poll until it reaches a terminal state."""
    settings = get_settings()
    client = get_client("athena", credentials)
    execution = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": settings.athena_database},
        ResultConfiguration={"OutputLocation": settings.athena_output_location},
    )
    query_execution_id = execution["QueryExecutionId"]
    while True:
        query_status = client.get_query_execution(QueryExecutionId=query_execution_id)
        state = query_status["QueryExecution"]["Status"]["State"]
        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            break
        time.sleep(5)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena query execution failed with state: {state}")
    return query_execution_id


def download_athena_results(query_execution_id: str, credentials: dict) -> pd.DataFrame:
    """Read the query's actual S3 output, including workgroup overrides."""
    athena_client = get_client("athena", credentials)
    execution = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
    location = execution["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
    bucket, key = parse_s3_location(location)
    s3_client = get_client("s3", credentials)
    s3_response = s3_client.get_object(Bucket=bucket, Key=key)
    with s3_response["Body"] as body:
        return pd.read_csv(io.BytesIO(body.read()), encoding="utf8")


def parse_s3_location(location: str) -> tuple[str, str]:
    """Extract a bucket and object key from an Athena result URI."""
    if not location.startswith("s3://"):
        raise ValueError("Athena output must be an s3:// URI")
    bucket, separator, key = location[5:].partition("/")
    if not bucket or not separator or not key:
        raise ValueError("Athena output must include a bucket and object key")
    return bucket, key


def split_dataframe(df: pd.DataFrame, max_rows: int) -> list:
    """Split a DataFrame into ordered chunks with at most max_rows rows."""
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    return [df.iloc[i : i + max_rows] for i in range(0, len(df), max_rows)]


def dataframe_to_excel(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to a single-sheet XLSX attachment without its index."""
    excel_writer = io.BytesIO()
    with pd.ExcelWriter(excel_writer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)
    return excel_writer.getvalue()


def send_email_with_attachment(
    excel_data: bytes, filename: str, shop_id: int, recipients: list
):
    """Send one report to all shop recipients; log AWS failures without raising."""
    settings = get_settings()
    ses_client = boto3.client("ses", region_name=settings.region, config=config)
    message = EmailMessage()
    message["From"] = settings.ses_email_source
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"Report for Shop ID {shop_id}"
    message.set_content(
        "Dear All,\n\n"
        "Please find the attached data for the previous week. "
        "In case the report exceeds email size limits, you will receive multiple emails.\n\n"
        "Best regards,\n"
        "Data Team"
    )
    message.add_attachment(
        excel_data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )

    try:
        email = ses_client.send_raw_email(
            Source=settings.ses_email_source,
            Destinations=recipients,
            RawMessage={"Data": message.as_bytes()},
        )
        logger.info("Email sent for %s; message ID: %s", filename, email["MessageId"])
    except (BotoCoreError, ClientError):
        logger.exception("Error sending email for %s", filename)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    handler(None, None)
