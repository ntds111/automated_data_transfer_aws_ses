import base64
import time
import boto3
import io
import pandas as pd
from botocore.exceptions import ClientError
from botocore.config import Config
 
config = Config(retries={'max_attempts': 10, 'mode': 'standard'}, read_timeout=360, connect_timeout=360)
boto3.setup_default_session(region_name="eu-central-1")
 
 
def handler(event, context):
    credentials = assume_role('arn:aws:iam::1234567890:role/your-role-name')
 
    shop_queries = {
        12345: [
            "dummyemail1@gmail.com",
            "dummyemail2@gmail.com",
            "dummyemail3@gmail.com"
        ],
        67890: [
            "dummyemail1@gmail.com",
            "dummyemail2@gmail.com",
            "dummyemail3@gmail.com"
        ]
    }
 
 
    # Updated grouping recipients by shop_id
    for shop_id, recipients in shop_queries.items():
        query = f"""
        your query here
        """
 
        print(f"Starting Athena query execution for shop_id {shop_id}...")
        try:
            query_execution_id = run_athena_query(query, credentials)
            output_df = download_athena_results(query_execution_id, credentials)
            split_dfs = split_dataframe(output_df, max_rows=65000)
 
            for i, df_part in enumerate(split_dfs):
                excel_data = dataframe_to_excel(df_part)
                part_suffix = f"_part{i + 1}" if len(split_dfs) > 1 else ""
                filename = f'athena_query_results_shop_{shop_id}{part_suffix}.xlsx'
 
                # Send a single email to all recipients for this shop_id
                send_email_with_attachment(excel_data, filename, shop_id, recipients)
 
        except Exception as e:
            print(f"Error for shop_id {shop_id}: {e}")
            continue
 
 
def assume_role(role_arn: str):
    sts_client = boto3.client('sts')
    try:
        assumed_role = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="LambdaSession")
    except sts_client.exceptions.ClientError as e:
        print(f"Error assuming role: {e}")
        raise
    return assumed_role['Credentials']
 
 
def get_client(service_name: str, credentials: dict):
    return boto3.client(
        service_name,
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
 
 
def run_athena_query(query: str, credentials: dict):
    client = get_client('athena', credentials)
    execution = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': 'default'},
        ResultConfiguration={
            'OutputLocation': 's3://s3_bucket_folder/output_folder_name'
        }
    )
    query_execution_id = execution['QueryExecutionId']
    while True:
        query_status = client.get_query_execution(QueryExecutionId=query_execution_id)
        state = query_status['QueryExecution']['Status']['State']
        if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            break
        time.sleep(5)
    if state != 'SUCCEEDED':
        raise Exception(f"Athena query execution failed with state: {state}")
    return query_execution_id
 
 
def download_athena_results(query_execution_id: str, credentials: dict) -> pd.DataFrame:
    s3_client = get_client('s3', credentials)
    bucket_name = 'bucket-name'
    key = f'output_folder_name/{query_execution_id}.csv'
    s3_response = s3_client.get_object(Bucket=bucket_name, Key=key)
    return pd.read_csv(io.BytesIO(s3_response['Body'].read()), encoding='utf8')
 
 
def split_dataframe(df: pd.DataFrame, max_rows: int) -> list:
    """Splits DataFrame into smaller DataFrames with a maximum number of rows."""
    return [df.iloc[i:i + max_rows] for i in range(0, len(df), max_rows)]
 
 
def dataframe_to_excel(df: pd.DataFrame) -> bytes:
    excel_writer = io.BytesIO()
    with pd.ExcelWriter(excel_writer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Sheet1', index=False)
    return excel_writer.getvalue()
 
 
def send_email_with_attachment(excel_data: bytes, filename: str, shop_id: int, recipients: list):
    ses_client = boto3.client('ses', region_name='eu-central-1', config=config)
    sender = "someemail.aws.yourcompanyhostname.cloud"
    subject = f"Report for Shop ID {shop_id}"
 
    # Generate the list of recipient names from the email addresses
    recipient_names = ', '.join([recipient.split('@')[0].split('.')[0].capitalize() for recipient in recipients])
 
    # Compose email body
    body_text = (
        f"Dear All,\n\n"
        "Please find the attached data for the previous week. "
        "In case the report exceeds email size limits, you will receive multiple emails.\n\n"
        "Best regards,\n"
        "Data Team"
    )
 
    encoded_data = base64.b64encode(excel_data).decode('utf-8')
 
    try:
        # Send email to all recipients
        email = ses_client.send_raw_email(
            Source=sender,
            Destinations=recipients,  # Sending to all recipients
            RawMessage={
                'Data': f"From: {sender}\n"
                        f"To: {', '.join(recipients)}\n"  # Joining all recipients with commas
                        f"Subject: {subject}\n"
                        f"MIME-Version: 1.0\n"
                        f"Content-Type: multipart/mixed; boundary=\"NextPart\"\n\n"
                        f"--NextPart\n"
                        f"Content-Type: text/plain\n\n"
                        f"{body_text}\n\n"
                        f"--NextPart\n"
                        f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet; name=\"{filename}\"\n"
                        f"Content-Transfer-Encoding: base64\n"
                        f"Content-Disposition: attachment; filename=\"{filename}\"\n\n"
                        f"{encoded_data}\n"
                        f"--NextPart--"
            }
        )
        print(f"Email sent to {', '.join(recipients)} for {filename}! Message ID:", email['MessageId'])
    except ClientError as e:
        print(f"Error sending email to {', '.join(recipients)} for {filename}: {e}")
        return
 
 
if __name__ == "__main__":
    handler(None, None)
