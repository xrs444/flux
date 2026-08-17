# firewalla-exporter

Prometheus exporter for the [Firewalla MSP API](https://docs.firewalla.net/) —
box/device/alarm telemetry, not host OS metrics (that's `node_exporter`,
deployed separately on `xfw` itself per the docstring in `exporter.py`).

Talks to the MSP cloud API (`https://{FIREWALLA_MSP_ID}/v2`), the same one
`mcp-firewalla` uses — this is **not** a local API on the Firewalla box, so
this exporter runs as an ordinary k8s Deployment. No flash-wear concerns.

## Environment variables

| Var | Required | Default | Purpose |
|---|---|---|---|
| `FIREWALLA_MSP_ID` | yes | — | MSP domain, e.g. `dn-j3almw.firewalla.net` |
| `FIREWALLA_MSP_TOKEN` | yes | — | Personal access token |
| `FIREWALLA_POLL_INTERVAL_SECONDS` | no | `60` | How often to poll the MSP API, independent of Prometheus's scrape_interval |
| `FIREWALLA_EXPORTER_PORT` | no | `9878` | `/metrics` listen port |
| `FIREWALLA_PER_DEVICE_METRICS` | no | `true` | Set `false` to drop per-device series (~113 devices × 3 series) and keep only box-level summaries |

## Metrics

- `firewalla_exporter_up`, `firewalla_exporter_last_poll_timestamp_seconds`
- `firewalla_box_online{gid,name,model}`
- `firewalla_box_device_count{gid,name}`, `firewalla_box_rule_count{gid,name}`
- `firewalla_box_alarm_count_total{gid,name}` (lifetime, as reported by `/boxes`)
- `firewalla_alarms_active{gid,name}` (live count via `/alarms?query=status:active`)
- `firewalla_device_online{gid,device_id,name}`
- `firewalla_device_bandwidth_bytes{gid,device_id,name,direction}` (cumulative, as reported by `/devices`)

## Local run

```bash
FIREWALLA_MSP_ID=... FIREWALLA_MSP_TOKEN=... uv run exporter.py
curl localhost:9878/metrics
```
