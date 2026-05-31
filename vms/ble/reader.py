"""MQTT BLE badge reader — subscribes to broker, publishes BleEvents to Redis stream.

No-op when VMS_BLE_MQTT_BROKER is empty (BLE disabled by default).
Install paho-mqtt to enable: pip install paho-mqtt
"""

from __future__ import annotations

import logging
import time
from typing import Any

from vms.ble.messages import BleEvent
from vms.config import get_settings

logger = logging.getLogger(__name__)

_BLE_STREAM = "ble_events"


class MqttBleReader:
    """Connects to MQTT broker, publishes BleEvent records to Redis stream."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client
        self._client: Any = None
        self._loop: Any = None

    def start(self) -> None:
        settings = get_settings()
        if not settings.ble_mqtt_broker:
            logger.info("BLE disabled — VMS_BLE_MQTT_BROKER not set")
            return
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("paho-mqtt not installed — BLE disabled.  pip install paho-mqtt")
            return

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(settings.ble_mqtt_broker, settings.ble_mqtt_port, keepalive=60)
        self._client.loop_start()
        logger.info(
            "BLE MQTT reader started: %s:%d", settings.ble_mqtt_broker, settings.ble_mqtt_port
        )

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        settings = get_settings()
        client.subscribe(settings.ble_mqtt_topic)
        logger.info("MQTT connected, subscribed to %s", settings.ble_mqtt_topic)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        import asyncio

        try:
            now_ms = int(time.time() * 1000)
            event = BleEvent.from_mqtt_payload(msg.payload.decode(), now_ms)
            settings = get_settings()
            loop = self._loop
            if loop is not None and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._publish(event, settings.ble_stream_maxlen), loop
                )
        except Exception:
            logger.exception("BLE message parse error: %r", msg.payload)

    def set_event_loop(self, loop: Any) -> None:
        """Register the asyncio event loop for thread-safe publishing."""
        self._loop = loop

    async def _publish(self, event: BleEvent, maxlen: int) -> None:
        from vms.redis_client import stream_add

        await stream_add(self._redis, _BLE_STREAM, event.to_redis_fields(), maxlen=maxlen)
