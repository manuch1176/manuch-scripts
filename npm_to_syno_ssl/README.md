# cert-push

Automatically pushes a renewed Let's Encrypt certificate from
[Nginx Proxy Manager](https://nginxproxymanager.com/) to a Synology NAS running DSM 7,
without storing any credentials inside the NPM Docker container.

## The problem

When Nginx Proxy Manager sits in front of a Synology DSM service, the Synology cannot
obtain its own Let's Encrypt certificate via the built-in DSM UI — Let's Encrypt's
HTTP-01 challenge hits NPM first, which proxies to DSM's HTTPS port, resulting in a 404.

The cleanest solution is to let NPM own the certificate and push it to DSM on every renewal.

## Architecture

```
certbot (inside NPM container)
     │
     │  renewal-hooks/deploy fires
     ▼
push-to-synology.sh                  ← runs inside container, NO credentials
     │  writes a flag file to the letsencrypt volume
     │
     │  (container boundary — credentials never cross this line)
     │
Host cron (every 15 min)
     │
     ▼
push-to-synology.py                  ← runs on host, reads credentials from host only
     │  detects flag file
     │  reads cert files from NPM letsencrypt volume
     │  calls DSM REST API (SYNO.Core.Certificate import)
     │  removes flag file on success
     ▼
Synology DSM API (port 5001, HTTPS)
     │
     ▼
DSM distributes cert to all its services
```

The key security property: **credentials never enter the NPM container**. A compromised
NPM instance can at most write a flag file, which would trigger a re-push of the same
valid certificate — harmless.

## Requirements

- Nginx Proxy Manager running in Docker
- Synology NAS running DSM 7.x
- Python 3.9+ on the Docker host (no external libraries needed — stdlib only)
- Root access on the Docker host for the cron job

## Files

| File | Location | Purpose |
|------|----------|---------|
| `push-to-synology.sh` | NPM letsencrypt volume → `renewal-hooks/deploy/` | Thin certbot hook, writes flag file only |
| `push-to-synology.py` | `/opt/cert-push/` on host | Reads flag, calls DSM API, pushes cert |
| `push-to-synology.conf` | `/opt/cert-push/` on host | Credentials and paths (chmod 600) |

## Notes

- The flag file is deleted on success. If DSM is unreachable at renewal time, the flag
  stays in place and the cron job retries every 15 minutes automatically.
- The hook script does nothing if a different domain's certificate is renewed — it checks
  `$RENEWED_DOMAINS` before writing the flag.
- No external Python libraries are required. The script uses only stdlib (`urllib`,
  `ssl`, `json`, `pathlib`).
- The DSM certificate API requires the user to be in the `administrators` group. There is
  no finer-grained permission for certificate management in DSM 7. Compensate by denying
  all shared folder access, all application access except DSM, and blocking SSH login
  for the account.

## Setup

See [SETUP.md](SETUP.md) for full installation instructions.

## Disclaimer

This software is provided "as is", without warranty of any kind. Use at your own risk.
The author accepts no liability for any damage or data loss caused by the use of this script.

## License

[MIT](../LICENSE) © Manuel Wenger
