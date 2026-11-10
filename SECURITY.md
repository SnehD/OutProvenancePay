# Security policy

OutProvenance Pay is a prototype for the PayPal **Sandbox**. It is not production software and has
not been audited or certified.

## Reporting a vulnerability

Please open a private security advisory on the repository (or contact the maintainers directly) rather than
filing a public issue. Include steps to reproduce and the affected file or endpoint.

## Ground rules for contributors

- Never commit secrets: `.env` files, `backend/data/`, private keys (`*.pem`) and databases are git-ignored.
- Never use live PayPal credentials or real money. Sandbox only.
- Prices, sellers and policy outcomes must come from the backend. Do not add client-trusted fields.
- AI output is untrusted input and must stay advisory.

## Known limitations

See "Security limitations" in the README and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for residual risks,
including the lack of user authentication in this prototype.
