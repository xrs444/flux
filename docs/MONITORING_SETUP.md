# Monitoring Stack Setup Guide

This guide covers the complete setup of Prometheus, Grafana, and Apprise for monitoring your HomeProd infrastructure.

## Architecture Overview

### Components

1. **Prometheus** (xsvr1:9090) - Metrics collection and storage
2. **Grafana** (xsvr1:3000) - Metrics visualization and dashboards
3. **Alertmanager** (xsvr1:9093) - Alert routing and management
4. **Apprise** (Kubernetes) - Multi-platform notification gateway
5. **ntfy** (Kubernetes) - Push notification service
6. **Node Exporters** - System metrics from all hosts
7. **ZFS Exporters** - ZFS pool metrics (xsvr1, xsvr2)
8. **Bird Exporters** - BGP metrics (xts1, xts2)
9. **kube-state-metrics** - Kubernetes object metrics

### Monitoring Targets

- **NixOS Hosts**: xsvr1, xsvr2, xsvr3, xlabmgmt, xts1, xts2, xcomm1, xdash1, xhac-radio
- **Talos VMs**: 172.20.3.10, 172.20.3.20, 172.20.3.30
- **Kubernetes Cluster**: Pods, nodes, deployments, services, etc.

## Deployment Steps

### Step 1: Create Apprise Sealed Secret

Before deploying, you need to create the sealed secret for Apprise to connect to ntfy:

```bash
# 1. Get your ntfy credentials
# The ntfy service is at: ntfy.xrs444.net
# You should already have a user created in ntfy

# 2. Create the ntfy URL (replace USERNAME and PASSWORD)
echo -n "ntfy://USERNAME:PASSWORD@ntfy.xrs444.net/monitoring-alerts" > /tmp/ntfy-url.txt

# 3. Create and seal the secret
kubectl create secret generic apprise-config \
  --from-file=ntfy-url=/tmp/ntfy-url.txt \
  --namespace=monitoring \
  --dry-run=client -o yaml | \
kubeseal --controller-name=sealed-secrets \
  --controller-namespace=kube-system \
  -o yaml > flux/apps/apprise/sealedsecret-apprise-config.yaml

# 4. Clean up temporary file
rm /tmp/ntfy-url.txt

# 5. Commit the sealed secret
git add flux/apps/apprise/sealedsecret-apprise-config.yaml
```

### Step 2: Deploy Kubernetes Components

The Apprise pod will be automatically deployed by Flux CD:

```bash
# Verify Flux is syncing
kubectl get kustomization -n flux-system

# Watch for Apprise deployment
kubectl get pods -n monitoring -w

# Check Apprise logs once deployed
kubectl logs -n monitoring -l app=apprise
```

### Step 3: Deploy NixOS Changes to xsvr1

```bash
# From the repository root
cd /Users/xrs444/Repositories/HomeProd

# Deploy to xsvr1 (monitoring server)
sudo nixos-rebuild switch --flake .#xsvr1

# Or if deploying remotely:
nixos-rebuild switch --flake .#xsvr1 --target-host xsvr1 --use-remote-sudo
```

### Step 4: Verify Services

```bash
# Check Prometheus
curl http://xsvr1:9090/-/healthy
curl http://xsvr1:9090/api/v1/targets

# Check Grafana
curl http://xsvr1:3000/api/health

# Check Alertmanager
curl http://xsvr1:9093/-/healthy

# Check Kubernetes Apprise
kubectl get svc -n monitoring apprise
kubectl exec -n monitoring -it $(kubectl get pod -n monitoring -l app=apprise -o name) -- wget -O- http://localhost:8000
```

## Configuration Details

### Prometheus Scrape Jobs

| Job Name | Targets | Interval | Description |
|----------|---------|----------|-------------|
| `prometheus` | localhost:9090 | 15s | Prometheus self-monitoring |
| `node` | All NixOS hosts:9100 | 15s | System metrics (CPU, RAM, disk) |
| `talos-node` | Talos VMs:9100 | 15s | Talos node system metrics |
| `zfs` | xsvr1, xsvr2:9134 | 15s | ZFS pool metrics |
| `bird` | xts1, xts2:9324 | 15s | BGP routing metrics |
| `kubelet` | Talos VMs:10250 | 15s | Kubernetes pod/container metrics |
| `kubernetes-apiserver` | 172.20.3.10:6443 | 15s | K8s control plane metrics |
| `kube-state-metrics` | 172.20.3.10:30080 | 30s | K8s object state metrics |

### Alert Rules

#### Node Alerts
- **InstanceDown**: Host unreachable for >5m (critical)
- **HighCPUUsage**: CPU >80% for >10m (warning)
- **HighMemoryUsage**: Memory >90% for >10m (warning)
- **DiskSpaceLow**: Disk <10% free for >5m (warning)

#### Kubernetes Alerts
- **KubernetesPodCrashLooping**: Pod restarting frequently (warning)
- **KubernetesPodNotReady**: Pod not ready >15m (warning)
- **KubernetesNodeNotReady**: Node unavailable >5m (critical)

#### BGP Alerts
- **BGPSessionDown**: BGP session not established (critical)
- **BGPPeerFlapping**: BGP session unstable (warning)
- **TailscaleExitNodeBothDown**: Both exit nodes down (critical)

### Alert Flow

```
Prometheus → Alertmanager → Apprise → ntfy → Your Devices
```

1. Prometheus evaluates alert rules every 15s
2. Firing alerts sent to Alertmanager
3. Alertmanager groups and routes alerts to Apprise webhook
4. Apprise forwards to ntfy with configured topic
5. ntfy pushes notifications to subscribed devices

## Accessing the Monitoring Stack

### Via Tailscale

All monitoring services are accessible via Tailscale:

- **Grafana**: http://xsvr1:3000 (default: admin/admin - change on first login)
- **Prometheus**: http://xsvr1:9090
- **Alertmanager**: http://xsvr1:9093

### Grafana Dashboards

After deployment, add community dashboards:

1. Go to Grafana → Dashboards → Import
2. Enter dashboard ID or upload JSON
3. Recommended dashboards:
   - **Node Exporter Full** (ID: 1860) - Comprehensive host metrics
   - **Kubernetes Cluster Monitoring** (ID: 315) - K8s overview
   - **ZFS** (ID: 7845) - ZFS pool monitoring

Alternatively, download dashboard JSON files and place them in:
```
nix/modules/services/monitoring/dashboards/
```
Then rebuild xsvr1 to auto-provision them.

## Testing Alerts

### Test Alert Firing

```bash
# Stop a service to trigger InstanceDown alert
ssh xsvr3 "sudo systemctl stop prometheus-node-exporter.service"

# Wait 5+ minutes, then check Alertmanager
curl http://xsvr1:9093/api/v2/alerts

# Check if notification was sent to ntfy
# (Check your ntfy app or https://ntfy.xrs444.net)

# Restore service
ssh xsvr3 "sudo systemctl start prometheus-node-exporter.service"
```

### Send Test Notification via Apprise

```bash
# Send a test notification directly to Apprise
kubectl exec -n monitoring $(kubectl get pod -n monitoring -l app=apprise -o name) -- \
  apprise -b "Test notification from Apprise" \
  "ntfy://USERNAME:PASSWORD@ntfy.xrs444.net/monitoring-alerts"
```

## Troubleshooting

### Prometheus Not Scraping Targets

```bash
# Check Prometheus targets status
curl http://xsvr1:9090/api/v1/targets | jq .

# Check if exporters are running
systemctl status prometheus-node-exporter.service
systemctl status prometheus-zfs-exporter.service

# Check firewall (should allow on tailscale0)
sudo iptables -L -n | grep 9100
```

### Apprise Not Receiving Alerts

```bash
# Check Alertmanager config
curl http://xsvr1:9093/api/v1/status

# Check Apprise pod logs
kubectl logs -n monitoring -l app=apprise

# Verify Apprise can reach ntfy
kubectl exec -n monitoring $(kubectl get pod -n monitoring -l app=apprise -o name) -- \
  wget -O- https://ntfy.xrs444.net/
```

### Grafana Dashboard Issues

```bash
# Check Grafana logs
journalctl -u grafana.service -f

# Verify Prometheus datasource
curl http://xsvr1:3000/api/datasources

# Test Prometheus query from Grafana
curl -H "Content-Type: application/json" \
  http://xsvr1:3000/api/datasources/proxy/1/api/v1/query?query=up
```

## Maintenance

### Updating Dashboards

```bash
# Download new dashboard JSON
curl -o node-exporter.json https://grafana.com/api/dashboards/1860/revisions/latest/download

# Place in dashboards directory
cp node-exporter.json nix/modules/services/monitoring/dashboards/

# Deploy
sudo nixos-rebuild switch --flake .#xsvr1
```

### Adjusting Alert Thresholds

Edit alert rules in:
```
nix/modules/services/monitoring/prometheus.nix
```

Look for the `rules` section and modify expressions like:
```nix
expr = ''(100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)) > 80'';
```

### Adding New Scrape Targets

Edit:
```
nix/modules/services/monitoring/prometheus.nix
```

Add to appropriate host list or create new scrape config.

## Next Steps

1. ✅ Configure Apprise sealed secret with your ntfy credentials
2. ✅ Deploy Kubernetes components (Flux will auto-deploy)
3. ✅ Deploy NixOS changes to xsvr1
4. ✅ Verify all services are running
5. ✅ Test alert notifications
6. ✅ Import Grafana dashboards
7. ✅ Set up Grafana admin password
8. ✅ Subscribe to ntfy topic on your devices

## Security Notes

- All monitoring ports are only accessible via Tailscale (tailscale0 interface)
- Grafana default password should be changed immediately
- ntfy credentials stored as sealed secrets in Kubernetes
- Prometheus and Alertmanager use HTTP (internal network only)
- Consider adding authentication to Prometheus/Alertmanager if needed

## Files Modified

- `flux/apps/apprise/*` - New Apprise deployment
- `flux/apps/kustomization.yaml` - Added Apprise to app list
- `nix/modules/services/monitoring/prometheus.nix` - Added Talos/K8s scraping, Alertmanager webhook
- `nix/modules/services/monitoring/grafana.nix` - Added dashboard provisioning
- `nix/modules/services/monitoring/dashboards/` - Dashboard storage directory

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Apprise Documentation](https://github.com/caronc/apprise)
- [ntfy Documentation](https://docs.ntfy.sh/)
- Existing docs: `nix/docs/monitoring.md`, `nix/docs/alerting-guide.md`
