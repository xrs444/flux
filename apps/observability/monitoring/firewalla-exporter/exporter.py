#!/usr/bin/env python3
"""Prometheus exporter for the Firewalla MSP API.

Polls https://{FIREWALLA_MSP_ID}/v2 (boxes/alarms/devices) and exposes
box- and device-level metrics on /metrics. This is the MSP cloud API (the
same one mcp-firewalla uses) -- not a local API on the Firewalla box -- so
this runs as an ordinary k8s Deployment, no flash-wear concerns.

API results are cached for FIREWALLA_POLL_INTERVAL_SECONDS regardless of
Prometheus's own scrape_interval, so a short scrape_interval doesn't
hammer the MSP API.
"""
import os
import sys
import threading
import time

import requests
from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

MSP_ID = os.environ["FIREWALLA_MSP_ID"]
MSP_TOKEN = os.environ["FIREWALLA_MSP_TOKEN"]
POLL_INTERVAL = int(os.environ.get("FIREWALLA_POLL_INTERVAL_SECONDS", "60"))
LISTEN_PORT = int(os.environ.get("FIREWALLA_METRICS_PORT", "9878"))
PER_DEVICE_METRICS = os.environ.get("FIREWALLA_PER_DEVICE_METRICS", "true").lower() == "true"

BASE_URL = f"https://{MSP_ID}/v2"
session = requests.Session()
session.headers.update({
    "Authorization": f"Token {MSP_TOKEN}",
    "Content-Type": "application/json",
})

_lock = threading.Lock()
_cache = {"ts": 0.0, "boxes": [], "devices": [], "active_alarms": {}, "ok": False}


def _get(path, params=None):
    r = session.get(f"{BASE_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _fetch_active_alarm_counts(boxes):
    """Count active alarms per box. /alarms is paginated and box-scoped."""
    counts = {}
    for box in boxes:
        gid = box["gid"]
        total = 0
        cursor = None
        for _ in range(20):  # hard cap: never loop forever on a pagination bug
            params = {"query": f"status:active box:{gid}", "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = _get("/alarms", params=params)
            total += len(data.get("results", []))
            cursor = data.get("next_cursor")
            if not cursor:
                break
        counts[gid] = total
    return counts


def _refresh():
    boxes = _get("/boxes")
    devices = _get("/devices")
    active_alarms = _fetch_active_alarm_counts(boxes)
    with _lock:
        _cache.update(ts=time.time(), boxes=boxes, devices=devices,
                       active_alarms=active_alarms, ok=True)


def _refresh_loop():
    while True:
        try:
            _refresh()
        except Exception as e:  # noqa: BLE001 -- exporter must never crash the loop
            print(f"[firewalla-exporter] refresh failed: {e}", file=sys.stderr)
            with _lock:
                _cache["ok"] = False
        time.sleep(POLL_INTERVAL)


class FirewallaCollector:
    def collect(self):
        with _lock:
            boxes = list(_cache["boxes"])
            devices = list(_cache["devices"])
            active_alarms = dict(_cache["active_alarms"])
            ok = _cache["ok"]
            ts = _cache["ts"]

        up = GaugeMetricFamily("firewalla_exporter_up", "1 if the last MSP API poll succeeded")
        up.add_metric([], 1 if ok else 0)
        yield up

        last_poll = GaugeMetricFamily("firewalla_exporter_last_poll_timestamp_seconds",
                                       "Unix timestamp of the last successful poll")
        last_poll.add_metric([], ts)
        yield last_poll

        box_online = GaugeMetricFamily("firewalla_box_online", "1 if the box is online",
                                        labels=["gid", "name", "model"])
        box_devices = GaugeMetricFamily("firewalla_box_device_count", "Devices known to this box",
                                         labels=["gid", "name"])
        box_rules = GaugeMetricFamily("firewalla_box_rule_count", "Rules configured on this box",
                                       labels=["gid", "name"])
        box_alarms_total = GaugeMetricFamily("firewalla_box_alarm_count_total",
                                              "Lifetime alarm count reported by the box",
                                              labels=["gid", "name"])
        box_alarms_active = GaugeMetricFamily("firewalla_alarms_active",
                                               "Currently active (unresolved) alarms",
                                               labels=["gid", "name"])
        for box in boxes:
            gid = box["gid"]
            name = box.get("name", gid)
            box_online.add_metric([gid, name, box.get("model", "")], 1 if box.get("online") else 0)
            box_devices.add_metric([gid, name], box.get("deviceCount", 0))
            box_rules.add_metric([gid, name], box.get("ruleCount", 0))
            box_alarms_total.add_metric([gid, name], box.get("alarmCount", 0))
            box_alarms_active.add_metric([gid, name], active_alarms.get(gid, 0))
        yield box_online
        yield box_devices
        yield box_rules
        yield box_alarms_total
        yield box_alarms_active

        if PER_DEVICE_METRICS:
            dev_online = GaugeMetricFamily("firewalla_device_online", "1 if the client device is online",
                                            labels=["gid", "device_id", "name"])
            dev_bandwidth = CounterMetricFamily(
                "firewalla_device_bandwidth_bytes",
                "Cumulative bandwidth per device, as reported by the MSP API",
                labels=["gid", "device_id", "name", "direction"],
            )
            for d in devices:
                gid, dev_id, name = d.get("gid", ""), d.get("id", ""), d.get("name", "")
                dev_online.add_metric([gid, dev_id, name], 1 if d.get("online") else 0)
                dev_bandwidth.add_metric([gid, dev_id, name, "download"], d.get("totalDownload", 0))
                dev_bandwidth.add_metric([gid, dev_id, name, "upload"], d.get("totalUpload", 0))
            yield dev_online
            yield dev_bandwidth


def main():
    REGISTRY.register(FirewallaCollector())
    threading.Thread(target=_refresh_loop, daemon=True).start()
    start_http_server(LISTEN_PORT)
    print(f"[firewalla-exporter] serving /metrics on :{LISTEN_PORT}, "
          f"polling {BASE_URL} every {POLL_INTERVAL}s")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
