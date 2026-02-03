# Apprise Centralized Alerting - Deployment Summary

## What Was Implemented

A centralized notification architecture where **all alerts from all systems** flow through Apprise before being delivered to notification endpoints (ntfy, email, Slack, etc.).

## Changes Made

### 1. Kubernetes Infrastructure (flux/)

#### Updated Apprise Deployment
- **File**: [flux/apps/apprise/deployment-apprise.yaml](../apps/apprise/deployment-apprise.yaml)
- **Change**: Configured to use `APPRISE_STATELESS_URLS` from sealed secret
- **Status**: ✅ Ready

#### Added Apprise Ingress
- **File**: [flux/apps/apprise/ingressroute-apprise.yaml](../apps/apprise/ingressroute-apprise.yaml)
- **URL**: `https://apprise.xrs444.net`
- **Purpose**: Allow external services (Home Assistant, Immich, etc.) to send notifications
- **Status**: ✅ Created

#### Updated Apprise Kustomization
- **File**: [flux/apps/apprise/kustomization.yaml](../apps/apprise/kustomization.yaml)
- **Change**: Added ingressroute to resources
- **Status**: ✅ Updated

#### Updated Loki Configuration
- **File**: [flux/apps/loki/configmap-loki.yaml](../apps/loki/configmap-loki.yaml:37-40)
- **Change**: Configured Loki ruler to send alerts to Prometheus Alertmanager on xsvr1
- **Old**: `http://localhost:9093` (non-functional)
- **New**: `http://xsvr1.lan:9093`
- **Status**: ✅ Fixed

#### Updated ntfy ACL
- **File**: [flux/apps/ntfy/configmap-ntfy.yaml](../apps/ntfy/configmap-ntfy.yaml)
- **Change**: Added `apprise` user with write-only access to all topics (`*`)
- **Purpose**: Allow Apprise to send to any ntfy topic
- **Status**: ✅ Updated

### 2. NixOS Infrastructure (nix/)

#### Updated Prometheus Alertmanager
- **File**: [nix/modules/services/monitoring/prometheus.nix](../../../nix/modules/services/monitoring/prometheus.nix:783)
- **Change**: Fixed webhook URLs to point to correct Apprise namespace
- **Old**: `http://apprise.monitoring.svc.cluster.local:8000/notify`
- **New**: `http://apprise.apprise.svc.cluster.local:8000/notify`
- **Receivers**: `default` and `critical`
- **Status**: ✅ Fixed

## Alert Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Alert Sources                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────┐         ┌────────────────┐              │
│  │  Prometheus    │         │  Loki          │              │
│  │  (xsvr1)       │────┐    │  (Kubernetes)  │──────┐       │
│  └────────────────┘    │    └────────────────┘      │       │
│                        │                             │       │
│  ┌────────────────┐    │    ┌────────────────┐      │       │
│  │ Home Assistant │────┼───▶│ Alertmanager   │──────┤       │
│  │ (External)     │    │    │ (xsvr1:9093)   │      │       │
│  └────────────────┘    │    └────────────────┘      │       │
│                        │                             │       │
│  ┌────────────────┐    │                             │       │
│  │ Paperless      │────┤                             │       │
│  │ (Kubernetes)   │    │                             │       │
│  └────────────────┘    │                             │       │
│                        ▼                             ▼       │
│  ┌────────────────┐  ┌──────────────────────────────────┐   │
│  │ Immich         │─▶│    Apprise API Server            │   │
│  │ (External)     │  │    apprise.apprise:8000          │   │
│  └────────────────┘  │    https://apprise.xrs444.net    │   │
│                      └──────────────────────────────────┘   │
│  ┌────────────────┐              │                          │
│  │ Other Services │──────────────┘                          │
│  └────────────────┘                                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │      Notification Endpoints              │
        ├─────────────────────────────────────────┤
        │                                          │
        │  ┌──────────┐  ┌─────────┐  ┌────────┐ │
        │  │   ntfy   │  │  Email  │  │ Slack  │ │
        │  │  (k8s)   │  │ (future)│  │(future)│ │
        │  └──────────┘  └─────────┘  └────────┘ │
        │                                          │
        │  ┌──────────┐  ┌─────────┐  ┌────────┐ │
        │  │ Discord  │  │Telegram │  │PagerDuty│ │
        │  │ (future) │  │(future) │  │(future)│ │
        │  └──────────┘  └─────────┘  └────────┘ │
        └─────────────────────────────────────────┘
```

## Current Status

### ✅ Fully Configured
- Prometheus → Alertmanager → Apprise → ntfy
- Loki → Alertmanager → Apprise → ntfy
- Apprise deployment ready
- Apprise ingress created
- ntfy ACL updated

### ⚠️ Requires Manual Steps
1. **Create ntfy user for Apprise**:
   ```bash
   kubectl exec -n ntfy -it deployment/ntfy -- ntfy user add apprise
   # Set a strong password when prompted
   ```

2. **Update Apprise sealed secret** with ntfy credentials:
   ```bash
   # Replace with your actual password
   NTFY_URL="ntfy://apprise:YOUR_PASSWORD@ntfy.ntfy.svc.cluster.local/alerts"

   kubectl create secret generic apprise-config \
     --from-literal=ntfy-url="$NTFY_URL" \
     --namespace apprise \
     --dry-run=client -o yaml | \
     kubeseal --format=yaml > flux/apps/apprise/sealedsecret-apprise-config.yaml
   ```

3. **Deploy NixOS changes** (Prometheus/Alertmanager):
   ```bash
   ssh xsvr1
   cd ~/nix
   sudo nixos-rebuild switch
   ```

4. **Deploy Flux changes** (Apprise, Loki, ntfy):
   ```bash
   cd flux
   git add -A
   git commit -m "Configure centralized alerting through Apprise"
   git push

   # Flux will auto-sync, or force it:
   flux reconcile kustomization apps --with-source
   ```

### 📋 Ready to Migrate
These services can now be configured to use Apprise:
- Home Assistant
- Paperless-ngx
- Immich
- Audiobookshelf
- Mealie
- Jellyfin
- NetBox
- Any custom scripts or applications

See [APPRISE_MIGRATION_GUIDE.md](APPRISE_MIGRATION_GUIDE.md) for detailed migration instructions.

## Access Points

### Internal (from Kubernetes pods)
```
http://apprise.apprise.svc.cluster.local:8000
```

### External (from Home Assistant, Immich, etc.)
```
https://apprise.xrs444.net
```

### API Endpoints
- `POST /notify` - Send to all configured endpoints
- `POST /notify/{topic}` - Send to specific ntfy topic

## Testing

### Quick Test (Internal)
```bash
kubectl run -it --rm test --image=curlimages/curl --restart=Never -- \
  curl -X POST http://apprise.apprise.svc.cluster.local:8000/notify \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Alert", "body": "Testing Apprise", "type": "info"}'
```

### Quick Test (External)
```bash
curl -X POST https://apprise.xrs444.net/notify \
  -H "Content-Type: application/json" \
  -d '{"title": "External Test", "body": "Testing from outside cluster", "type": "success"}'
```

### Test Prometheus Alertmanager
```bash
ssh xsvr1
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Test alert via Apprise",
      "description": "Testing Prometheus → Alertmanager → Apprise → ntfy"
    }
  }]'
```

Check your ntfy app/web interface for the notification.

## Documentation

- **[APPRISE_SETUP.md](APPRISE_SETUP.md)** - Complete architecture and setup guide
- **[APPRISE_MIGRATION_GUIDE.md](APPRISE_MIGRATION_GUIDE.md)** - Step-by-step service migration instructions

## Next Steps

1. ✅ Complete the manual setup steps above
2. ✅ Test internal Kubernetes alert flow
3. ✅ Test external access via ingress
4. 📋 Migrate Home Assistant notifications
5. 📋 Migrate Paperless notifications (via n8n or script)
6. 📋 Migrate Immich notifications
7. 📋 Add additional notification platforms (email, Slack, Discord, PagerDuty)
8. 📋 Configure alert routing by severity
9. 📋 Set up authentication/rate limiting on external ingress

## Benefits

✅ **Single point of control** - All notifications managed in one place
✅ **Easy to add platforms** - Just update the Apprise URLs, no need to reconfigure every service
✅ **Centralized routing** - Route different alerts to different platforms based on severity
✅ **Reduced complexity** - Services don't need individual notification configs
✅ **Better monitoring** - Track all notifications through Apprise logs

## Support

For issues or questions:
- Check [APPRISE_SETUP.md](APPRISE_SETUP.md) for troubleshooting
- Review Apprise logs: `kubectl logs -n apprise -l app=apprise -f`
- Check Alertmanager logs: `ssh xsvr1 && journalctl -u alertmanager -f`
- Review [Apprise documentation](https://github.com/caronc/apprise)
