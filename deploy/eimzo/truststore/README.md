# E-IMZO sidecar truststore

This directory is mounted read-only into the `eimzo-server` sidecar at
`/opt/eimzo/truststore` (see `deploy/docker-compose.yml`). It must contain the
Uzbekistan **root + intermediate CA certificates** that the UNICON e-imzo-server
uses to validate signer certificate chains when verifying PKCS#7 signatures.

**The real production certificates are supplied out of band and are NOT committed
to this repository** — only this README placeholder is tracked so the bind-mount
path exists.

## Refresh procedure

1. Obtain the current O'zDSt root and intermediate certificates from the official
   E-IMZO / soliq.uz distribution (or the UNICON-provided bundle for your licensed
   e-imzo-server build).
2. Copy the PEM/DER files into this directory on the deployment host.
3. Restart the sidecar:
   ```bash
   docker compose --env-file .env -f deploy/docker-compose.yml --profile eimzo \
     restart eimzo-server
   ```
4. Confirm the sidecar comes back healthy (`docker compose ... ps eimzo-server`).

Review the bundle **at least annually** and whenever UNICON/soliq rotates a CA.
