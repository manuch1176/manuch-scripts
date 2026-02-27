#!/usr/bin/env python3
"""
push-to-synology.py — Host-side cert push script
=================================================
Placed at:   /opt/cert-push/push-to-synology.py
Runs as:     root (via cron)
Schedule:    */15 * * * * root /usr/bin/python3 /opt/cert-push/push-to-synology.py

Workflow:
  1. Check for flag file written by the certbot deploy hook
  2. Translate the container-internal cert path to the host volume path
  3. Authenticate to DSM REST API
  4. Find the existing certificate by description
  5. Upload the renewed cert + key, replacing the existing entry
  6. Log out of DSM
  7. Delete the flag file

All credentials stay on this host and never touch the NPM container.

Volume mapping reference:
  /etc/letsencrypt  (inside container) -> /var/lib/docker/volumes/npm_letsencrypt/_data  (host)
  /data             (inside container) -> /var/lib/docker/volumes/npm_data/_data          (host)
  Lineage for my.hostname.com: npm-2

DSM 7 API notes:
  - Auth uses entry.cgi with version=7 (not auth.cgi / version=3)
  - Login must request enable_syno_token=yes
  - SynoToken must be passed as a query param on EVERY request (GET and POST)
  - Certificate import uses SYNO.Core.Certificate (not .CRT) with method=import

Author:  Manuel Wenger
License: MIT (see LICENSE file or https://opensource.org/licenses/MIT)

DISCLAIMER: This software is provided "as is", without warranty of any kind.
Use at your own risk. The author accepts no liability for any damage or data
loss caused by the use of this script.
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import ssl
import uuid
from pathlib import Path

# =============================================================================
# Configuration loader
# =============================================================================

CONFIG_FILE = "/opt/cert-push/push-to-synology.conf"


def load_config(path: str) -> dict:
    """Parse a simple key=value config file, ignoring comments and blank lines."""
    config = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()
    return config


# =============================================================================
# Logging setup
# =============================================================================

def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("cert-push")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")

    fh = logging.FileHandler(log_file)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# =============================================================================
# Multipart form builder (no external dependencies)
# =============================================================================

def build_multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """
    Build a multipart/form-data payload from fields (str->str) and
    files (str->(filename, bytes, content_type)).
    Returns (body_bytes, content_type_header_value).
    """
    boundary = uuid.uuid4().hex
    body = []

    for name, value in fields.items():
        body.append(f"--{boundary}".encode())
        body.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        body.append(b"")
        body.append(value.encode())

    for name, (filename, data, ctype) in files.items():
        body.append(f"--{boundary}".encode())
        body.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
        )
        body.append(f"Content-Type: {ctype}".encode())
        body.append(b"")
        body.append(data)

    body.append(f"--{boundary}--".encode())
    body.append(b"")

    payload = b"\r\n".join(body)
    content_type = f"multipart/form-data; boundary={boundary}"
    return payload, content_type


# =============================================================================
# DSM API client
# =============================================================================

class SynologyAPIError(Exception):
    pass


class SynologyClient:
    """
    Minimal Synology DSM 7 REST API client.
    Uses only stdlib — no external libraries needed.
    Disables SSL verification for internal LAN hosts (self-signed certs).

    DSM 7 requires:
    - Auth via entry.cgi with SYNO.API.Auth version=7
    - enable_syno_token=yes on login
    - SynoToken passed as query param on every subsequent request
    """

    def __init__(self, host: str, port: int, logger: logging.Logger):
        self.base_url = f"https://{host}:{port}/webapi"
        self.logger = logger
        self.sid = None
        self.token = ""
        # Accept self-signed certs on LAN
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def _get(self, endpoint: str, params: dict) -> dict:
        # Always inject SynoToken if we have one
        if self.token:
            params = dict(params)
            params["SynoToken"] = self.token
        url = f"{self.base_url}/{endpoint}?{urllib.parse.urlencode(params)}"
        self.logger.debug(f"GET {url}")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("success"):
            raise SynologyAPIError(f"API error: {data.get('error')}")
        return data.get("data", {})

    def _post_multipart(self, endpoint: str, fields: dict, files: dict) -> dict:
        url = f"{self.base_url}/{endpoint}"
        body, content_type = build_multipart(fields, files)
        req = urllib.request.Request(url, data=body)
        req.add_header("Content-Type", content_type)
        self.logger.debug(f"POST {url} (multipart, {len(body)} bytes)")
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("success"):
            raise SynologyAPIError(f"API error: {data.get('error')}")
        return data.get("data", {})

    def login(self, username: str, password: str):
        """
        Authenticate against DSM 7.
        Uses entry.cgi + version=7 + enable_syno_token=yes as required by DSM 7.
        Stores both sid and synotoken for all subsequent requests.
        """
        self.logger.info(f"Authenticating to DSM as '{username}'")
        # Login does not yet have a token, so call _get before token is set
        url = (
            f"{self.base_url}/entry.cgi?"
            + urllib.parse.urlencode({
                "api":              "SYNO.API.Auth",
                "version":          "7",
                "method":           "login",
                "account":          username,
                "passwd":           password,
                "session":          "cert-push",
                "format":           "sid",
                "enable_syno_token": "yes",
            })
        )
        self.logger.debug(f"GET {url}")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("success"):
            raise SynologyAPIError(f"Login failed: {data.get('error')}")
        self.sid   = data["data"]["sid"]
        self.token = data["data"].get("synotoken", "")
        self.logger.info("DSM authentication successful")
        self.logger.debug(f"SynoToken present: {bool(self.token)}")

    def logout(self):
        """Terminate the DSM session."""
        if not self.sid:
            return
        try:
            self._get("entry.cgi", {
                "api":     "SYNO.API.Auth",
                "version": "7",
                "method":  "logout",
                "session": "cert-push",
                "_sid":    self.sid,
            })
            self.logger.info("DSM session closed")
        except Exception as e:
            self.logger.warning(f"Logout failed (non-fatal): {e}")
        finally:
            self.sid = None
            self.token = ""

    def find_certificate_id(self, description: str) -> str:
        """
        Return the cert_id for the certificate matching the given description.
        Raises SynologyAPIError if not found.
        """
        self.logger.info(f"Looking up certificate with description '{description}'")
        data = self._get("entry.cgi", {
            "api":     "SYNO.Core.Certificate.CRT",
            "version": "1",
            "method":  "list",
            "_sid":    self.sid,
        })
        certs = data.get("certificates", [])
        self.logger.debug(f"Found {len(certs)} certificate(s) on DSM")
        for cert in certs:
            self.logger.debug(
                f"  - id={cert.get('id')} desc={cert.get('desc')} "
                f"subject={cert.get('subject', {}).get('common_name')}"
            )
            if cert.get("desc") == description:
                cert_id = cert["id"]
                self.logger.info(f"Matched certificate id: {cert_id}")
                return cert_id
        raise SynologyAPIError(
            f"No certificate with description '{description}' found on DSM. "
            f"Available descriptions: {[c.get('desc') for c in certs]}"
        )

    def upload_certificate(self, cert_id: str, cert_path: Path, key_path: Path, chain_path: Path):
        """
        Replace an existing DSM certificate with new cert/key files.

        Uses SYNO.Core.Certificate (not .CRT) — only this API has the import method.
        SynoToken and _sid go in the URL query string; cert fields in the multipart body.
        """
        self.logger.info(f"Uploading certificate (id={cert_id})")

        cert_data  = cert_path.read_bytes()
        key_data   = key_path.read_bytes()
        chain_data = chain_path.read_bytes() if chain_path.exists() else b""

        query_params = urllib.parse.urlencode({
            "api":       "SYNO.Core.Certificate",
            "method":    "import",
            "version":   "1",
            "SynoToken": self.token,
            "_sid":      self.sid,
        })

        fields = {
            "id":         cert_id,
            "desc":       "",        # keep existing description unchanged
            "as_default": "false",
        }

        files = {
            "cert": ("cert.pem",    cert_data, "application/x-pem-file"),
            "key":  ("privkey.pem", key_data,  "application/x-pem-file"),
        }
        if chain_data:
            files["inter_cert"] = ("chain.pem", chain_data, "application/x-pem-file")

        self._post_multipart(f"entry.cgi?{query_params}", fields, files)
        self.logger.info("Certificate uploaded successfully")


# =============================================================================
# Path translation
# =============================================================================

def translate_path(container_path: str, container_prefix: str, host_volume_path: str) -> Path:
    """
    Convert a container-internal path to the equivalent host path.

    Example:
      container_path     = /etc/letsencrypt/live/npm-2
      container_prefix   = /etc/letsencrypt
      host_volume_path   = /var/lib/docker/volumes/npm_letsencrypt/_data
      result             = /var/lib/docker/volumes/npm_letsencrypt/_data/live/npm-2
    """
    relative = Path(container_path).relative_to(container_prefix)
    return Path(host_volume_path) / relative


# =============================================================================
# Main
# =============================================================================

def main():
    if not os.path.exists(CONFIG_FILE):
        print(f"ERROR: Config file not found: {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(CONFIG_FILE)
    logger = setup_logging(cfg["LOG_FILE"])

    flag_file = Path(cfg["FLAG_FILE"])

    if not flag_file.exists():
        logger.debug("No flag file found — nothing to do")
        sys.exit(0)

    logger.info("=" * 60)
    logger.info("Flag file detected — starting certificate push")

    container_lineage = flag_file.read_text().strip()
    if not container_lineage:
        logger.error("Flag file is empty — cannot determine cert path. Removing flag.")
        flag_file.unlink()
        sys.exit(1)

    logger.info(f"Container lineage path: {container_lineage}")

    host_lineage = translate_path(
        container_lineage,
        cfg["CONTAINER_LETSENCRYPT_PATH"],
        cfg["NPM_LETSENCRYPT_PATH"],
    )
    logger.info(f"Host lineage path: {host_lineage}")

    cert_file  = host_lineage / "fullchain.pem"
    key_file   = host_lineage / "privkey.pem"
    chain_file = host_lineage / "chain.pem"

    for f in [cert_file, key_file]:
        if not f.exists():
            logger.error(f"Required cert file not found: {f}")
            sys.exit(1)

    logger.info(f"cert:  {cert_file}")
    logger.info(f"key:   {key_file}")
    logger.info(f"chain: {chain_file} ({'present' if chain_file.exists() else 'absent'})")

    client = SynologyClient(cfg["SYNO_HOST"], int(cfg["SYNO_PORT"]), logger)

    try:
        client.login(cfg["SYNO_USER"], cfg["SYNO_PASS"])
        cert_id = client.find_certificate_id(cfg["SYNO_CERT_DESC"])
        client.upload_certificate(cert_id, cert_file, key_file, chain_file)

        flag_file.unlink()
        logger.info("Flag file removed")
        logger.info("Certificate push completed successfully")

    except SynologyAPIError as e:
        logger.error(f"DSM API error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        client.logout()


if __name__ == "__main__":
    main()
