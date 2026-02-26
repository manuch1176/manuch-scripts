# Copy Let's Encrypt SSL certificate from Nginx Proxy Manager (NPM) to Synology DSM

## Volume mapping reference

In these examples, NPM is running inside Docker on an AlmaLinux host, in the same
LAN segment like the Synology.

Adapt as needed in push-to-synology.conf:

    Inside container        →  Host path  
    /etc/letsencrypt        →  /var/lib/docker/volumes/npm_letsencrypt/_data  
    /data                   →  /var/lib/docker/volumes/npm_data/_data  

    Hook script:    /var/lib/docker/volumes/npm_letsencrypt/_data/renewal-hooks/deploy/  
    Flag file:      /var/lib/docker/volumes/npm_letsencrypt/_data/.cert-renewed  

    Lineage for desired certificate: npm-2
    LAN IP of the Synology: 192.168.0.5

## 1. Create the DSM service account

In DSM → Control Panel → User & Group → Create:
  - Username:       certupdater
  - Password:       (strong, random — must match SYNO_PASS in conf)
  - Groups:         administrators
  - Shared folders: deny all
  - Applications:   allow DSM, deny all


## 2. Find the lineage for the desired certificate

    grep -l "my.hostname.com" /var/lib/docker/volumes/npm_letsencrypt/_data/renewal/*.conf

    /var/lib/docker/volumes/npm_letsencrypt/_data/renewal/npm-2.conf


## 3. Deploy the hook script (runs inside NPM container)

    # The renewal-hooks/deploy directory already exists in the letsencrypt volume
    cp push-to-synology.sh \
      /var/lib/docker/volumes/npm_letsencrypt/_data/renewal-hooks/deploy/push-to-synology.sh

    chmod +x \
      /var/lib/docker/volumes/npm_letsencrypt/_data/renewal-hooks/deploy/push-to-synology.sh


## 4. Deploy the host-side script and config

    mkdir -p /opt/cert-push

    cp push-to-synology.py   /opt/cert-push/
    cp push-to-synology.conf /opt/cert-push/

    chmod 700 /opt/cert-push
    chmod 600 /opt/cert-push/push-to-synology.conf
    chmod 700 /opt/cert-push/push-to-synology.py

    # Fill in the password
    vi /opt/cert-push/push-to-synology.conf


## 5. Install cron job (runs as root every 15 minutes)

    cat > /etc/cron.d/cert-push << 'EOF'
    */15 * * * * root /usr/bin/python3 /opt/cert-push/push-to-synology.py
    EOF

    chmod 644 /etc/cron.d/cert-push


## 6. Test the full pipeline manually

    # Step 1: Simulate what the certbot hook writes (lineage is npm-2)
    echo "/etc/letsencrypt/live/npm-2" > \
      /var/lib/docker/volumes/npm_letsencrypt/_data/.cert-renewed

    # Step 2: Run the Python script manually
    python3 /opt/cert-push/push-to-synology.py

    # Step 3: Check the log
    cat /opt/cert-push/push-to-synology.log
<!-- -->
```
# python3 /opt/cert-push/push-to-synology.py
2026-02-27T15:55:21 [INFO] ============================================================
2026-02-27T15:55:21 [INFO] Flag file detected — starting certificate push
2026-02-27T15:55:21 [INFO] Container lineage path: /etc/letsencrypt/live/npm-2
2026-02-27T15:55:21 [INFO] Host lineage path: /var/lib/docker/volumes/npm_letsencrypt/_data/live/npm-2
2026-02-27T15:55:21 [INFO] cert:  /var/lib/docker/volumes/npm_letsencrypt/_data/live/npm-2/fullchain.pem
2026-02-27T15:55:21 [INFO] key:   /var/lib/docker/volumes/npm_letsencrypt/_data/live/npm-2/privkey.pem
2026-02-27T15:55:21 [INFO] chain: /var/lib/docker/volumes/npm_letsencrypt/_data/live/npm-2/chain.pem (present)
2026-02-27T15:55:21 [INFO] Authenticating to DSM as 'certupdater'
2026-02-27T15:55:21 [DEBUG] GET https://192.168.0.5:5001/webapi/entry.cgi?api=SYNO.API.Auth&version=7&method=login
2026-02-27T15:55:22 [INFO] DSM authentication successful
2026-02-27T15:55:22 [DEBUG] SynoToken present: True
2026-02-27T15:55:22 [INFO] Looking up certificate with description 'my.hostname.com'
2026-02-27T15:55:22 [DEBUG] GET https://192.168.0.5:5001/webapi/entry.cgi?api=SYNO.Core.Certificate.CRT&version=1&method=list
2026-02-27T15:55:22 [DEBUG] Found 3 certificate(s) on DSM
2026-02-27T15:55:22 [DEBUG]   - id=xxxxx desc=Synology QuickConnect Certificate subject=xxxxx.direct.quickconnect.to
2026-02-27T15:55:22 [DEBUG]   - id=yyyyy desc= subject=synology.com
2026-02-27T15:55:22 [DEBUG]   - id=zzzzz desc=my.hostname.com subject=my.hostname.com
2026-02-27T15:55:22 [INFO] Matched certificate id: zzzzz
2026-02-27T15:55:22 [INFO] Uploading certificate (id=zzzzz)
2026-02-27T15:55:22 [DEBUG] POST https://192.168.0.5:5001/webapi/entry.cgi?api=SYNO.Core.Certificate&method=import (multipart, 5509 bytes)
2026-02-27T15:56:03 [INFO] Certificate uploaded successfully
2026-02-27T15:56:03 [INFO] Flag file removed
2026-02-27T15:56:03 [INFO] Certificate push completed successfully
2026-02-27T15:56:03 [DEBUG] GET https://192.168.0.5:5001/webapi/entry.cgi?api=SYNO.API.Auth&version=7&method=logout
2026-02-27T15:56:03 [INFO] DSM session closed
```

## 6. Verify on DSM

    DSM → Control Panel → Security → Certificate
    Check the expiry date of my.hostname.com — it should match NPM's cert.


## Notes

- The flag file is deleted automatically on success.
  If the push fails (DSM unreachable, wrong credentials, etc.),
  the flag file is left in place and the cron retries every 15 minutes.

- The hook script silently does nothing if a different cert is renewed —
  it only fires for my.hostname.com.
