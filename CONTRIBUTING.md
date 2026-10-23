# Contributing

Use Python 3.11 or 3.12. Create and activate a virtual environment, then install
`python -m pip install -r requirements-dev.txt` from the repository root.
Install hooks with `pre-commit install`.

## Workflow

1. Make a focused change with deterministic tests in `tests/`.
2. Run `python -m ruff check . --fix` and `python -m black .`.
3. Run `python -m pytest tests/test_main.py -q` for reporting changes or
   `python -m pytest tests/test_config.py -q` for configuration changes.
4. Before opening a PR, run the same checks as CI:
   ```bash
   python -m ruff check .
   python -m black --check .
   python -m pytest --cov --cov-report=term-missing
   pre-commit run --all-files
   ```
5. Explain behavior changes, compatibility, and verification in the PR; add an
   entry to `CHANGELOG.md` when changing user-facing behavior.

## Standards

- Keep the existing flat application layout and public `main.handler` entry point.
- Use Black's 88-column formatting and Ruff's configured lint/import checks.
- Add concise module and function docstrings. Use module loggers rather than
  prints; never log credentials or report contents.
- Read application settings through `config.get_settings`; do not create AWS
  clients or load credentials during imports.
- Mock all cloud/network boundaries. Tests must pass without AWS credentials.
  The test fixture rejects any AWS client creation not explicitly mocked.
- Retain per-shop error isolation unless deliberately changing its contract.
- Keep secrets and generated reports out of commits; use `.env.example` for
  safe configuration examples. Discuss vulnerabilities privately as described
  in `SECURITY.md`.

The historical SAM template is illustrative and requires an IAM/placeholder
review before real deployment. Do not use it as a production permissions model.
