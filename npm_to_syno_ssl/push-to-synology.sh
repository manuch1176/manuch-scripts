#!/bin/bash
# =============================================================================
# push-to-synology.sh — certbot deploy hook (runs inside NPM container)
#
# Placed at:
#   /var/lib/docker/volumes/npm_letsencrypt/_data/renewal-hooks/deploy/
#
# This script is intentionally minimal and contains NO credentials.
# It only writes a flag file to signal the host-side Python script.
#
# The target domain is read from a companion file in the letsencrypt volume:
#   /etc/letsencrypt/.cert-push-domain  (inside container)
#   = <NPM_LETSENCRYPT_PATH>/.cert-push-domain  (on host)
# That file must contain a single line: the domain whose certificate should
# be pushed to Synology (e.g.  my.hostname.com).
#
# Certbot injects these environment variables automatically:
#   RENEWED_DOMAINS  — space-separated list of renewed domains
#   RENEWED_LINEAGE  — path to the renewed cert directory (inside container)
#
# Author:  Manuel Wenger
# License: MIT (see LICENSE file or https://opensource.org/licenses/MIT)
#
# DISCLAIMER: This software is provided "as is", without warranty of any kind.
# Use at your own risk. The author accepts no liability for any damage or data
# loss caused by the use of this script.
# =============================================================================

set -euo pipefail

DOMAIN_FILE="/etc/letsencrypt/.cert-push-domain"
FLAG_FILE="/etc/letsencrypt/.cert-renewed"

# Read target domain from companion config file
if [ ! -f "$DOMAIN_FILE" ]; then
    echo "[push-to-synology] ERROR: Domain config file not found: $DOMAIN_FILE" >&2
    echo "[push-to-synology] Create it on the host at the letsencrypt volume path containing just the target domain name." >&2
    exit 1
fi

TARGET_DOMAIN="$(cat "$DOMAIN_FILE")"

if [ -z "$TARGET_DOMAIN" ]; then
    echo "[push-to-synology] ERROR: Domain config file is empty: $DOMAIN_FILE" >&2
    exit 1
fi

# Only act if our target domain was part of this renewal
case " $RENEWED_DOMAINS " in
    *" $TARGET_DOMAIN "*)
        # Write flag file with the lineage path so the host script knows
        # which cert directory to read from.
        if ! printf '%s\n' "$RENEWED_LINEAGE" > "$FLAG_FILE"; then
            echo "[push-to-synology] ERROR: Failed to write flag file: $FLAG_FILE" >&2
            exit 1
        fi
        echo "[push-to-synology] Flag written for $TARGET_DOMAIN (lineage: $RENEWED_LINEAGE)"
        ;;
    *)
        # Not our cert — do nothing
        echo "[push-to-synology] Skipping (target domain not in renewal: $RENEWED_DOMAINS)"
        ;;
esac
