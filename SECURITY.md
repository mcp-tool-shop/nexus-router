# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

**Please do not file public issues for security vulnerabilities.**

If you discover a security vulnerability in nexus-router, please report it privately:

1. **Email**: Send details to security@mcp-tool-shop.dev
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes (optional)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 7 days
- **Resolution target**: Within 30 days for critical issues

## Security Considerations

### Event Store

- SQLite database files may contain sensitive execution logs
- Use appropriate file permissions for persistent databases
- Consider encryption at rest for production deployments

### Policy Enforcement

- `allow_apply: false` prevents destructive operations
- `max_steps` limits execution scope
- Schema validation rejects malformed requests

### Provenance

- SHA256 digests provide integrity verification
- Provenance records are append-only
- Method IDs are immutable once defined

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who report valid vulnerabilities (with permission).
