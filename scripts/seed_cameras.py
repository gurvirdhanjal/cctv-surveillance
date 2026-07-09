"""Seed the 5 plant-floor cameras via the running VMS API.

Reads RTSP URLs from .env, logs in as admin, then upserts the 5 real cameras.
Does NOT require direct DB access — only the API server must be running.

Usage:
    venv/Scripts/python.exe scripts/seed_cameras.py
    venv/Scripts/python.exe scripts/seed_cameras.py --api http://localhost:8080 --user admin --password changeme
    venv/Scripts/python.exe scripts/seed_cameras.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Load camera URL env vars from .env (skip DB and JWT dummy values)
_SKIP_KEYS = {"VMS_DB_URL", "VMS_JWT_SECRET"}
_root = Path(__file__).resolve().parent.parent
_env_file = _root / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        if _k not in _SKIP_KEYS:
            os.environ.setdefault(_k, _v.strip())


# ── camera definitions ──────────────────────────────────────────────────────
# URL decode percent-encoded passwords from .env so we can pass them as plain
# text to the from-credentials endpoint (the endpoint re-encodes them).
def _decode(url: str) -> dict[str, str | int]:
    """Parse rtsp://user:pass@host:port/path into credential fields."""
    parsed = urllib.parse.urlparse(url)
    return {
        "host": parsed.hostname or "",
        "port": parsed.port or 554,
        "username": urllib.parse.unquote(parsed.username or ""),
        "password": urllib.parse.unquote(parsed.password or ""),
        "stream_path": parsed.path.lstrip("/"),
    }


def _cam(name: str, env_var: str, tier: str = "FULL") -> dict:
    url = os.environ.get(env_var, "")
    if not url:
        return {}
    creds = _decode(url)
    return {"name": name, "capability_tier": tier, "shutter_type": "rolling", **creds}


CAMERAS = [
    _cam("Back Gate", "VMS_CAM_GATE_BACK_URL"),
    _cam("Front Gate", "VMS_CAM_GATE_FRONT_URL"),
    _cam("Gate 4", "VMS_CAM_GATE_4_URL"),
    _cam("Indoor 2", "VMS_CAM_INDOOR_2_URL"),
    _cam("ANPR Gate", "VMS_CAM_ANPR_URL"),
]


def _api(api_base: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    url = f"{api_base}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if payload is not None else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"  HTTP {exc.code} {url}: {body[:200]}")
        return {}


def main(api_base: str, username: str, password: str, dry_run: bool) -> None:
    missing = [c["name"] for c in CAMERAS if not c]
    if missing:
        print(f"ERROR: missing env vars for: {missing}")
        sys.exit(1)

    if dry_run:
        print("Dry run — no API calls will be made.\n")
        for cam in CAMERAS:
            print(
                f"  Would add: {cam['name']} ({cam['host']}:{cam['port']}) path={cam['stream_path']}"
            )
        return

    # Login
    print(f"Logging in as {username} at {api_base}…")
    resp = _api(api_base, "/api/auth/token", {"username": username, "password": password})
    token = resp.get("access_token", "")
    if not token:
        print("Login failed — check --user / --password.")
        sys.exit(1)
    print("  Logged in OK.\n")

    # Fetch existing cameras
    existing_resp = _api(api_base, "/api/cameras", token=token)
    existing_names = {
        c.get("name") for c in (existing_resp if isinstance(existing_resp, list) else [])
    }

    added = 0
    for cam in CAMERAS:
        if cam["name"] in existing_names:
            print(f"  SKIP {cam['name']} — already exists")
            continue
        print(f"  ADD  {cam['name']} ({cam['host']}:{cam['port']})…", end=" ")
        result = _api(api_base, "/api/cameras/from-credentials", cam, token=token)
        if result.get("camera_id"):
            print(f"camera_id={result['camera_id']}")
            added += 1
        else:
            print("FAILED")

    print(f"\nDone — {added} camera(s) added.")
    if added == 0 and len(existing_names) > 0:
        print("All cameras already exist. To re-seed, delete them from the admin panel first.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the 5 plant-floor cameras via the API")
    parser.add_argument("--api", default="http://localhost:8080")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(api_base=args.api, username=args.user, password=args.password, dry_run=args.dry_run)
