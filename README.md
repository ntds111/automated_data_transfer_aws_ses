# automated_data_transfer_aws_ses

# Reporting Tool

This project provides an AWS Lambda function to query data from Athena, process the results, and send email reports with Excel attachments. It is designed for automating the generation and distribution ofExcel reports for specific shops within a pre-defined time range. The emails include Excel files with processed data, segmented to fit within attachment size limits.

## Features

- Query AWS Athena for click costs and product information for specific shops.
- Process query results using pandas.
- Split large datasets into manageable parts for email attachments.
- Send reports as emails with Excel files using AWS SES (Simple Email Service).
- Role assumption via AWS STS (Security Token Service) for secure access.

## Prerequisites

Before deploying or running the project, ensure the following prerequisites are met:

- **AWS Credentials:** Proper IAM roles and permissions are configured for accessing Athena, S3, and SES.
- **Boto3:** AWS SDK for Python for interacting with AWS services.
- **Pandas:** Data processing library.
- **Athena Database:** The required Athena database and tables should exist.
- **S3 Bucket:** The bucket for Athena query results must be set up and accessible.

## Setup

### 1. Install Dependencies
Ensure you have `boto3`, `pandas`, and `xlsxwriter` installed in your environment.

### 2. AWS Configuration
Configure your AWS credentials using the `aws configure` command or set up your credentials via environment variables.

### 3. Role Assumption
The script uses an IAM role to assume the necessary permissions. Ensure that this role has the correct trust relationships and policies in place.

### 4. SES Email Configuration
The script uses AWS SES to send emails. Ensure the `send_raw_email` API is available in the region you're working with (in this case, `your-region`).

### 5. Athena Query Setup
The Athena query used to retrieve data is based on specific tables and databases.

## How to Run

The main script is designed to be executed as a Lambda function, but you can also run it locally for testing purposes. The `handler` function is the entry point.



### Important Functions

- `assume_role(role_arn)`: Assumes an AWS IAM role using STS.
- `run_athena_query(query, credentials)`: Executes an Athena query and monitors its execution status.
- `download_athena_results(query_execution_id, credentials)`: Downloads the results of the executed Athena query from S3.
- `dataframe_to_excel(df)`: Converts a pandas DataFrame to an Excel file.
- `send_email_with_attachment(excel_data, filename, shop_id, recipients)`: Sends emails with the Excel file as an attachment using AWS SES.

## Environment Variables

- **AWS_REGION**: Region for AWS services.
- **AWS_ROLE_ARN**: IAM role to assume for accessing the required AWS resources.
- **SES_EMAIL_SOURCE**: Email address used as the sender in SES.


## Deployment

To deploy this script as a Lambda function use Docker


## Known Issues

- **Email Size Limit**: AWS SES imposes a limit on the size of emails. The script handles this by splitting the dataset into multiple parts if necessary.
- **Athena Query Timing**: Large queries may take some time to execute. Ensure that the Athena query timeout is long enough to avoid premature failures.

## License

This project is licensed under the MIT License.

---
