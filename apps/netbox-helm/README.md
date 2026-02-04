# NetBox + Diode - Helm Chart Deployment

Official Helm chart-based deployment of NetBox with Diode for automated network discovery.

## Why Helm Charts?

This deployment uses official Helm charts from:
- **NetBox**: [netbox-community/netbox-chart](https://github.com/netbox-community/netbox-chart) (v5.0+)
- **Diode**: [netboxlabs/diode](https://github.com/netboxlabs/diode) (v1.13+)

### Benefits
- ✅ **Official support** from NetBox Labs and community
- ✅ **Easier upgrades** - Just bump chart versions
- ✅ **Better defaults** - Production-tested configurations
- ✅ **Managed dependencies** - PostgreSQL/Redis handled automatically
- ✅ **Less maintenance** - No reinventing the wheel
- ✅ **Values-based config** - Clean override pattern

## Architecture

```
┌─────────────────────────────────────────┐
│     Diode Discovery Agent (CronJob)    │
│    (Kubernetes, SNMP, Network Scan)     │
└─────────────┬───────────────────────────┘
              │ gRPC (port 8081)
              ▼
┌─────────────────────────────────────────┐
│       Diode Server (Helm Chart)         │
│    netboxlabs/diode:latest              │
└─────────────┬───────────────────────────┘
              │ REST API
              ▼
┌─────────────────────────────────────────┐
│       NetBox (Helm Chart)               │
│  netbox-community/netbox:latest         │
│  ├── PostgreSQL 15 (sidecar)            │
│  └── Redis 7 (sidecar)                  │
└─────────────────────────────────────────┘
```

## Components

### 1. NetBox (HelmRelease)
- **Chart**: `netbox-community/netbox` v5.0+
- **Includes**: PostgreSQL, Redis, NetBox application
- **Features**: OIDC auth, persistence, ingress
- **File**: [helmrelease-netbox.yaml](helmrelease-netbox.yaml)

### 2. Diode Server (HelmRelease)
- **Chart**: `netboxlabs/diode` v1.13+
- **Purpose**: Ingest network data via gRPC → push to NetBox
- **Features**: Health checks, service exposure
- **File**: [helmrelease-diode.yaml](helmrelease-diode.yaml)

### 3. Discovery Agent (CronJob)
- **Custom**: Python-based discovery script
- **Methods**: Kubernetes, SNMP, nmap, LLDP/CDP
- **Schedule**: Hourly by default
- **Directory**: [diode-agent/](diode-agent/)

## Prerequisites

- Kubernetes cluster with Flux CD
- `kubeseal` for creating sealed secrets
- Container registry for discovery agent image
- DNS/Ingress configured (Traefik)

## Quick Start

### Step 1: Add DIODE_API_TOKEN to Secrets

After NetBox is deployed, you need to:

1. Log into NetBox UI
2. Create an API token with write permissions
3. Add `DIODE_API_TOKEN` to the sealed secret:

```bash
# Get existing secrets (you'll need to unseal them temporarily)
# Then add DIODE_API_TOKEN and reseal
# See: ../netbox/DIODE_SETUP_INSTRUCTIONS.md for details
```

### Step 2: Deploy NetBox + Diode

```bash
# Deploy the Helm releases
kubectl apply -k flux/apps/netbox-helm/

# Or use Flux
flux reconcile kustomization flux-system --with-source
```

### Step 3: Build Discovery Agent

```bash
cd flux/apps/netbox-helm/diode-agent/

# Build container
export CONTAINER_REGISTRY="your-registry.example.com"
./build.sh

# Push to registry
docker push ${CONTAINER_REGISTRY}/diode-discovery-agent:latest

# Update image in cronjob-discovery.yaml
```

### Step 4: Configure & Deploy Agent

1. Edit [diode-agent/configmap-diode-agent.yaml](diode-agent/configmap-diode-agent.yaml):
   - Set `NETWORK_SCAN_RANGES` to your networks
   - Set `DEFAULT_SITE` to match NetBox site

2. Create sealed credentials:
```bash
kubectl create secret generic diode-agent-secret \
  --namespace=diode-agent \
  --from-literal=SNMP_COMMUNITY="public" \
  --dry-run=client -o yaml | \
kubeseal --format=yaml --cert=<your-cert> \
  > diode-agent/sealedsecret-diode-agent.yaml
```

3. Deploy agent:
```bash
kubectl apply -k flux/apps/netbox-helm/diode-agent/
```

### Step 5: Verify

```bash
# Check Helm releases
flux get helmreleases -n netbox

# Check NetBox pods
kubectl get pods -n netbox

# Check Diode logs
kubectl logs -n netbox -l app.kubernetes.io/name=diode -c diode-server

# Trigger manual discovery
kubectl create job --from=cronjob/diode-discovery-agent \
  -n diode-agent manual-discovery-$(date +%s)

# View discovery logs
kubectl logs -n diode-agent -l app=diode-discovery-agent -f
```

## Configuration

### NetBox Values

Key values in [helmrelease-netbox.yaml](helmrelease-netbox.yaml):

```yaml
values:
  # Replicas
  replicaCount: 1

  # Resources
  resources:
    requests:
      memory: "512Mi"
      cpu: "250m"

  # PostgreSQL
  postgresql:
    enabled: true
    auth:
      existingSecret: netbox-secret

  # OIDC Authentication
  remoteAuth:
    enabled: true
    backend: social_core.backends.open_id_connect.OpenIdConnectAuth

  # Ingress
  ingress:
    enabled: true
    hosts:
      - host: netbox.xrs444.net
```

### Diode Values

Key values in [helmrelease-diode.yaml](helmrelease-diode.yaml):

```yaml
values:
  diode-server:
    enabled: true

    config:
      netbox:
        apiUrl: "http://netbox:8080"
        apiTokenSecret:
          name: netbox-secret
          key: DIODE_API_TOKEN

    service:
      type: ClusterIP
      port: 8081
```

### Discovery Agent

Configuration in [diode-agent/configmap-diode-agent.yaml](diode-agent/configmap-diode-agent.yaml):

```yaml
data:
  DIODE_SERVER_URL: "diode-diode-server.netbox.svc.cluster.local:8081"
  DISCOVERY_ENABLED_METHODS: "snmp,nmap,kubernetes,lldp"
  NETWORK_SCAN_RANGES: "192.168.1.0/24,10.0.0.0/24"
  DEFAULT_SITE: "homelab"
```

## Upgrading

### NetBox Chart Upgrade

```bash
# Edit helmrelease-netbox.yaml, bump version
version: '>=5.1.0 <6.0.0'

# Commit and push
git add flux/apps/netbox-helm/helmrelease-netbox.yaml
git commit -m "Upgrade NetBox chart to 5.1"
git push

# Flux will automatically upgrade
```

### Diode Chart Upgrade

```bash
# Edit helmrelease-diode.yaml, bump version
version: '>=1.14.0'

# Commit and push - Flux handles the rest
```

## Migration from Manual Manifests

If you're migrating from the old `flux/apps/netbox/` directory:

### Migration Steps

1. **Backup data** - Export NetBox data first!
2. **Keep secrets** - Sealed secrets remain the same
3. **Deploy new stack** - Apply netbox-helm kustomization
4. **Verify** - Check pods and ingress
5. **Migrate data** (if needed) - Import NetBox backup
6. **Remove old** - Delete old netbox deployment

### What Changed

- ❌ Manual deployment YAML → ✅ HelmRelease
- ❌ Custom kustomize patches → ✅ Helm values
- ❌ Sidecar containers → ✅ Helm-managed PostgreSQL/Redis
- ❌ Manual Diode deployment → ✅ Diode Helm chart
- ✅ Secrets - Same sealed secrets work!
- ✅ Discovery agent - Same code, updated service name

### Side-by-Side Comparison

| Component | Old (Manual) | New (Helm) |
|-----------|--------------|------------|
| NetBox | Custom deployment YAML | Official Helm chart |
| PostgreSQL | Sidecar container | Helm-managed StatefulSet |
| Redis | Sidecar container | Helm-managed StatefulSet |
| Diode | Custom deployment | Official Helm chart |
| Discovery | Custom CronJob | Same (updated service name) |
| Secrets | Sealed secrets | Same sealed secrets |
| Upgrades | Manual YAML edits | Chart version bump |

## File Structure

```
flux/apps/netbox-helm/
├── namespace-netbox.yaml              # Namespace definition
├── helmrepository-netbox.yaml         # NetBox chart repo
├── helmrepository-diode.yaml          # Diode chart repo (OCI)
├── helmrelease-netbox.yaml            # NetBox HelmRelease + values
├── helmrelease-diode.yaml             # Diode HelmRelease + values
├── sealedsecret-netbox.yaml           # DB, Redis, API tokens
├── oauth2-sealedsecret-netbox.yaml    # Kanidm OIDC credentials
├── kustomization.yaml                 # Kustomize manifest
├── README.md                          # This file
│
└── diode-agent/                       # Discovery agent (same as before)
    ├── namespace-diode-agent.yaml
    ├── serviceaccount-diode-agent.yaml
    ├── configmap-diode-agent.yaml     # ✏️ Updated service URL
    ├── sealedsecret-diode-agent.yaml
    ├── cronjob-discovery.yaml
    ├── discovery-script.py
    ├── Dockerfile
    ├── build.sh
    ├── kustomization.yaml
    ├── README.md
    ├── QUICKSTART.md
    └── .gitignore
```

## Troubleshooting

### Helm Release Failed

```bash
# Check Helm release status
flux get helmrelease netbox -n netbox

# View detailed events
kubectl describe helmrelease netbox -n netbox

# Check logs
kubectl logs -n netbox -l app.kubernetes.io/name=netbox
```

### PostgreSQL Issues

```bash
# Check PostgreSQL pod
kubectl get pods -n netbox -l app.kubernetes.io/name=postgresql

# View logs
kubectl logs -n netbox -l app.kubernetes.io/name=postgresql
```

### Diode Can't Connect to NetBox

```bash
# Verify NetBox service
kubectl get svc -n netbox

# Check Diode logs
kubectl logs -n netbox -l app.kubernetes.io/name=diode -c diode-server

# Verify API token exists
kubectl get secret netbox-secret -n netbox -o yaml | grep DIODE_API_TOKEN
```

### Discovery Agent Can't Reach Diode

```bash
# Verify Diode service name
kubectl get svc -n netbox | grep diode

# Test connectivity from agent
kubectl run -it --rm debug --image=busybox --restart=Never -- \
  nc -zv diode-diode-server.netbox.svc.cluster.local 8081
```

## Advanced Configuration

### Custom NetBox Plugins

Add plugins via Helm values:

```yaml
# helmrelease-netbox.yaml
values:
  plugins:
    - name: netbox-plugin-name
      config:
        PLUGIN_SETTING: value
```

### External PostgreSQL/Redis

Disable built-in databases:

```yaml
# helmrelease-netbox.yaml
values:
  postgresql:
    enabled: false
  externalDatabase:
    host: postgres.example.com
    port: 5432
```

### Horizontal Scaling

Scale NetBox replicas:

```yaml
# helmrelease-netbox.yaml
values:
  replicaCount: 3

  # Enable pod disruption budget
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
```

## Resources

### Official Documentation
- [NetBox Helm Chart](https://github.com/netbox-community/netbox-chart)
- [NetBox Chart Repository](https://charts.netbox.oss.netboxlabs.com/)
- [Diode Documentation](https://netboxlabs.com/docs/diode/)
- [Diode Releases](https://github.com/netboxlabs/diode/releases)

### Community
- [NetBox Labs Blog: Diode Helm Chart](https://netboxlabs.com/blog/diode-helm-chart/)
- [NetBox Slack](https://netdev.chat/) - #netbox-chart channel

## Security Considerations

- **Secrets**: Always use sealed secrets
- **RBAC**: Minimal permissions for discovery agent
- **Network Policies**: Consider isolating NetBox namespace
- **TLS**: Enable for production (configure ingress)
- **API Tokens**: Rotate regularly
- **Updates**: Keep charts updated for security patches

## Maintenance Tasks

### Weekly
- Review discovery logs
- Check Helm release status
- Monitor resource usage

### Monthly
- Update chart versions
- Rotate SNMP credentials
- Review NetBox data quality

### Quarterly
- Backup NetBox database
- Update discovery agent image
- Review and update network ranges

## Support

For issues:
1. Check Helm release status: `flux get helmreleases -n netbox`
2. Review pod logs
3. Consult official chart documentation
4. Check GitHub issues for known problems

## Summary

You now have a production-ready, Helm-based NetBox deployment with:
- ✅ Official NetBox Helm chart (easy upgrades)
- ✅ Official Diode Helm chart (automated discovery)
- ✅ Custom discovery agent (multi-method)
- ✅ OIDC authentication (Kanidm)
- ✅ Persistent storage
- ✅ Ingress configuration
- ✅ Full documentation

**Next**: Follow the Quick Start guide above! 🚀
