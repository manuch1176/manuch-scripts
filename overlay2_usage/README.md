# docker_overlay2_usage.py

Finds the largest directories in Docker's overlay storage and maps them
to their containers. Works with both:

  - Classic Docker overlay2     (e.g. AlmaLinux / RHEL)  
    Path:    /var/lib/docker/overlay2  
    Mapping: via GraphDriver.Data (UpperDir / LowerDir)

  - Containerd overlayfs        (e.g. Ubuntu with containerd snapshotter)  
    Path:    /var/lib/docker/rootfs/overlayfs  
    Mapping: directory name IS the full container ID

The correct mode is detected automatically via 'docker info'.

Modes currently not supported: vfs, devicemapper, btrfs, zfs, aufs.

## Requirements

- Python 3.9+
- Root privileges
- Docker installed and running

## Usage

```bash
sudo python3 docker_overlay2_usage.py [--top N] [--min-size MB] [--path PATH]
```

| Argument | Description | Default |
|----------|-------------|---------|
| `--top N` | Show the N largest directories | 10 |
| `--min-size MB` | Only show directories larger than MB megabytes | 0 |
| `--path PATH` | Path of overlayfs, if different from defaults | /var/lib/docker/rootfs/overlayfs or /var/lib/docker/overlay2 |

**Examples:**

```bash
# Show top 10 largest overlay2 directories
sudo python3 docker_overlay2_usage.py

# Show top 5 entries larger than 500 MB
sudo python3 docker_overlay2_usage.py --top 5 --min-size 500
```

## Sample output

```bash
# python3 docker_overlay2_usage.py 

================================================================================
  Docker overlay2 disk usage — top 20 directories
  Base path: /var/lib/docker/overlay2
================================================================================

🔍 Scanning directory sizes...
🔍 Building container → overlay2 map...

      SIZE  LAYER ID                              CONTAINER       STATUS      NAME / IMAGE
--------------------------------------------------------------------------------------------------------------
    4.6 GB  3aad80ca8453053f28c9fe1b35e98349563606d794a8cd3229d167795d770df9  e85fd3014c2e    running     openwebui  (ghcr.io/open-webui/open-webui:main)
    3.1 GB  21ed1234b008b6dc50ced6bce645ac452a45707cd62178ff965796a315797072  e85fd3014c2e    running     openwebui  (ghcr.io/open-webui/open-webui:main)
    2.1 GB  661efa57515f368fd8ac6caec9f3d8b25799f7f5ccda36871f3c850fc0eeacc1  17c1ae0e7f5a    running     webtop  (lscr.io/linuxserver/webtop:latest)
    1.7 GB  cb4814cca99668a5cf33fd978e3c3b723f5ef9d510d355c64be52a8ef11ccd28  4419ff7fab0d    running     homebridge  (oznu/homebridge:ubuntu)
    1.3 GB  38dca9589b29e2ef340bfdb7bcae90f82bdd2eac24dc930acdd54bea09540aae  17c1ae0e7f5a    running     webtop  (lscr.io/linuxserver/webtop:latest)
  999.7 MB  10e0d8f3c2f10fbcfedc36abd1690d9f3e407a5748f4d98fa13487ed61bef385  e85fd3014c2e    running     openwebui  (ghcr.io/open-webui/open-webui:main)
  967.1 MB  b1e853ca5931fdea5c881e5f807d0e508ea60c6666e40b6c2a052c12ff45d9fb  0204be874545    running     npm_app  (jc21/nginx-proxy-manager:latest)
  828.1 MB  cf009dd7a2629a411e653fa92f7376b1157022d6bad11f4581d3f87b689741e5  4794e32a6bca    running     docmost  (docmost/docmost:latest)
  787.8 MB  ac550e619730d3675a8e8d787b92c7f1603faa687fb7b0ddca3eb1b2d01cd6cd  17c1ae0e7f5a    running     webtop  (lscr.io/linuxserver/webtop:latest)
  580.9 MB  0c39aaa17a0f4ba0eee6bbc702537f370eb0dc7b84499d5532b8e430fe717427  4419ff7fab0d    running     homebridge  (oznu/homebridge:ubuntu)
  535.9 MB  ff114459c2fa85ea45885e846181c8fdd7974b6abf3d7fa9f67742dede8c0932  0204be874545    running     npm_app  (jc21/nginx-proxy-manager:latest)
  528.8 MB  4c6a29229f79994fd782ff4bc2c0560d0ec6ae487a311fc4fb3d4ce7c6417b1e  4794e32a6bca    running     docmost  (docmost/docmost:latest)
  517.5 MB  7c2ec686b647b2812414fbd0a8df9ae3a886f85bf495abf2573023f11a17c8e8                              — (image layer / build cache / not matched)
  500.0 MB  be11ca3147910869390a4c3b905a3228f0a8c390c53a0275ec4bbc4bd1545f5d  bf2e2eef56bb    running     uptime-kuma  (louislam/uptime-kuma)
  481.1 MB  da1d7f30c5d3c310d90fd994605038469d2986aed8538cd623cb57b9221f79a8                              — (image layer / build cache / not matched)
  447.7 MB  696393a8d9b5de165c0b5ce0167c1144fcc7b09ce8bf8afdc9b7a8a5cca2658a  274159e5dd02    running     postgres  (postgres:18)
  331.8 MB  af7df891de44349dec3f7203dc32c3a19a8c58c14c529d316226fa88c1c2bba9  050dde5cbf4b    running     npm_db  (mariadb:latest)
  323.5 MB  0ac6c8335459215457a3eae2eedf00ee92ade04d83e5026cbddb7b12548cf636  274159e5dd02    running     postgres  (postgres:18)
  291.8 MB  c7f890c33515dcfd1368bae2a9567a6879b5c95f056027e47b26a94aebbaab14  4419ff7fab0d    running     homebridge  (oznu/homebridge:ubuntu)
  280.4 MB  4ae21700dc09151f3ff648803010ba82ab123ce149ac66cf6270be7c754da92e  841250d869b0    running     forgejo  (codeberg.org/forgejo/forgejo:13)

================================================================================
  2 unmatched entries = image layers, build cache, or dangling volumes
  Tip: run 'docker system df' for a high-level overview
  Tip: run 'docker system prune' to remove unused data
```

## Disclaimer

This software is provided "as is", without warranty of any kind. Use at your own risk. The author accepts no liability for any damage or data loss caused by the use of this script.

## License

[MIT](../LICENSE) © Manuel Wenger
