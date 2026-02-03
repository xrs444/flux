# Apprise Quick Reference Card

## URLs

- **Internal**: `http://apprise.apprise.svc.cluster.local:8000`
- **External**: `https://apprise.xrs444.net`

## Send Notification

### Basic (All endpoints)
```bash
curl -X POST https://apprise.xrs444.net/notify \
  -H "Content-Type: application/json" \
  -d '{"title": "Title", "body": "Message", "type": "info"}'
```

### Specific Topic
```bash
curl -X POST https://apprise.xrs444.net/notify/alerts \
  -H "Content-Type: application/json" \
  -d '{"title": "Alert", "body": "Critical issue", "type": "failure"}'
```

### Types
- `info` - Informational (default)
- `success` - Success/completion
- `warning` - Warning
- `failure` - Error/critical

## Common Commands

### Check Status
```bash
kubectl get pods -n apprise
kubectl logs -n apprise -l app=apprise -f
```

### Test Alertmanager
```bash
ssh xsvr1
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels": {"alertname": "Test"}, "annotations": {"summary": "Test"}}]'
```

### Check ntfy Users
```bash
kubectl exec -n ntfy deployment/ntfy -- ntfy user list
```

### Update Apprise Secret
```bash
NTFY_URL="ntfy://apprise:PASSWORD@ntfy.ntfy.svc.cluster.local/alerts"
kubectl create secret generic apprise-config \
  --from-literal=ntfy-url="$NTFY_URL" \
  --namespace apprise --dry-run=client -o yaml | \
  kubeseal --format=yaml > flux/apps/apprise/sealedsecret-apprise-config.yaml
```

## Service Examples

### Home Assistant
```yaml
notify:
  - platform: rest
    name: apprise
    resource: https://apprise.xrs444.net/notify/homeassistant
    method: POST
    headers:
      Content-Type: application/json
    data:
      title: "{{ title }}"
      body: "{{ message }}"
```

### Python
```python
import requests
requests.post(
    'http://apprise.apprise.svc.cluster.local:8000/notify',
    json={'title': 'Title', 'body': 'Message', 'type': 'info'}
)
```

### Bash
```bash
send_notification() {
    curl -X POST http://apprise.apprise.svc.cluster.local:8000/notify \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$1\", \"body\": \"$2\", \"type\": \"${3:-info}\"}"
}
```

## Alert Flow

```
Service → Apprise → ntfy/Email/Slack/etc.
```

## Files Changed

- `nix/modules/services/monitoring/prometheus.nix` - Alertmanager webhooks
- `flux/apps/loki/configmap-loki.yaml` - Loki alertmanager URL
- `flux/apps/apprise/ingressroute-apprise.yaml` - External access
- `flux/apps/ntfy/configmap-ntfy.yaml` - Added apprise user ACL

## Documentation

- [APPRISE_DEPLOYMENT_SUMMARY.md](APPRISE_DEPLOYMENT_SUMMARY.md) - What was set up
- [APPRISE_SETUP.md](APPRISE_SETUP.md) - Complete architecture guide
- [APPRISE_MIGRATION_GUIDE.md](APPRISE_MIGRATION_GUIDE.md) - Service migration steps
