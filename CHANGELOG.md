# Changelog

## Unreleased

### Added
- Environment-backed reporting configuration and safe configuration example.
- Ruff, Black, pytest coverage, pre-commit hooks, and Python 3.11/3.12 CI.
- Mocked AWS/reporting tests and contributor/security documentation.
- MIT license matching the license previously declared in the README.

### Changed
- Preserved the flat layout, `main.handler`, and report-generation semantics.
- Standardized logging, docstrings, MIME email construction, and AWS error logging.
- Read downloads from Athena's actual S3 result URI and close response streams.
- Corrected Docker source/handler references and adopted Python 3.11.
- Updated AWS SDK pins to support a patched urllib3 transport; pinned XlsxWriter.
- Pinned NumPy to a wheel-compatible release for the Python 3.11 Lambda base.
- Normalized the historical SAM template's invalid indentation without changing
  its example configuration.
