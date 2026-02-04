# NetBox + Diode Helm Deployment - Quick Reference

## 🚀 Quick Deploy

```bash
# 1. Deploy NetBox + Diode (Helm)
kubectl apply -k flux/apps/netbox/

# 2. Check status
flux get helmreleases -n netbox
kubectl get pods -n netbox

# 3. Get NetBox URL
kubectl get ingress -n netbox
```

## 📦 What's Deployed

```
netbox namespace:
├── NetBox (Helm chart v5.0+)
│   ├── PostgreSQL 15 (StatefulSet)
│   ├── Redis 7 (StatefulSet)
│   └── NetBox app
└── Diode Server (Helm chart v1.13+)

diode-agent namespace:
└── Discovery Agent (CronJob - hourly)
```

## 🔧 Common Commands

### Helm Releases

```bash
# List releases
flux get helmreleases -n netbox
helm list -n netbox

# Check release values
helm get values netbox -n netbox

# Force reconcile
flux reconcile helmrelease netbox -n netbox
```

### Logs

```bash
# NetBox logs
kubectl logs -n netbox -l app.kubernetes.io/name=netbox

# Diode logs
kubectl logs -n netbox -l app.kubernetes.io/name=diode

# PostgreSQL logs
kubectl logs -n netbox -l app.kubernetes.io/name=postgresql

# Discovery agent logs
kubectl logs -n diode-agent -l app=diode-discovery-agent -f
```

### Discovery Agent

```bash
# Manual discovery run
kubectl create job --from=cronjob/diode-discovery-agent \
  -n diode-agent manual-$(date +%s)

# Check CronJob
kubectl get cronjob -n diode-agent

# View recent jobs
kubectl get jobs -n diode-agent --sort-by=.metadata.creationTimestamp
```

### Debugging

```bash
# Describe Helm release
kubectl describe helmrelease netbox -n netbox

# Check pods
kubectl get pods -n netbox -o wide

# Check services
kubectl get svc -n netbox

# Check PVCs
kubectl get pvc -n netbox

# Test Diode connectivity
kubectl run -it --rm test --image=busybox --restart=Never -- \
  nc -zv diode-diode-server.netbox.svc.cluster.local 8081
```

## ⚙️ Configuration Files

| File | Purpose |
|------|---------|
| `helmrelease-netbox.yaml` | NetBox config & values |
| `helmrelease-diode.yaml` | Diode config & values |
| `sealedsecret-netbox.yaml` | DB, Redis, API tokens |
| `oauth2-sealedsecret-netbox.yaml` | OIDC credentials |
| `diode-agent/configmap-diode-agent.yaml` | Discovery settings |
| `diode-agent/cronjob-discovery.yaml` | Schedule & image |

## 🔄 Upgrade Process

```bash
# 1. Edit helmrelease file
version: '>=5.1.0 <6.0.0'

# 2. Commit and push
git add flux/apps/netbox/
git commit -m "Upgrade NetBox chart"
git push

# 3. Flux auto-upgrades, or force:
flux reconcile helmrelease netbox -n netbox
```

## 🔐 Secrets Management

```bash
# View sealed secret (encrypted)
kubectl get sealedsecret netbox-secret -n netbox -o yaml

# View actual secret (after unsealing)
kubectl get secret netbox-secret -n netbox -o yaml

# Update secret
# 1. Create new secret YAML
# 2. Seal it: kubeseal --format=yaml --cert=<cert> < secret.yaml
# 3. Update sealedsecret-netbox.yaml
# 4. Apply
```

## 📊 Monitoring

```bash
# Resource usage
kubectl top pods -n netbox
kubectl top pods -n diode-agent

# Events
kubectl get events -n netbox --sort-by='.lastTimestamp'

# Helm release history
helm history netbox -n netbox
```

## 🌐 URLs

- **NetBox**: https://netbox.xrs444.net
- **Diode** (internal): `diode-diode-server.netbox.svc.cluster.local:8081`
- **Kanidm OIDC**: https://idm.xrs444.net/oauth2/openid/oauth2_netbox

## 📝 Key Values

### NetBox

```yaml
# Replicas
replicaCount: 1

# Resources
resources:
  requests: { memory: "512Mi", cpu: "250m" }
  limits: { memory: "2Gi", cpu: "1000m" }

# Ingress
ingress.hosts[0].host: netbox.xrs444.net
```

### Diode

```yaml
# Service
service.port: 8081

# NetBox connection
config.netbox.apiUrl: "http://netbox:8080"
config.netbox.apiTokenSecret.name: netbox-secret
```

### Discovery Agent

```yaml
# Schedule
schedule: "0 * * * *"  # Hourly

# Diode URL
DIODE_SERVER_URL: "diode-diode-server.netbox.svc.cluster.local:8081"

# Methods
DISCOVERY_ENABLED_METHODS: "snmp,nmap,kubernetes,lldp"

# Networks
NETWORK_SCAN_RANGES: "192.168.1.0/24,10.0.0.0/24"
```

## 🔥 Emergency Commands

```bash
# Restart NetBox
kubectl rollout restart deployment netbox -n netbox

# Restart Diode
kubectl rollout restart deployment diode-diode-server -n netbox

# Scale down NetBox
kubectl scale deployment netbox -n netbox --replicas=0

# Scale up
kubectl scale deployment netbox -n netbox --replicas=1

# Suspend CronJob
kubectl patch cronjob diode-discovery-agent -n diode-agent \
  -p '{"spec":{"suspend":true}}'

# Resume CronJob
kubectl patch cronjob diode-discovery-agent -n diode-agent \
  -p '{"spec":{"suspend":false}}'
```

## 🎯 Important Paths

```
flux/apps/netbox/
├── README.md                    # Full documentation
├── HELM_MIGRATION_SUMMARY.md    # Migration guide
├── QUICK_REFERENCE.md           # This file
├── helmrelease-netbox.yaml      # Edit for NetBox config
├── helmrelease-diode.yaml       # Edit for Diode config
└── diode-agent/
    ├── README.md                # Discovery agent docs
    ├── QUICKSTART.md            # Agent quick start
    └── configmap-diode-agent.yaml  # Edit for discovery config
```

## 📚 Documentation Links

- [Full README](README.md)
- [Migration Summary](HELM_MIGRATION_SUMMARY.md)
- [Discovery Agent README](diode-agent/README.md)
- [Discovery Agent Quick Start](diode-agent/QUICKSTART.md)

## ✅ Checklist

Initial Setup:
- [ ] Review Helm values in helmrelease files
- [ ] Verify sealed secrets exist
- [ ] Deploy: `kubectl apply -k flux/apps/netbox/`
- [ ] Check pods: `kubectl get pods -n netbox`
- [ ] Access NetBox UI: https://netbox.xrs444.net
- [ ] Create API token with write permissions
- [ ] Add DIODE_API_TOKEN to sealedsecret-netbox.yaml
- [ ] Build discovery agent container
- [ ] Configure network ranges in agent ConfigMap
- [ ] Deploy agent: `kubectl apply -k flux/apps/netbox/diode-agent/`
- [ ] Test discovery: manual job run
- [ ] Verify devices in NetBox

## 🆘 Troubleshooting Quick Fixes

**Helm release failed?**
```bash
kubectl describe helmrelease netbox -n netbox
```

**Can't access NetBox?**
```bash
kubectl get ingress -n netbox
kubectl get svc -n netbox
```

**Diode not working?**
```bash
kubectl logs -n netbox -l app.kubernetes.io/name=diode
kubectl get secret netbox-secret -n netbox  # Check DIODE_API_TOKEN exists
```

**Discovery agent errors?**
```bash
kubectl logs -n diode-agent -l app=diode-discovery-agent --tail=50
# Check service name: kubectl get svc -n netbox | grep diode
```

## 📞 Support

1. Check logs (see commands above)
2. Review [README.md](README.md) troubleshooting section
3. Check official docs:
   - [NetBox Chart](https://github.com/netbox-community/netbox-chart)
   - [Diode Docs](https://netboxlabs.com/docs/diode/)
4. Join [NetBox Slack](https://netdev.chat/) - #netbox-chart

---

**Need more detail?** See [README.md](README.md) for comprehensive documentation.
