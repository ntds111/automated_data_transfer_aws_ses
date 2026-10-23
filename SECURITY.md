# Security policy

## Reporting a vulnerability

Do not publish credentials, report data, or exploit details in public issues.
Use GitHub's **Security → Advisories → Report a vulnerability** on this repository
when private vulnerability reporting is enabled:
https://github.com/ntds111/automated_data_transfer_aws_ses/security/advisories/new

If private reporting is unavailable, open an issue requesting a private reporting
channel without including vulnerability details. Include affected revisions,
impact, and a minimal reproduction only after a private channel is established.
Response times are best-effort; there is no guaranteed support SLA. Security fixes
target the latest default-branch revision.

## Deployment precautions

- Use IAM execution roles or local AWS profiles, never committed credentials.
- Restrict the caller's STS/SES permissions and the assumed role's Athena/S3/Glue
  permissions to required resources; account for encryption keys as necessary.
- The historical SAM example includes broad policies and placeholders. Audit and
  replace them before deployment.
- Verify intended recipients and SQL filters before enabling the schedule.
  Reports may contain sensitive business data; avoid logging report contents.
- Keep dependencies updated and verify changes with the mocked test suite.
- If credentials were exposed, revoke/rotate them immediately and review access
  logs; removing a file from the latest commit does not remove it from history.
