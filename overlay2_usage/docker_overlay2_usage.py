#!/usr/bin/env python3
"""
docker_overlay2_usage.py

Finds the largest directories in Docker's overlay storage and maps them
to their containers. Works with both:

  - Classic Docker overlay2     (e.g. AlmaLinux / RHEL)
    Path:    /var/lib/docker/overlay2
    Mapping: via GraphDriver.Data (UpperDir / LowerDir)

  - Containerd overlayfs        (e.g. Ubuntu with containerd snapshotter)
    Path:    /var/lib/docker/rootfs/overlayfs
    Mapping: directory name IS the full container ID

The correct mode is detected automatically via 'docker info'.
    
Requires: root privileges, Docker installed
Usage: sudo python3 docker_overlay2_usage.py [--top N] [--min-size MB] [--path PATH]

Author:  Manuel Wenger
License: MIT (see LICENSE file or https://opensource.org/licenses/MIT)

DISCLAIMER: This software is provided "as is", without warranty of any kind.
Use at your own risk. The author accepts no liability for any damage or data
loss caused by the use of this script.
"""


import subprocess
import json
import os
import argparse
from typing import Optional

# Known default paths per storage driver
DRIVER_PATHS = {
    "overlay2":   "/var/lib/docker/overlay2",
    "overlayfs":  "/var/lib/docker/rootfs/overlayfs",
}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_storage_driver() -> str:
    """Return the Docker storage driver name from 'docker info'."""
    result = subprocess.run(
        ["docker", "info", "--format", "{{.Driver}}"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def resolve_overlay_path(driver: str, override: Optional[str]) -> str:
    if override:
        return override
    path = DRIVER_PATHS.get(driver)
    if path and os.path.isdir(path):
        return path
    # Fallback: scan known paths
    for p in DRIVER_PATHS.values():
        if os.path.isdir(p):
            return p
    raise RuntimeError(
        f"Cannot find overlay storage directory for driver '{driver}'. "
        f"Use --path to specify it manually."
    )


# ---------------------------------------------------------------------------
# Disk usage
# ---------------------------------------------------------------------------

def get_dir_sizes(path: str, top_n: int) -> list:
    """Return (size_bytes, dir_path) for immediate subdirs, sorted descending."""
    result = subprocess.run(
        ["du", "--max-depth=1", path],
        capture_output=True, text=True
    )
    entries = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            size_kb, dirpath = int(parts[0]), parts[1]
            if dirpath != path:
                entries.append((size_kb * 1024, dirpath))
    entries.sort(reverse=True)
    return entries[:top_n]


# ---------------------------------------------------------------------------
# Container maps — one per architecture
# ---------------------------------------------------------------------------

def get_containers() -> list:
    """Return basic info for all containers (including stopped)."""
    result = subprocess.run(
        ["docker", "ps", "-aq", "--no-trunc"],
        capture_output=True, text=True
    )
    containers = []
    for cid in result.stdout.strip().splitlines():
        inspect = subprocess.run(
            ["docker", "inspect", cid],
            capture_output=True, text=True
        )
        try:
            data = json.loads(inspect.stdout)[0]
        except (json.JSONDecodeError, IndexError):
            continue
        containers.append({
            "full_id":  cid,
            "short_id": cid[:12],
            "name":     data.get("Name", "").lstrip("/"),
            "image":    data.get("Config", {}).get("Image", "unknown"),
            "status":   data.get("State", {}).get("Status", "unknown"),
            "graph":    data.get("GraphDriver", {}),
        })
    return containers


def build_map_overlay2(containers: list, overlay_path: str) -> dict:
    """
    Classic overlay2 (AlmaLinux / RHEL):
    Extract layer IDs from GraphDriver.Data paths and map them to containers.
    """
    overlay_map = {}
    for c in containers:
        if c["graph"].get("Name") != "overlay2":
            continue
        layers = c["graph"].get("Data", {})
        for key in ("UpperDir", "LowerDir", "WorkDir", "MergedDir"):
            val = layers.get(key, "")
            for part in val.split(":"):
                part = part.strip()
                if part.startswith(overlay_path):
                    rel = os.path.relpath(part, overlay_path)
                    layer_id = rel.split(os.sep)[0]
                    if layer_id and layer_id != "l":
                        overlay_map[layer_id] = c
    return overlay_map


def build_map_containerd(containers: list) -> dict:
    """
    Containerd overlayfs (Ubuntu):
    Directory name == full container ID. Build a simple full_id -> info map.
    """
    return {c["full_id"]: c for c in containers}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyse Docker overlay disk usage — supports overlay2 and containerd overlayfs"
    )
    parser.add_argument("--top",      type=int, default=20,   help="Show top N directories (default: 20)")
    parser.add_argument("--min-size", type=int, default=100,  help="Minimum size in MB to display (default: 100)")
    parser.add_argument("--path",     type=str, default=None, help="Override overlay storage path")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("⚠️  Warning: not running as root. Results may be incomplete.")

    # --- Auto-detect ---
    driver = detect_storage_driver()
    overlay_path = resolve_overlay_path(driver, args.path)
    is_containerd = (driver == "overlayfs")

    print(f"\n{'='*90}")
    print(f"  Docker overlay disk usage — top {args.top} directories")
    print(f"  Storage driver : {driver}")
    print(f"  Base path      : {overlay_path}")
    print(f"  Mode           : {'containerd overlayfs' if is_containerd else 'classic overlay2'}")
    print(f"{'='*90}\n")

    print("🔍 Scanning directory sizes...")
    entries = get_dir_sizes(overlay_path, args.top)

    print("🔍 Inspecting containers...")
    containers = get_containers()

    if is_containerd:
        overlay_map = build_map_containerd(containers)
    else:
        overlay_map = build_map_overlay2(containers, overlay_path)

    min_bytes = args.min_size * 1024 * 1024

    print(f"\n{'SIZE':>10}  {'CONTAINER ID':14}  {'STATUS':10}  {'NAME':25}  IMAGE")
    print("-" * 100)

    unmatched = 0
    for size, dirpath in entries:
        if size < min_bytes:
            continue

        dir_name = os.path.basename(dirpath)

        # Containerd: also handle <id>-init layers
        base_id = dir_name.removesuffix("-init") if is_containerd else dir_name
        suffix   = " (init)" if is_containerd and dir_name.endswith("-init") else ""

        info = overlay_map.get(base_id)

        if info:
            print(
                f"{format_size(size):>10}  {info['short_id']:14}  {info['status']:10}  "
                f"{info['name']:25}  {info['image']}{suffix}"
            )
        else:
            print(
                f"{format_size(size):>10}  {dir_name[:12]:14}  {'':10}  "
                f"{'— image layer / build cache':25}{suffix}"
            )
            unmatched += 1

    print(f"\n{'='*90}")
    print(f"  {unmatched} unmatched = image layers, build cache, or dangling data")
    print(f"  Tip: 'docker system df'    — high-level usage overview")
    print(f"  Tip: 'docker system prune' — remove all unused data\n")


if __name__ == "__main__":
    main()
