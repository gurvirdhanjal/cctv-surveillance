"""
Seed the database with realistic demo data for development.
Usage:
    python scripts/seed_demo_data.py
Reads VMS_DB_URL from environment (defaults to dev DB).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from vms.db.models import (  # noqa: E402
    Alert,
    AlertRouting,
    Camera,
    MaintenanceWindow,
    Person,
    User,
    Zone,
)
from vms.db.session import Base  # noqa: E402

DB_URL = os.environ.get("VMS_DB_URL", "postgresql://vms:vms@localhost:5432/vms")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc).replace(tzinfo=None)


def ago(**kwargs: int) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).replace(tzinfo=None)


def main() -> None:
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        # ── Cameras ──────────────────────────────────────────────────────────
        cameras = [
            Camera(
                name="Main Entrance",
                rtsp_url="rtsp://cam01.plant.local:554/stream",
                capability_tier="FULL",
                shutter_type="global",
                is_active=True,
            ),
            Camera(
                name="Assembly Line A",
                rtsp_url="rtsp://cam02.plant.local:554/stream",
                capability_tier="FULL",
                shutter_type="rolling",
                is_active=True,
            ),
            Camera(
                name="Warehouse Bay 1",
                rtsp_url="rtsp://cam03.plant.local:554/stream",
                capability_tier="MID",
                shutter_type="rolling",
                is_active=True,
            ),
            Camera(
                name="Server Room",
                rtsp_url="rtsp://cam04.plant.local:554/stream",
                capability_tier="FULL",
                shutter_type="global",
                is_active=True,
            ),
            Camera(
                name="Loading Dock",
                rtsp_url="rtsp://cam05.plant.local:554/stream",
                capability_tier="LOW",
                shutter_type="unknown",
                is_active=True,
            ),
        ]
        for cam in cameras:
            existing = db.query(Camera).filter_by(name=cam.name).first()
            if not existing:
                db.add(cam)
        db.flush()
        print(f"Cameras: {db.query(Camera).count()} total")

        cam_ids = {c.name: c.camera_id for c in db.query(Camera).all()}

        # ── Zones ─────────────────────────────────────────────────────────────
        zones = [
            Zone(
                name="Reception",
                is_restricted=False,
                is_active=True,
                max_capacity=20,
                loiter_threshold_s=300,
            ),
            Zone(
                name="Assembly Floor",
                is_restricted=False,
                is_active=True,
                max_capacity=50,
                loiter_threshold_s=600,
            ),
            Zone(
                name="Restricted Storage",
                is_restricted=True,
                is_active=True,
                max_capacity=5,
                loiter_threshold_s=60,
            ),
            Zone(
                name="Server Room",
                is_restricted=True,
                is_active=True,
                max_capacity=3,
                loiter_threshold_s=30,
            ),
            Zone(
                name="Loading Bay",
                is_restricted=False,
                is_active=True,
                max_capacity=15,
                loiter_threshold_s=180,
            ),
        ]
        for zone in zones:
            existing = db.query(Zone).filter_by(name=zone.name).first()
            if not existing:
                db.add(zone)
        db.flush()
        print(f"Zones: {db.query(Zone).count()} total")

        zone_ids = {z.name: z.zone_id for z in db.query(Zone).all()}

        # ── Persons ───────────────────────────────────────────────────────────
        persons = [
            Person(employee_id="EMP-001", name="Arjun Sharma", is_active=True),
            Person(employee_id="EMP-002", name="Priya Patel", is_active=True),
            Person(employee_id="EMP-003", name="Ravi Kumar", is_active=True),
            Person(employee_id="EMP-004", name="Sunita Mehta", is_active=True),
            Person(employee_id="EMP-005", name="Amit Singh", is_active=True),
        ]
        for person in persons:
            existing = db.query(Person).filter_by(employee_id=person.employee_id).first()
            if not existing:
                db.add(person)
        db.flush()
        print(f"Persons: {db.query(Person).count()} total")

        # ── Alert routing ─────────────────────────────────────────────────────
        routing_rules = [
            AlertRouting(
                alert_type="INTRUSION",
                severity="HIGH",
                channel="WEBHOOK",
                target="https://hooks.example.com/vms-security",
                is_active=True,
            ),
            AlertRouting(
                alert_type="UNKNOWN_PERSON",
                severity=None,
                channel="EMAIL",
                target="security@plant.local",
                is_active=True,
            ),
            AlertRouting(
                alert_type=None,
                severity="HIGH",
                channel="SLACK",
                target="#vms-alerts",
                is_active=True,
            ),
        ]
        if db.query(AlertRouting).count() == 0:
            for rule in routing_rules:
                db.add(rule)
        db.flush()
        print(f"Alert routing rules: {db.query(AlertRouting).count()} total")

        # ── Alerts ────────────────────────────────────────────────────────────
        admin_user = db.query(User).filter_by(username="admin").first()
        admin_id = admin_user.user_id if admin_user else None

        alerts_data = [
            Alert(
                alert_type="INTRUSION",
                severity="HIGH",
                state="active",
                camera_id=cam_ids.get("Server Room"),
                zone_id=zone_ids.get("Server Room"),
                triggered_at=ago(minutes=5),
            ),
            Alert(
                alert_type="UNKNOWN_PERSON",
                severity="MEDIUM",
                state="active",
                camera_id=cam_ids.get("Main Entrance"),
                triggered_at=ago(minutes=12),
            ),
            Alert(
                alert_type="LOITERING",
                severity="LOW",
                state="acknowledged",
                camera_id=cam_ids.get("Warehouse Bay 1"),
                zone_id=zone_ids.get("Loading Bay"),
                triggered_at=ago(hours=1),
                acknowledged_at=ago(minutes=45),
                acknowledged_by=admin_id,
            ),
            Alert(
                alert_type="CROWD_DENSITY",
                severity="MEDIUM",
                state="active",
                camera_id=cam_ids.get("Assembly Line A"),
                zone_id=zone_ids.get("Assembly Floor"),
                triggered_at=ago(minutes=30),
            ),
            Alert(
                alert_type="PPE_VIOLATION",
                severity="HIGH",
                state="active",
                camera_id=cam_ids.get("Assembly Line A"),
                zone_id=zone_ids.get("Assembly Floor"),
                triggered_at=ago(minutes=8),
            ),
            Alert(
                alert_type="INTRUSION",
                severity="HIGH",
                state="resolved",
                camera_id=cam_ids.get("Server Room"),
                zone_id=zone_ids.get("Restricted Storage"),
                triggered_at=ago(hours=3),
                acknowledged_at=ago(hours=2, minutes=50),
                acknowledged_by=admin_id,
                resolved_at=ago(hours=2, minutes=30),
            ),
            Alert(
                alert_type="VIOLENCE",
                severity="CRITICAL",
                state="active",
                camera_id=cam_ids.get("Loading Dock"),
                triggered_at=ago(minutes=2),
            ),
            Alert(
                alert_type="UNKNOWN_PERSON",
                severity="MEDIUM",
                state="resolved",
                camera_id=cam_ids.get("Main Entrance"),
                triggered_at=ago(hours=5),
                acknowledged_at=ago(hours=4, minutes=55),
                acknowledged_by=admin_id,
                resolved_at=ago(hours=4, minutes=40),
            ),
        ]
        if db.query(Alert).count() == 0:
            for alert in alerts_data:
                db.add(alert)
        db.flush()
        print(f"Alerts: {db.query(Alert).count()} total")

        # ── Maintenance windows ───────────────────────────────────────────────
        if admin_id and db.query(MaintenanceWindow).count() == 0:
            windows = [
                MaintenanceWindow(
                    name="Weekly Cam 3 Maintenance",
                    scope_type="CAMERA",
                    scope_id=cam_ids.get("Warehouse Bay 1", 1),
                    schedule_type="RECURRING",
                    cron_expr="0 2 * * 0",
                    duration_minutes=120,
                    suppress_alert_types='["INTRUSION","LOITERING"]',
                    is_active=True,
                    reason="Weekly lens cleaning and focus check",
                    created_by=admin_id,
                ),
                MaintenanceWindow(
                    name="Assembly Floor Deep Clean",
                    scope_type="ZONE",
                    scope_id=zone_ids.get("Assembly Floor", 1),
                    schedule_type="ONE_TIME",
                    starts_at=ago(hours=26),
                    ends_at=ago(hours=24),
                    suppress_alert_types='["CROWD_DENSITY","LOITERING"]',
                    is_active=True,
                    reason="Monthly floor deep clean — workers expected outside normal pattern",
                    created_by=admin_id,
                ),
            ]
            for mw in windows:
                db.add(mw)
            db.flush()
        print(f"Maintenance windows: {db.query(MaintenanceWindow).count()} total")

        db.commit()
        print("\nDemo data seeded successfully.")
        print(f"  Cameras:            {db.query(Camera).count()}")
        print(f"  Zones:              {db.query(Zone).count()}")
        print(f"  Persons:            {db.query(Person).count()}")
        print(f"  Alert routing:      {db.query(AlertRouting).count()}")
        print(f"  Alerts:             {db.query(Alert).count()}")
        print(f"  Maintenance:        {db.query(MaintenanceWindow).count()}")


if __name__ == "__main__":
    main()
