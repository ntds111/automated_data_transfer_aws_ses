# Automated Athena reports via AWS SES

[![CI](https://github.com/ntds111/automated_data_transfer_aws_ses/actions/workflows/ci.yml/badge.svg)](https://github.com/ntds111/automated_data_transfer_aws_ses/actions/workflows/ci.yml)

An AWS Lambda reporting template that queries Athena, reads CSV results from S3,
and emails per-shop Excel reports through SES. Replace the example SQL, resources,
and recipients before using it with real data.

## Architecture

`main.handler(event, context)` → STS role assumption → Athena query/polling →
S3 CSV download → pandas → XLSX chunks (65,000 rows) → SES raw email.

Athena and S3 use the assumed role; SES uses the caller's credentials. Each shop's
failure is logged and does not prevent later shops from running. SES delivery
errors are logged rather than raised, matching the original behavior. Empty
results produce no email. The event and context arguments are currently unused.

The flat layout deliberately preserves `main.py` and its public functions:

- `main.py`: Lambda/local entry point and reporting functions.
- `config.py`: environment-backed configuration (no AWS calls at import time).
- `tests/`: deterministic unit tests with mocked AWS boundaries.
- `pyproject.toml`: lint, format, pytest, and coverage configuration; this is a
  deployable application, not an installable library.
- `function_to_copy_config_from.yaml`: historical SAM example, **not a
  production-ready deployment**. Replace placeholders and audit its broad IAM
  policies before deployment.

## Setup and local run

Use Python **3.11 or 3.12** (the Docker runtime is 3.11). From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env: SQL, resources, sender, and recipients must match your environment.
set -a
source .env
set +a
AWS_PROFILE=reporting python main.py
```

For runtime-only installations, use `python -m pip install -r requirements.txt`.
`.env` is not loaded automatically; source only a trusted local file. The
application makes real AWS calls and sends real emails when run normally.

Configure your local AWS profile separately (for example with AWS CLI SSO).
Lambda uses its execution role. Do not commit credentials. The caller needs
`sts:AssumeRole` and `ses:SendRawEmail`; the assumed role needs Athena query
permissions, Glue catalog access as appropriate, and access to the result bucket
(including any applicable KMS permissions). SES identities must be verified in the
configured region; sandbox accounts also require verified recipients.

## Environment variables

All application configuration is read at invocation time. Defaults preserve the
original example settings but are **not usable production configuration**.

| Variable | Purpose / default |
| --- | --- |
| `AWS_REGION` | All clients' region; defaults to `eu-central-1`. |
| `AWS_ROLE_ARN` | Reporting role; replace the original placeholder ARN. |
| `SES_EMAIL_SOURCE` | Verified SES sender; replace the original placeholder. |
| `ATHENA_DATABASE` | Athena database; defaults to `default`. |
| `ATHENA_OUTPUT_LOCATION` | S3 result prefix; replace `s3://s3_bucket_folder/output_folder_name`. Downloads use Athena's actual output URI, including workgroup overrides. |
| `ATHENA_QUERY` | SQL template; replace `your query here`. Literal `{shop_id}` is substituted with the integer shop ID. Include your own date range and shop filter. |
| `SHOP_RECIPIENTS` | JSON object mapping integer shop IDs (JSON string keys) to nonempty email lists. Defaults to the two original example shops and recipients. |

Boto3's standard credential chain supports `AWS_PROFILE`, local AWS configuration,
or `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN`.
These are not application-specific settings; prefer profiles or IAM roles.

## Quality checks

```bash
python -m ruff check .
python -m black --check .
python -m pytest --cov --cov-report=term-missing
pre-commit install
pre-commit run --all-files
```

To apply formatting/import fixes: `python -m ruff check . --fix` then
`python -m black .`. CI runs lint, formatting, and tests with a 90% coverage floor
on Python 3.11 and 3.12 for pushes and pull requests. Tests do not need AWS
credentials and reject unmocked AWS client creation.

## Docker / Lambda

The image retains AWS's Lambda base image and runtime interface. Lambda supplies
a least-privileged user at deployment; no custom `USER` overrides that behavior.
The Docker build installs dependencies before copying source for layer caching.

```bash
docker build -t athena-reports .
# Docker env files must not contain shell quotes around JSON/SQL values.
# Create a private .env.docker with the same settings, but without those quotes.
docker run --rm -p 9000:8080 --env-file .env.docker \
  -e AWS_PROFILE=reporting -v "$HOME/.aws:/root/.aws:ro" athena-reports
# In another terminal (this invokes real reporting):
curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H 'Content-Type: application/json' -d '{}'
```

Push the built image to your own ECR repository and configure Lambda environment
variables, execution role, memory, timeout, and schedule for your workload.
Do not bake `.env` or credentials into the image. The historical SAM example
contains a daily 04:00 UTC schedule and placeholder image URI.

## Troubleshooting and limitations

- **AccessDenied / role assumption:** check caller permissions, trust policy, S3,
  Glue, workgroup, and KMS access. SES uses the caller, not the assumed role.
- **SES rejection:** verify sender/recipients and SES sandbox status in
  `AWS_REGION`. Inspect local logs or Lambda CloudWatch logs for delivery errors.
- **Query failure:** verify SQL, database, result bucket, and workgroup settings.
  Polling remains every five seconds until a terminal state; configure a Lambda
  timeout appropriate for the workload (the historical 60-second example may be
  insufficient). Local runs have no overall polling deadline.
- **Large reports:** row-based splitting does **not** guarantee SES byte-size
  limits. Wide rows/base64 overhead may still cause rejection. Results and Excel
  attachments are held in memory; provision Lambda memory accordingly.
- **No email / successful invocation despite errors:** empty results send nothing;
  shop and SES failures are logged and swallowed by design. Monitor logs, not
  just Lambda invocation status.

## Compatibility and migration

`python main.py`, `main.handler`, and existing helper signatures remain available.
No `src/` migration is required. Docker's previously nonexistent
`lambda_function.handler` target is corrected to `main.handler`; update external
handler overrides if needed. Python 3.9 is replaced by supported Python 3.11.
The AWS SDK pins are updated to permit a patched HTTP transport. Configuration
now honors the documented environment variables; existing example defaults remain.
Message text, recipient grouping, chunk sizes, filenames, and error isolation
are retained; MIME serialization and diagnostic logging are standardized.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and
[SECURITY.md](SECURITY.md). Licensed under the [MIT License](LICENSE).
