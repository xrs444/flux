# Apprise Centralized Notification Setup

This document describes the centralized notification architecture using Apprise as a routing hub.

## Architecture Overview

All alerts from all systems now flow through Apprise before being sent to notification endpoints (ntfy, email, Slack, etc.).

```
┌─────────────────────┐
│ Prometheus (xsvr1)  │
│   Alertmanager      │──┐
└─────────────────────┘  │
                         │
┌─────────────────────┐  │     ┌──────────────────┐     ┌─────────────────┐
│ Loki (Kubernetes)   │──┼────▶│ Apprise API      │────▶│ ntfy            │
│   Log Alerts        │  │     │ (Kubernetes)     │     │ (Kubernetes)    │
└─────────────────────┘  │     └──────────────────┘     └─────────────────┘
                         │              │
┌─────────────────────┐  │              │               ┌─────────────────┐
│ Home Assistant      │──┘              └──────────────▶│ Email, Slack,   │
│ Paperless, Immich   │                                 │ Discord, etc.   │
│ (Future)            │                                 │ (Future)        │
└─────────────────────┘                                 └─────────────────┘
```

## Current Alert Flows

### 1. Prometheus → Alertmanager → Apprise → ntfy

**Source**: Prometheus on xsvr1
**Configuration**: [nix/modules/services/monitoring/prometheus.nix](nix/modules/services/monitoring/prometheus.nix:778-796)

Prometheus sends alerts to Alertmanager (localhost:9093), which then forwards them via webhook to:
```
http://apprise.apprise.svc.cluster.local:8000/notify
```

**Alert Types**: System metrics, Kubernetes, ZFS, SMART, backups, SSL certificates, BGP

### 2. Loki → Alertmanager → Apprise → ntfy

**Source**: Loki in Kubernetes
**Configuration**: [flux/apps/loki/configmap-loki.yaml](flux/apps/loki/configmap-loki.yaml:37-40)

Loki's ruler sends alerts to Prometheus Alertmanager on xsvr1:
```
http://xsvr1.lan:9093
```

Alertmanager then routes these to Apprise (same as above).

**Alert Types**: Log-based alerts (to be configured)

### 3. Direct to ntfy (To Be Migrated)

**Current State**: These services bypass Apprise and send directly to ntfy
- Home Assistant → ntfy://hass@ntfy.ntfy/homeassistant
- Paperless → ntfy://paperless@ntfy.ntfy/documents
- Immich → ntfy://immich@ntfy.ntfy/photos

**Future**: Migrate these to send to Apprise API instead

## Apprise Configuration

### Deployment
**Location**: [flux/apps/apprise/](flux/apps/apprise/)
**Namespace**: `apprise`
**Service**: `apprise.apprise.svc.cluster.local:8000`

### Endpoints

- `POST /notify` - Webhook endpoint for receiving alerts (accepts Prometheus Alertmanager format)
- Apprise automatically converts the webhook payload to notifications

### Notification URLs

Apprise uses `APPRISE_STATELESS_URLS` environment variable to define where notifications are sent.

**Secret**: `apprise-config/ntfy-url` (SealedSecret)

**Current Configuration**:
- ntfy endpoint with prometheus user credentials

**URL Format**:
```
ntfy://username:password@ntfy.ntfy.svc.cluster.local/topic
```

### Adding More Notification Endpoints

To add additional notification platforms (email, Slack, Discord, etc.), update the sealed secret with multiple URLs separated by spaces:

```bash
# Example with multiple endpoints
APPRISE_URLS="ntfy://user:pass@ntfy.ntfy.svc.cluster.local/alerts slack://TokenA/TokenB/TokenC discord://WebhookID/WebhookToken"

# Create the secret (replace with your actual values)
kubectl create secret generic apprise-config \
  --from-literal=ntfy-url="$APPRISE_URLS" \
  --namespace apprise \
  --dry-run=client -o yaml | \
  kubeseal --format=yaml > flux/apps/apprise/sealedsecret-apprise-config.yaml
```

### Supported Notification Services

Apprise supports 80+ notification services. Common ones include:

- **ntfy** (current): `ntfy://user:pass@host/topic`
- **Email**: `mailto://user:pass@gmail.com`
- **Slack**: `slack://TokenA/TokenB/TokenC`
- **Discord**: `discord://WebhookID/WebhookToken`
- **Telegram**: `tgram://BotToken/ChatID`
- **Microsoft Teams**: `msteams://TokenA/TokenB/TokenC`
- **PagerDuty**: `pagerduty://IntegrationKey@ApiKey`

Full list: https://github.com/caronc/apprise/wiki

## Testing the Setup

### 1. Test Apprise Directly

```bash
# From inside the cluster (any pod)
curl -X POST http://apprise.apprise.svc.cluster.local:8000/notify \
  -H "Content-Type: application/json" \
  -d '{
    "body": "Test notification from Apprise",
    "title": "Test Alert"
  }'
```

### 2. Test Prometheus Alertmanager

```bash
# SSH to xsvr1
ssh xsvr1

# Send a test alert to Alertmanager
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning",
      "instance": "test"
    },
    "annotations": {
      "summary": "This is a test alert",
      "description": "Testing Alertmanager → Apprise → ntfy flow"
    }
  }]'
```

You should receive a notification via ntfy.

### 3. Check Logs

```bash
# Apprise logs
kubectl logs -n apprise -l app=apprise -f

# Loki logs
kubectl logs -n loki -l app=loki -f
```

## Deployment Steps

### Apply Nix Configuration (Prometheus/Alertmanager)

```bash
# On xsvr1 (the monitoring server)
cd ~/nix
sudo nixos-rebuild switch
```

### Apply Kubernetes Configuration (Apprise, Loki)

```bash
# From your flux repo
cd flux
git add -A
git commit -m "Configure centralized alerting through Apprise"
git push

# Flux will automatically apply changes
# Or force reconciliation:
flux reconcile kustomization apps --with-source
```

### Verify Deployment

```bash
# Check Apprise is running
kubectl get pods -n apprise
kubectl get svc -n apprise

# Check Loki config was updated
kubectl get configmap -n loki loki-config -o yaml

# Verify Prometheus Alertmanager on xsvr1
ssh xsvr1
systemctl status alertmanager
curl http://localhost:9093/api/v1/status
```

## Next Steps

### 1. Migrate Existing Direct ntfy Users

Update the following services to send notifications via Apprise:

- **Home Assistant**: Change notification service URL to `http://apprise.apprise.svc.cluster.local:8000/notify`
- **Paperless**: Configure webhook to Apprise instead of direct ntfy
- **Immich**: Configure webhook to Apprise instead of direct ntfy

### 2. Add More Notification Platforms

- Email for critical alerts
- Slack for team notifications
- PagerDuty for on-call rotation
- SMS via Twilio for critical failures

### 3. Configure Loki Alert Rules

Add log-based alerting rules to Loki:
- Application error rates
- Failed login attempts
- Container crash patterns
- Security-related log patterns

### 4. Set Up Alert Routing

Configure Apprise with different tags/endpoints for different alert types:
- Critical alerts → PagerDuty + ntfy
- Warnings → ntfy only
- Info → Email digest

### 5. Alert Notification Preferences

Create different notification channels based on severity:
```
Critical: PagerDuty + SMS + ntfy
Warning: ntfy + Email
Info: Email only (daily digest)
```

## Troubleshooting

### Alerts not reaching ntfy

1. Check Apprise logs: `kubectl logs -n apprise -l app=apprise`
2. Verify secret is correct: `kubectl get secret -n apprise apprise-config -o yaml`
3. Test Apprise endpoint directly (see Testing section)
4. Verify ntfy is accessible from Apprise pod

### Prometheus alerts not firing

1. Check Alertmanager: `ssh xsvr1 && systemctl status alertmanager`
2. View Alertmanager UI: http://xsvr1:9093
3. Check webhook configuration: `journalctl -u alertmanager -f`

### Loki alerts not working

1. Check Loki has alert rules configured
2. Verify Loki can reach xsvr1:9093: `kubectl exec -n loki -it <loki-pod> -- wget -O- http://xsvr1.lan:9093/api/v1/status`
3. Check Loki logs: `kubectl logs -n loki -l app=loki`

## References

- [Apprise GitHub](https://github.com/caronc/apprise)
- [Apprise API Documentation](https://github.com/caronc/apprise-api)
- [Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Loki Alerting](https://grafana.com/docs/loki/latest/alert/)
