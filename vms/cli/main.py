"""vms-cli — small click-based CLI to inspect the running VMS.

Examples:
  vms-cli alerts list --api http://localhost:8000 --token $TOK
  vms-cli alerts tail --api http://localhost:8000 --token $TOK
  vms-cli detectors status --api http://localhost:8000 --token $TOK
  vms-cli head-count --api http://localhost:8000 --token $TOK
"""

from __future__ import annotations

import json
import sys
import time

import click
import httpx


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@click.group()
def cli() -> None:
    """VMS inspection CLI."""


@cli.group()
def alerts() -> None:
    """Alert inspection."""


@alerts.command("list")
@click.option("--api", required=True)
@click.option("--token", required=True)
@click.option("--state", default=None)
@click.option("--alert-type", default=None)
@click.option("--limit", default=50, type=int)
def alerts_list(
    api: str, token: str, state: str | None, alert_type: str | None, limit: int
) -> None:
    params: dict[str, str | int] = {"limit": limit}
    if state:
        params["state"] = state
    if alert_type:
        params["alert_type"] = alert_type
    r = httpx.get(f"{api}/api/alerts", headers=_headers(token), params=params)
    if r.status_code != 200:
        click.echo(f"error: HTTP {r.status_code}", err=True)
        sys.exit(2)
    for a in r.json():
        click.echo(json.dumps(a))


@alerts.command("tail")
@click.option("--api", required=True)
@click.option("--token", required=True)
@click.option("--interval", default=1.0, type=float)
def alerts_tail(api: str, token: str, interval: float) -> None:
    seen: set[int] = set()
    while True:
        r = httpx.get(
            f"{api}/api/alerts",
            headers=_headers(token),
            params={"state": "active", "limit": 50},
        )
        if r.status_code == 200:
            for a in r.json():
                if a["alert_id"] not in seen:
                    seen.add(a["alert_id"])
                    click.echo(json.dumps(a))
        time.sleep(interval)


@cli.group()
def detectors() -> None:
    """Detector inspection."""


@detectors.command("status")
@click.option("--api", required=True)
@click.option("--token", required=True)
def detectors_status(api: str, token: str) -> None:
    r = httpx.get(f"{api}/api/anomaly-detectors/health", headers=_headers(token))
    click.echo(json.dumps(r.json(), indent=2))


@cli.command("head-count")
@click.option("--api", required=True)
@click.option("--token", required=True)
def head_count(api: str, token: str) -> None:
    r = httpx.get(f"{api}/api/state/snapshot", headers=_headers(token))
    body = r.json()
    click.echo(json.dumps(body.get("head_count", {}), indent=2))
