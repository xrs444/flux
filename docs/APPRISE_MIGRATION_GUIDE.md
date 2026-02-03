# Apprise Service Migration Guide

This guide provides step-by-step instructions for migrating all services to use Apprise as the centralized notification hub.

## Overview

Apprise is now accessible at:
- **Internal (from Kubernetes)**: `http://apprise.apprise.svc.cluster.local:8000`
- **External (from Home Assistant, etc.)**: `https://apprise.xrs444.net`

## Apprise API Endpoints

### Primary Endpoint: `/notify`
Accepts JSON payloads and sends to all configured notification endpoints.

```bash
curl -X POST https://apprise.xrs444.net/notify \
  -H "Content-Type: application/json" \
  -d '{
    "body": "Your notification message",
    "title": "Notification Title",
    "type": "info"
  }'
```

**Type options**: `info`, `success`, `warning`, `failure`

### Topic-Specific Notifications
Send to specific ntfy topics by using the URL path:

```bash
# Send to the 'alerts' topic
curl -X POST https://apprise.xrs444.net/notify/alerts \
  -H "Content-Type: application/json" \
  -d '{"body": "Alert message", "title": "Alert"}'

# Send to the 'homeassistant' topic
curl -X POST https://apprise.xrs444.net/notify/homeassistant \
  -H "Content-Type: application/json" \
  -d '{"body": "HA notification", "title": "Home Assistant"}'
```

## Migration Instructions by Service

### 1. Home Assistant

Home Assistant can send notifications to Apprise using the REST notify platform.

**Configuration** (`configuration.yaml`):

```yaml
notify:
  # Replace existing ntfy notification platform with Apprise
  - platform: rest
    name: apprise
    resource: https://apprise.xrs444.net/notify/homeassistant
    method: POST
    headers:
      Content-Type: application/json
    data:
      title: "{{ title }}"
      body: "{{ message }}"
      type: "info"

  # For critical alerts
  - platform: rest
    name: apprise_critical
    resource: https://apprise.xrs444.net/notify/homeassistant
    method: POST
    headers:
      Content-Type: application/json
    data:
      title: "{{ title }}"
      body: "{{ message }}"
      type: "failure"
```

**Usage in automations**:

```yaml
automation:
  - alias: "Send notification via Apprise"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: notify.apprise
        data:
          title: "Front Door"
          message: "Front door opened at {{ now().strftime('%I:%M %p') }}"
```

**Migration Steps**:
1. Add the REST notify platform configuration above
2. Update existing automations to use `notify.apprise` instead of `notify.ntfy`
3. Test with a simple automation
4. Remove old ntfy configuration once verified

### 2. Paperless-ngx

Paperless-ngx doesn't have built-in notification webhooks, but you can use n8n or custom scripts to monitor for new documents and send notifications.

**Option A: Using n8n Workflow**

Create an n8n workflow that:
1. Polls Paperless API for new documents (or uses webhook)
2. Sends notification to Apprise

```javascript
// n8n HTTP Request node to Apprise
{
  "method": "POST",
  "url": "http://apprise.apprise.svc.cluster.local:8000/notify/documents",
  "body": {
    "title": "New Document",
    "body": "Document '{{ $json.title }}' was added to Paperless",
    "type": "success"
  }
}
```

**Option B: Custom Python Script**

```python
#!/usr/bin/env python3
import requests
from paperless_api import PaperlessAPI

# Monitor Paperless for new documents
def notify_new_document(doc_title):
    requests.post(
        'http://apprise.apprise.svc.cluster.local:8000/notify/documents',
        json={
            'title': 'New Document',
            'body': f'Document "{doc_title}" added to Paperless',
            'type': 'success'
        }
    )
```

### 3. Immich

If Immich is external, configure it to send webhooks to Apprise.

**Immich Webhook Configuration** (if available in your version):

1. Go to Immich Admin Settings → Webhooks
2. Add new webhook: `https://apprise.xrs444.net/notify/photos`
3. Select events: Upload complete, Backup complete, etc.

**Immich doesn't have native webhooks?** Use n8n to poll Immich API:

```javascript
// n8n workflow to monitor Immich
{
  "method": "POST",
  "url": "http://apprise.apprise.svc.cluster.local:8000/notify/photos",
  "body": {
    "title": "Immich Backup",
    "body": "{{ $json.assetCount }} new photos backed up",
    "type": "success"
  }
}
```

### 4. Audiobookshelf

Configure notification webhooks in Audiobookshelf admin panel.

**Steps**:
1. Go to Settings → Notifications
2. Add webhook URL: `https://apprise.xrs444.net/notify/media`
3. Or use internal: `http://apprise.apprise.svc.cluster.local:8000/notify/media`
4. Test the webhook

### 5. Mealie

Mealie can send notifications for meal plans and shopping lists.

**Configuration**:
- Go to Mealie Settings → Webhooks
- Add webhook: `http://apprise.apprise.svc.cluster.local:8000/notify/mealie`
- Select events to notify on

### 6. Jellyfin

Configure Jellyfin webhook plugin to send to Apprise.

**Steps**:
1. Install "Webhook" plugin in Jellyfin
2. Configure webhook URL: `http://apprise.apprise.svc.cluster.local:8000/notify/media`
3. Or external: `https://apprise.xrs444.net/notify/media`
4. Select events: New media added, Playback started, etc.

### 7. NetBox

Configure NetBox webhooks for infrastructure changes.

**Steps**:
1. Go to NetBox Admin → Webhooks
2. Create new webhook
3. URL: `http://apprise.apprise.svc.cluster.local:8000/notify/infrastructure`
4. Content type: `application/json`
5. Select events: Device changes, IP allocation, etc.

### 8. Custom Applications / Scripts

For any custom scripts or applications:

**Bash Script Example**:
```bash
#!/bin/bash
send_notification() {
    local title="$1"
    local message="$2"
    local type="${3:-info}"

    curl -X POST http://apprise.apprise.svc.cluster.local:8000/notify \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$title\", \"body\": \"$message\", \"type\": \"$type\"}"
}

# Usage
send_notification "Backup Complete" "Daily backup finished successfully" "success"
send_notification "Backup Failed" "Daily backup encountered errors" "failure"
```

**Python Example**:
```python
import requests

def send_apprise_notification(title, message, notification_type="info", topic=None):
    """Send notification via Apprise"""
    url = "http://apprise.apprise.svc.cluster.local:8000/notify"
    if topic:
        url = f"{url}/{topic}"

    payload = {
        "title": title,
        "body": message,
        "type": notification_type
    }

    response = requests.post(url, json=payload)
    return response.status_code == 200

# Usage
send_apprise_notification("Script Complete", "Processing finished", "success", "automation")
```

## Configuring ntfy Topics

The sealed secret needs to be updated with an apprise user credential to access ntfy.

### Create ntfy User for Apprise

```bash
# On a pod with access to ntfy or via the ntfy CLI
kubectl exec -n ntfy -it deployment/ntfy -- ntfy user add apprise

# Set a strong password when prompted
```

### Update Apprise Secret

The Apprise secret should contain ntfy URLs for different topics:

```bash
# Generate the Apprise URL configuration
# Format: ntfy://username:password@host/topic

# Single topic (current setup)
NTFY_URL="ntfy://apprise:YOUR_PASSWORD@ntfy.ntfy.svc.cluster.local/alerts"

# Multiple topics (space-separated)
NTFY_URLS="ntfy://apprise:YOUR_PASSWORD@ntfy.ntfy.svc.cluster.local/alerts ntfy://apprise:YOUR_PASSWORD@ntfy.ntfy.svc.cluster.local/homeassistant ntfy://apprise:YOUR_PASSWORD@ntfy.ntfy.svc.cluster.local/documents"

# Create sealed secret
kubectl create secret generic apprise-config \
  --from-literal=ntfy-url="$NTFY_URLS" \
  --namespace apprise \
  --dry-run=client -o yaml | \
  kubeseal --format=yaml > flux/apps/apprise/sealedsecret-apprise-config.yaml
```

## Adding More Notification Platforms

Apprise supports 80+ notification services. To add more:

### Email (Gmail)

```bash
URLS="$NTFY_URLS mailto://user:app-password@gmail.com?to=alerts@example.com"
```

### Slack

```bash
URLS="$NTFY_URLS slack://TokenA/TokenB/TokenC/#channel"
```

### Discord

```bash
URLS="$NTFY_URLS discord://WebhookID/WebhookToken"
```

### Telegram

```bash
URLS="$NTFY_URLS tgram://BotToken/ChatID"
```

### PagerDuty

```bash
URLS="$NTFY_URLS pagerduty://IntegrationKey@ApiKey"
```

### Microsoft Teams

```bash
URLS="$NTFY_URLS msteams://TokenA/TokenB/TokenC"
```

Update the sealed secret with all desired URLs space-separated.

## Routing by Severity

You can configure different notification endpoints based on message type:

### Using Apprise Tags (Advanced)

Create a configuration file approach (requires persistent config):

```yaml
# apprise-config.yml
urls:
  # Critical alerts to PagerDuty + ntfy
  - pagerduty://IntegrationKey@ApiKey:
      - tag: critical
  - ntfy://apprise:pass@ntfy.ntfy.svc.cluster.local/alerts:
      - tag: critical, warning, info

  # Email for warnings and above
  - mailto://user:pass@gmail.com:
      - tag: critical, warning
```

### Using Multiple Apprise Instances

Deploy separate Apprise instances for different severity levels:
- `apprise-critical.apprise:8000` → PagerDuty + SMS + ntfy
- `apprise-warning.apprise:8000` → ntfy + Email
- `apprise-info.apprise:8000` → ntfy only

## Testing

### Test Apprise Endpoint

```bash
# From inside cluster
kubectl run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://apprise.apprise.svc.cluster.local:8000/notify \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "body": "Testing Apprise", "type": "info"}'

# From external (after ingress is set up)
curl -X POST https://apprise.xrs444.net/notify \
  -H "Content-Type: application/json" \
  -d '{"title": "External Test", "body": "Testing from outside", "type": "success"}'
```

### Test Specific Topics

```bash
# Test alerts topic
curl -X POST https://apprise.xrs444.net/notify/alerts \
  -H "Content-Type: application/json" \
  -d '{"title": "Alert Test", "body": "Testing alerts topic"}'

# Test homeassistant topic
curl -X POST https://apprise.xrs444.net/notify/homeassistant \
  -H "Content-Type: application/json" \
  -d '{"title": "HA Test", "body": "Testing Home Assistant topic"}'
```

## Troubleshooting

### Notifications Not Arriving

1. **Check Apprise logs**:
   ```bash
   kubectl logs -n apprise -l app=apprise -f
   ```

2. **Verify ntfy user exists**:
   ```bash
   kubectl exec -n ntfy deployment/ntfy -- ntfy user list
   ```

3. **Test ntfy directly**:
   ```bash
   curl -u apprise:password \
     -d "Direct ntfy test" \
     https://ntfy.xrs444.net/alerts
   ```

4. **Check secret is correct**:
   ```bash
   kubectl get secret -n apprise apprise-config -o jsonpath='{.data.ntfy-url}' | base64 -d
   ```

### External Services Can't Reach Apprise

1. **Verify ingress exists**:
   ```bash
   kubectl get ingressroute -n apprise
   ```

2. **Check DNS resolution**:
   ```bash
   dig apprise.xrs444.net
   ```

3. **Test from external network**:
   ```bash
   curl -v https://apprise.xrs444.net/notify
   ```

### Apprise Returns 500 Error

- Check the ntfy URL format in the secret
- Verify ntfy credentials are correct
- Ensure ntfy service is running: `kubectl get pods -n ntfy`

## Security Considerations

### Securing External Access

If exposing Apprise externally, consider:

1. **Add authentication** - Use Traefik BasicAuth middleware
2. **Rate limiting** - Prevent abuse via Traefik RateLimit middleware
3. **IP whitelisting** - Restrict to known external service IPs
4. **API keys** - Implement API key validation

### Example: Adding BasicAuth

```yaml
# middleware-apprise-auth.yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: apprise-auth
  namespace: apprise
spec:
  basicAuth:
    secret: apprise-auth-secret
---
# Update ingressroute to use middleware
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: apprise
  namespace: apprise
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`apprise.xrs444.net`)
      kind: Rule
      middlewares:
        - name: apprise-auth
      services:
        - name: apprise
          port: 8000
  tls:
    certResolver: letsencrypt
```

## Migration Checklist

- [x] Prometheus Alertmanager → Apprise
- [x] Loki → Alertmanager → Apprise
- [x] ntfy ACL updated with apprise user
- [x] Apprise ingress created
- [ ] Home Assistant notifications migrated
- [ ] Paperless notifications configured (via n8n or script)
- [ ] Immich notifications configured
- [ ] Create ntfy user password for apprise
- [ ] Update Apprise sealed secret with credentials
- [ ] Test each service's notifications
- [ ] Document any service-specific configurations
- [ ] Remove old direct ntfy integrations

## Next Steps

1. Create the `apprise` user in ntfy with appropriate password
2. Update the sealed secret with the apprise user credentials
3. Test internal Kubernetes services can reach Apprise
4. Test external services can reach https://apprise.xrs444.net
5. Migrate each service one at a time, testing thoroughly
6. Monitor Apprise logs during migration
7. Update this checklist as services are migrated

## References

- [Apprise GitHub](https://github.com/caronc/apprise)
- [Apprise URL Documentation](https://github.com/caronc/apprise/wiki)
- [Apprise API Usage](https://github.com/caronc/apprise-api/wiki)
- [Home Assistant REST Notify](https://www.home-assistant.io/integrations/rest/)
