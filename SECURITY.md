# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, guardrail bypass, or secret-detection false negative in **NetArk (`netark-mcp`)**, please report it responsibly:

1. **Do NOT open a public GitHub issue** for active exploits or credential-exposure bugs.
2. Use GitHub's **Private Vulnerability Reporting** ("Security" tab ➔ "Report a vulnerability") on the repository, or contact the maintainer listed in `pyproject.toml` (`joinblue42@gmail.com`).
3. Include a minimal reproducible payload (e.g., `PreToolUse` stdin JSON or AST snippet) and your Python / OS version.

## Deterministic Guard Boundaries & Honest Scope

NetArk is designed as a **deterministic local pre-execution harness** (`PreToolUse` AST, secret regex + Shannon entropy DLP, SSRF host checks, and path placement enforcement). Please keep the following architectural boundaries in mind:

- **Static / Heuristic Defense Layer**: Tier-0 checks inspect tool parameters, file contents, and shell AST patterns locally without network telemetry. Determined adversaries with direct shell execution outside hooked AI tool calls are governed by OS permissions, not MCP hooks.
- **No Secret Storage**: NetArk never writes `.env*`, `auth.json`, or `*vault*.json` files and blocks AI agents from reading or writing them (`SEC-CRED`).
- **Supply Chain Integrity**: Official PyPI releases are built and published automatically from tagged commits via GitHub Actions OIDC Trusted Publishing with Sigstore attestations (`attestations: true`).
