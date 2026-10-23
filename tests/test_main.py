"""Deterministic report generation and mocked AWS integration tests."""

import io
import logging
import runpy
import zipfile
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock, call
from xml.etree import ElementTree

import pandas as pd
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

import main


def aws_error():
    return ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Denied"}}, "TestOperation"
    )


@pytest.mark.parametrize(
    "length,limit,sizes", [(0, 2, []), (4, 2, [2, 2]), (5, 2, [2, 2, 1])]
)
def test_split_dataframe_preserves_rows(length, limit, sizes):
    frame = pd.DataFrame({"value": range(length)})
    parts = main.split_dataframe(frame, limit)
    assert [len(part) for part in parts] == sizes
    if parts:
        pd.testing.assert_frame_equal(pd.concat(parts), frame)


@pytest.mark.parametrize("limit", [0, -1])
def test_split_dataframe_rejects_invalid_limit(limit):
    with pytest.raises(ValueError, match="positive"):
        main.split_dataframe(pd.DataFrame({"value": [1]}), limit)


def test_excel_contains_sheet_and_values_without_index():
    data = main.dataframe_to_excel(pd.DataFrame({"name": ["café"], "count": [7]}))
    with zipfile.ZipFile(io.BytesIO(data)) as workbook:
        assert workbook.testzip() is None
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        assert sheet.find("s:dimension", ns).attrib["ref"] == "A1:B2"
        assert sheet.find(".//s:c[@r='B2']/s:v", ns).text == "7"
        assert "café" in workbook.read("xl/sharedStrings.xml").decode()
        assert b"Sheet1" in workbook.read("xl/workbook.xml")


def test_assume_role_and_client_credentials(monkeypatch):
    credentials = {
        "AccessKeyId": "placeholder-access",
        "SecretAccessKey": "placeholder-secret",
        "SessionToken": "placeholder-session",
    }
    client = Mock()
    client.assume_role.return_value = {"Credentials": credentials}
    factory = Mock(return_value=client)
    monkeypatch.setattr(main.boto3, "client", factory)
    assert main.assume_role("role-arn") == credentials
    client.assume_role.assert_called_once_with(
        RoleArn="role-arn", RoleSessionName="LambdaSession"
    )
    main.get_client("s3", credentials)
    assert factory.call_args_list == [
        call("sts", region_name="eu-central-1"),
        call(
            "s3",
            region_name="eu-central-1",
            aws_access_key_id="placeholder-access",
            aws_secret_access_key="placeholder-secret",
            aws_session_token="placeholder-session",
        ),
    ]


@pytest.mark.parametrize(
    "error",
    [aws_error(), EndpointConnectionError(endpoint_url="https://sts.example.com")],
)
def test_assume_role_logs_and_reraises(monkeypatch, caplog, error):
    client = Mock()
    client.assume_role.side_effect = error
    monkeypatch.setattr(main.boto3, "client", Mock(return_value=client))
    with pytest.raises(type(error)):
        main.assume_role("role-arn")
    assert "Error assuming reporting role" in caplog.text


@pytest.mark.parametrize("state", ["SUCCEEDED", "FAILED", "CANCELLED"])
def test_athena_polling(monkeypatch, state):
    client = Mock()
    client.start_query_execution.return_value = {"QueryExecutionId": "query-id"}
    client.get_query_execution.side_effect = [
        {"QueryExecution": {"Status": {"State": "RUNNING"}}},
        {"QueryExecution": {"Status": {"State": state}}},
    ]
    monkeypatch.setenv("ATHENA_DATABASE", "reports")
    monkeypatch.setenv("ATHENA_OUTPUT_LOCATION", "s3://reports/output/")
    monkeypatch.setattr(main, "get_client", Mock(return_value=client))
    sleep = Mock()
    monkeypatch.setattr(main.time, "sleep", sleep)
    if state == "SUCCEEDED":
        assert main.run_athena_query("SELECT 1", {}) == "query-id"
    else:
        with pytest.raises(RuntimeError, match=state):
            main.run_athena_query("SELECT 1", {})
    sleep.assert_called_once_with(5)
    client.start_query_execution.assert_called_once_with(
        QueryString="SELECT 1",
        QueryExecutionContext={"Database": "reports"},
        ResultConfiguration={"OutputLocation": "s3://reports/output/"},
    )
    assert client.get_query_execution.call_args_list == [
        call(QueryExecutionId="query-id"),
        call(QueryExecutionId="query-id"),
    ]


def test_athena_start_failure_propagates(monkeypatch):
    client = Mock()
    client.start_query_execution.side_effect = aws_error()
    monkeypatch.setattr(main, "get_client", Mock(return_value=client))
    with pytest.raises(ClientError):
        main.run_athena_query("SELECT 1", {})


def test_download_uses_actual_output_and_closes_body(monkeypatch):
    athena, s3 = Mock(), Mock()
    athena.get_query_execution.return_value = {
        "QueryExecution": {
            "ResultConfiguration": {
                "OutputLocation": "s3://workgroup-bucket/nested/id.csv"
            }
        }
    }
    body = io.BytesIO("name,count\ncafé,7\n".encode())
    s3.get_object.return_value = {"Body": body}
    factory = Mock(side_effect=[athena, s3])
    monkeypatch.setattr(main, "get_client", factory)
    result = main.download_athena_results("id", {})
    pd.testing.assert_frame_equal(
        result, pd.DataFrame({"name": ["café"], "count": [7]})
    )
    assert body.closed
    s3.get_object.assert_called_once_with(
        Bucket="workgroup-bucket", Key="nested/id.csv"
    )
    assert factory.call_args_list == [call("athena", {}), call("s3", {})]


def test_download_closes_body_on_parse_error(monkeypatch):
    athena, s3 = Mock(), Mock()
    athena.get_query_execution.return_value = {
        "QueryExecution": {
            "ResultConfiguration": {"OutputLocation": "s3://bucket/id.csv"}
        }
    }
    body = io.BytesIO(b"")
    s3.get_object.return_value = {"Body": body}
    monkeypatch.setattr(main, "get_client", Mock(side_effect=[athena, s3]))
    with pytest.raises(pd.errors.EmptyDataError):
        main.download_athena_results("id", {})
    assert body.closed


@pytest.mark.parametrize(
    "location",
    ["https://example.com/result", "s3://", "s3://bucket", "s3://bucket/", "s3:///key"],
)
def test_invalid_s3_location(location):
    with pytest.raises(ValueError, match="Athena output"):
        main.parse_s3_location(location)


def test_ses_attachment_roundtrip(monkeypatch, caplog):
    client = Mock()
    client.send_raw_email.return_value = {"MessageId": "message-id"}
    factory = Mock(return_value=client)
    monkeypatch.setattr(main.boto3, "client", factory)
    monkeypatch.setenv("SES_EMAIL_SOURCE", "reports@example.com")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    recipients = ["a@example.com", "b@example.com"]
    with caplog.at_level(logging.INFO):
        main.send_email_with_attachment(b"excel-bytes", "report.xlsx", 42, recipients)
    args = client.send_raw_email.call_args.kwargs
    assert args["Source"] == "reports@example.com"
    assert args["Destinations"] == recipients
    message = BytesParser(policy=policy.default).parsebytes(args["RawMessage"]["Data"])
    assert message["Subject"] == "Report for Shop ID 42"
    assert message["To"] == ", ".join(recipients)
    (attachment,) = message.iter_attachments()
    assert attachment.get_filename() == "report.xlsx"
    assert attachment.get_content_type() == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert attachment.get_payload(decode=True) == b"excel-bytes"
    assert "previous week" in message.get_body().get_content()
    assert "message-id" in caplog.text
    factory.assert_called_once_with("ses", region_name="us-east-1", config=main.config)


@pytest.mark.parametrize(
    "error",
    [aws_error(), EndpointConnectionError(endpoint_url="https://ses.example.com")],
)
def test_ses_failure_is_logged_without_raising(monkeypatch, caplog, error):
    client = Mock()
    client.send_raw_email.side_effect = error
    monkeypatch.setattr(main.boto3, "client", Mock(return_value=client))
    main.send_email_with_attachment(b"data", "report.xlsx", 42, ["a@example.com"])
    assert "Error sending email for report.xlsx" in caplog.text


def test_email_header_injection_is_rejected(monkeypatch):
    client = Mock()
    monkeypatch.setattr(main.boto3, "client", Mock(return_value=client))
    monkeypatch.setenv("SES_EMAIL_SOURCE", "a@example.com\nBcc: b@example.com")
    with pytest.raises(ValueError):
        main.send_email_with_attachment(b"data", "report.xlsx", 42, ["a@example.com"])
    client.send_raw_email.assert_not_called()


def test_handler_continues_after_shop_failure(monkeypatch, caplog):
    credentials = {"Credentials": "placeholder"}
    monkeypatch.setattr(main, "assume_role", Mock(return_value=credentials))
    run_query = Mock(side_effect=[RuntimeError("query failed"), "query-id"])
    monkeypatch.setattr(main, "run_athena_query", run_query)
    monkeypatch.setenv("ATHENA_QUERY", "SELECT {shop_id}")
    monkeypatch.setattr(
        main, "download_athena_results", Mock(return_value=pd.DataFrame({"value": [1]}))
    )
    send = Mock()
    monkeypatch.setattr(main, "send_email_with_attachment", send)
    assert main.handler({}, None) is None
    assert run_query.call_args_list == [
        call("SELECT 12345", credentials),
        call("SELECT 67890", credentials),
    ]
    assert send.call_args.args[1:3] == ("athena_query_results_shop_67890.xlsx", 67890)
    assert "Error for shop_id 12345" in caplog.text


@pytest.mark.parametrize(
    "rows,suffixes", [(0, []), (1, [""]), (65001, ["_part1", "_part2"])]
)
def test_handler_attachment_names_and_chunking(monkeypatch, rows, suffixes):
    monkeypatch.setenv("SHOP_RECIPIENTS", '{"42": ["a@example.com"]}')
    monkeypatch.setattr(main, "assume_role", Mock(return_value={}))
    monkeypatch.setattr(main, "run_athena_query", Mock(return_value="id"))
    monkeypatch.setattr(
        main,
        "download_athena_results",
        Mock(return_value=pd.DataFrame({"value": range(rows)})),
    )
    excel = Mock(return_value=b"data")
    monkeypatch.setattr(main, "dataframe_to_excel", excel)
    send = Mock()
    monkeypatch.setattr(main, "send_email_with_attachment", send)
    main.handler(None, None)
    assert send.call_args_list == [
        call(
            b"data", f"athena_query_results_shop_42{suffix}.xlsx", 42, ["a@example.com"]
        )
        for suffix in suffixes
    ]
    assert [len(args.args[0]) for args in excel.call_args_list] == (
        [] if rows == 0 else [1] if rows == 1 else [65000, 1]
    )


def test_local_entrypoint_is_executable_without_cloud(monkeypatch):
    """Exercise __main__ with SDK stubs and no query rows to email."""
    monkeypatch.setenv("SHOP_RECIPIENTS", '{"42": ["a@example.com"]}')
    client = Mock()
    client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "placeholder-access",
            "SecretAccessKey": "placeholder-secret",
            "SessionToken": "placeholder-session",
        }
    }
    client.start_query_execution.return_value = {"QueryExecutionId": "id"}
    client.get_query_execution.return_value = {
        "QueryExecution": {
            "Status": {"State": "SUCCEEDED"},
            "ResultConfiguration": {"OutputLocation": "s3://bucket/id.csv"},
        }
    }
    client.get_object.return_value = {"Body": io.BytesIO(b"value\n")}
    monkeypatch.setattr(main.boto3, "client", Mock(return_value=client))
    runpy.run_path(main.__file__, run_name="__main__")
    client.start_query_execution.assert_called_once()
    client.get_object.assert_called_once_with(Bucket="bucket", Key="id.csv")
    client.send_raw_email.assert_not_called()
