#!/bin/sh
# =============================================================================
# push-to-synology.sh — certbot deploy hook (runs inside NPM container)
#
# Placed at:
#   /var/lib/docker/volumes/npm_letsencrypt/_data/renewal-hooks/deploy/
#
# This script is intentionally minimal and contains NO credentials.
# It only writes a flag file to signal the host-side Python script.
#
# Certbot injects these environment variables automatically:
#   RENEWED_DOMAINS  — space-separated list of renewed domains
#   RENEWED_LINEAGE  — path to the renewed cert directory (inside container)
# =============================================================================

TARGET_DOMAIN="my.hostname.com"
FLAG_FILE="/etc/letsencrypt/.cert-renewed"

# Only act if our target domain was part of this renewal
case " $RENEWED_DOMAINS " in
    *" $TARGET_DOMAIN "*)
        # Write flag file with the lineage path so the host script knows
        # which cert directory to read from.
        printf '%s\n' "$RENEWED_LINEAGE" > "$FLAG_FILE"
        echo "[push-to-synology] Flag written for $TARGET_DOMAIN (lineage: $RENEWED_LINEAGE)"
        ;;
    *)
        # Not our cert — do nothing
        echo "[push-to-synology] Skipping (target domain not in renewal: $RENEWED_DOMAINS)"
        ;;
esac
