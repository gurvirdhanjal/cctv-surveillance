"""Detector registry: read anomaly_detectors rows, instantiate classes."""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector
from vms.db.models import AnomalyDetector as AnomalyDetectorRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistryLoadError:
    alert_type: str
    class_path: str
    reason: str


@dataclass(frozen=True)
class RegistryLoadResult:
    detectors: dict[str, AnomalyDetector] = field(default_factory=dict)
    errors: list[RegistryLoadError] = field(default_factory=list)


def _import_class(path: str) -> type:
    module_name, _, class_name = path.rpartition(".")
    if not module_name:
        raise ImportError(f"class_path missing module prefix: {path!r}")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def load_enabled_detectors(session: Session) -> RegistryLoadResult:
    """Read enabled anomaly_detectors rows, instantiate each, collect errors."""
    detectors: dict[str, AnomalyDetector] = {}
    errors: list[RegistryLoadError] = []

    rows = session.query(AnomalyDetectorRow).filter_by(is_enabled=True).all()
    for row in rows:
        try:
            config: dict[str, object] = {}
            if row.config_json is not None:
                try:
                    config = json.loads(row.config_json)
                except json.JSONDecodeError as exc:
                    errors.append(
                        RegistryLoadError(
                            alert_type=row.alert_type,
                            class_path=row.class_path,
                            reason=f"config_json parse error: {exc}",
                        )
                    )
                    continue
                if not isinstance(config, dict):
                    errors.append(
                        RegistryLoadError(
                            alert_type=row.alert_type,
                            class_path=row.class_path,
                            reason="config_json must be a JSON object",
                        )
                    )
                    continue

            cls = _import_class(row.class_path)
            if not issubclass(cls, AnomalyDetector):
                errors.append(
                    RegistryLoadError(
                        alert_type=row.alert_type,
                        class_path=row.class_path,
                        reason="class is not an AnomalyDetector subclass",
                    )
                )
                continue
            instance = cls(config)
            detectors[row.alert_type] = instance
            logger.info("loaded detector %s -> %s", row.alert_type, row.class_path)
        except Exception as exc:
            errors.append(
                RegistryLoadError(
                    alert_type=row.alert_type,
                    class_path=row.class_path,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )

    return RegistryLoadResult(detectors=detectors, errors=errors)
