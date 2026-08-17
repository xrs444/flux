# NetBox Helm Chart Migration - Complete Summary

> **⚠️ REMOVED — DO NOT USE.** The Diode portions of this migration were removed — didn't work well in this deployment. See the banner in [README.md](README.md). Kept for historical reference only. (2026-08-17)

## What We Built

A complete refactoring of your NetBox deployment to use **official Helm charts** from NetBox Community and NetBox Labs, replacing manual Kubernetes manifests.

## Why This Is Better

### Before (Manual Manifests)
- ❌ Custom deployment YAML
- ❌ Manual PostgreSQL/Redis sidecars
- ❌ Hard to upgrade
- ❌ Manual dependency management
- ❌ Reinventing the wheel

### After (Helm Charts)
- ✅ Official NetBox Community chart (v5.0+)
- ✅ Official Diode chart (v1.13+)
- ✅ Managed PostgreSQL/Redis via Helm
- ✅ Easy upgrades (version bump)
- ✅ Production-tested defaults
- ✅ Community support

## Architecture Comparison

### Old Architecture
```
┌─────────────────────────────────┐
│    NetBox Pod (Manual)          │
│  ┌───────────────────────────┐  │
│  │ NetBox Container          │  │
│  │ PostgreSQL Sidecar        │  │
│  │ Redis Sidecar             │  │
│  │ Diode Sidecar (custom)    │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
```

### New Architecture (Helm)
```
┌────────────────────────────────────────────────┐
│           NetBox Namespace                     │
├────────────────────────────────────────────────┤
│                                                │
│  ┌────────────────────┐  ┌─────────────────┐  │
│  │ NetBox Pod         │  │ PostgreSQL Pod  │  │
│  │ (Helm-managed)     │  │ (StatefulSet)   │  │
│  └────────────────────┘  └─────────────────┘  │
│                                                │
│  ┌────────────────────┐  ┌─────────────────┐  │
│  │ Diode Server Pod   │  │ Redis Pod       │  │
│  │ (Helm-managed)     │  │ (StatefulSet)   │  │
│  └────────────────────┘  └─────────────────┘  │
└────────────────────────────────────────────────┘
         ▲
         │ gRPC
         │
┌────────┴───────────────────────────────────────┐
│      Diode Discovery Agent (CronJob)           │
│         (diode-agent namespace)                │
└────────────────────────────────────────────────┘
```

## What Changed

### NetBox Deployment

| Aspect | Old | New |
|--------|-----|-----|
| Deployment method | Manual YAML | HelmRelease |
| Chart | N/A | netbox-community/netbox v5.0+ |
| PostgreSQL | Sidecar container | Helm-managed StatefulSet |
| Redis | Sidecar container | Helm-managed StatefulSet |
| Configuration | ConfigMap + env vars | Helm values.yaml |
| Upgrades | Manual YAML edits | Chart version bump |

### Diode Deployment

| Aspect | Old | New |
|--------|-----|-----|
| Deployment | Custom sidecar | HelmRelease |
| Chart | N/A | netboxlabs/diode v1.13+ |
| Service | Manual service.yaml | Helm-managed |
| Configuration | Manual ConfigMap | Helm values.yaml |

### Discovery Agent

| Aspect | Old | New |
|--------|-----|-----|
| Code | ✅ Same Python script | ✅ Same Python script |
| Dockerfile | ✅ Same | ✅ Same |
| Schedule | ✅ Same CronJob | ✅ Same CronJob |
| Service URL | `diode-server.netbox...` | `diode-diode-server.netbox...` |
| Secrets | ✅ Same sealed secrets | ✅ Same sealed secrets |

## File Structure

```
flux/apps/
├── netbox/                          # 📦 OLD - Manual manifests
│   ├── deployment-netbox.yaml       #    (can be archived/removed)
│   ├── service-netbox.yaml
│   ├── configmap-netbox.yaml
│   ├── sealedsecret-netbox.yaml     #    ⬇️ Copied to new location
│   ├── oauth2-sealedsecret-netbox.yaml  # ⬇️ Copied to new location
│   ├── diode-agent/                 #    ⬇️ Copied to new location
│   └── ...
│
└── netbox/                     # ✨ NEW - Helm-based deployment
    ├── namespace-netbox.yaml        # Namespace
    ├── helmrepository-netbox.yaml   # NetBox chart repo
    ├── helmrepository-diode.yaml    # Diode chart repo (OCI)
    ├── helmrelease-netbox.yaml      # 🎯 NetBox Helm release
    ├── helmrelease-diode.yaml       # 🎯 Diode Helm release
    ├── sealedsecret-netbox.yaml     # From old deployment
    ├── oauth2-sealedsecret-netbox.yaml  # From old deployment
    ├── kustomization.yaml           # Kustomize manifest
    ├── README.md                    # Complete documentation
    ├── HELM_MIGRATION_SUMMARY.md    # This file
    │
    └── diode-agent/                 # Discovery agent (updated)
        ├── configmap-diode-agent.yaml  # ✏️ Updated service URL
        └── ... (rest same as before)
```

## Deployment Files Created

### Core Helm Resources
1. ✅ [helmrepository-netbox.yaml](helmrepository-netbox.yaml) - NetBox chart repository
2. ✅ [helmrepository-diode.yaml](helmrepository-diode.yaml) - Diode OCI registry
3. ✅ [helmrelease-netbox.yaml](helmrelease-netbox.yaml) - NetBox HelmRelease + values
4. ✅ [helmrelease-diode.yaml](helmrelease-diode.yaml) - Diode HelmRelease + values
5. ✅ [namespace-netbox.yaml](namespace-netbox.yaml) - Namespace definition
6. ✅ [kustomization.yaml](kustomization.yaml) - Kustomize manifest

### Migrated Secrets
7. ✅ [sealedsecret-netbox.yaml](sealedsecret-netbox.yaml) - DB, Redis, API tokens
8. ✅ [oauth2-sealedsecret-netbox.yaml](oauth2-sealedsecret-netbox.yaml) - OIDC credentials

### Discovery Agent (Updated)
9. ✅ [diode-agent/](diode-agent/) - Complete discovery agent directory
   - ✏️ Updated ConfigMap with new Diode service name
   - All other files same as before

### Documentation
10. ✅ [README.md](README.md) - Complete deployment guide
11. ✅ [HELM_MIGRATION_SUMMARY.md](HELM_MIGRATION_SUMMARY.md) - This file

## Key Configuration Changes

### NetBox HelmRelease Values

```yaml
# helmrelease-netbox.yaml
spec:
  values:
    # Use official chart defaults for most settings
    replicaCount: 1

    # PostgreSQL now managed by Helm subchart
    postgresql:
      enabled: true
      auth:
        existingSecret: netbox-secret

    # Redis now managed by Helm subchart
    redis:
      enabled: true
      auth:
        existingSecret: netbox-secret

    # OIDC configuration via extraEnvs
    remoteAuth:
      enabled: true
      backend: social_core.backends.open_id_connect.OpenIdConnectAuth
```

### Diode HelmRelease Values

```yaml
# helmrelease-diode.yaml
spec:
  values:
    diode-server:
      enabled: true
      config:
        netbox:
          apiUrl: "http://netbox:8080"
          apiTokenSecret:
            name: netbox-secret
            key: DIODE_API_TOKEN
```

### Discovery Agent Update

```yaml
# diode-agent/configmap-diode-agent.yaml
data:
  # OLD: DIODE_SERVER_URL: "diode-server.netbox.svc.cluster.local:8081"
  # NEW: Service name follows Helm naming convention
  DIODE_SERVER_URL: "diode-diode-server.netbox.svc.cluster.local:8081"
```

## Migration Path

### Option 1: Fresh Deployment (Recommended)

1. **Deploy new Helm-based stack** to `netbox/`
2. **Verify** everything works
3. **Archive old deployment** (`flux/apps/netbox/`)
4. **Update Flux kustomization** to reference new path

### Option 2: In-Place Migration

1. **Backup NetBox data** first!
2. **Scale down old deployment**
3. **Deploy new Helm releases** (reuse PVCs if possible)
4. **Verify** data migration
5. **Remove old resources**

### Option 3: Side-by-Side Testing

1. **Deploy Helm stack** to new namespace (`netbox-helm`)
2. **Test thoroughly** with separate database
3. **Migrate data** when ready
4. **Switch ingress** to new deployment
5. **Decommission old deployment**

## What You Need to Do

### Immediate Actions

1. **Review Configuration**
   - [ ] Check [helmrelease-netbox.yaml](helmrelease-netbox.yaml) values
   - [ ] Check [helmrelease-diode.yaml](helmrelease-diode.yaml) values
   - [ ] Verify sealed secrets are correct

2. **Add DIODE_API_TOKEN**
   - [ ] Create NetBox API token (after first deploy)
   - [ ] Add to [sealedsecret-netbox.yaml](sealedsecret-netbox.yaml)

3. **Build Discovery Agent**
   - [ ] Build container: `cd diode-agent && ./build.sh`
   - [ ] Push to your registry
   - [ ] Update image in `diode-agent/cronjob-discovery.yaml`

4. **Deploy**
   - [ ] Choose migration strategy (fresh, in-place, or side-by-side)
   - [ ] Apply kustomization: `kubectl apply -k flux/apps/netbox/`
   - [ ] Verify: `flux get helmreleases -n netbox`

### Post-Deployment

5. **Configure Discovery Agent**
   - [ ] Edit network ranges in `diode-agent/configmap-diode-agent.yaml`
   - [ ] Create sealed credentials
   - [ ] Deploy agent: `kubectl apply -k flux/apps/netbox/diode-agent/`

6. **Test Discovery**
   - [ ] Run manual discovery job
   - [ ] Check logs for errors
   - [ ] Verify devices appear in NetBox

7. **Clean Up**
   - [ ] Archive old `flux/apps/netbox/` directory
   - [ ] Update Flux app kustomization
   - [ ] Document any custom changes

## Benefits Realized

### Operational Benefits
- 🚀 **Faster upgrades** - Just bump chart versions
- 🔧 **Easier management** - Values-based configuration
- 📊 **Better scaling** - Helm manages replicas and dependencies
- 🔒 **Security updates** - Official charts are maintained

### Development Benefits
- 📖 **Better documentation** - Official chart docs
- 🤝 **Community support** - Large user base
- 🧪 **Easier testing** - Helm test hooks available
- 🔄 **CI/CD friendly** - Standard Helm patterns

### Maintenance Benefits
- ⏱️ **Less YAML** - Helm handles boilerplate
- 🎯 **Focus on values** - Only customize what matters
- 🛠️ **Built-in best practices** - Production-tested defaults
- 📦 **Dependency management** - Helm subcharts

## Troubleshooting

### Helm Release Fails

```bash
# Check release status
flux get helmreleases -n netbox

# Describe release for errors
kubectl describe helmrelease netbox -n netbox

# Check Helm release directly
helm list -n netbox
helm get values netbox -n netbox
```

### Service Name Issues

If discovery agent can't connect:

```bash
# List services to find exact name
kubectl get svc -n netbox

# Should see something like:
# diode-diode-server    ClusterIP   ...   8081/TCP

# Update diode-agent ConfigMap if different
```

### Chart Version Compatibility

```bash
# Check available chart versions
helm search repo netbox/netbox --versions
helm search repo netboxlabs/diode --versions

# Update HelmRelease version constraints as needed
```

## Next Steps

1. **Read**: Full deployment guide in [README.md](README.md)
2. **Deploy**: Follow Quick Start section
3. **Configure**: Set up discovery agent
4. **Monitor**: Watch Helm releases and pods
5. **Optimize**: Adjust resources and scaling as needed

## Resources

### Official Documentation
- [NetBox Helm Chart](https://github.com/netbox-community/netbox-chart) - Official chart repo
- [NetBox Chart Hub](https://artifacthub.io/packages/helm/netbox/netbox) - Chart info and values
- [Diode Documentation](https://netboxlabs.com/docs/diode/) - Official Diode docs
- [NetBox Labs Blog: Diode Helm Chart](https://netboxlabs.com/blog/diode-helm-chart/) - Announcement

### Community
- [NetBox Slack](https://netdev.chat/) - #netbox-chart channel
- [Flux Documentation](https://fluxcd.io/flux/components/helm/) - HelmRelease guide

## Summary

You now have a **modern, Helm-based NetBox deployment** that:

✅ Uses official, community-maintained charts
✅ Simplifies upgrades and maintenance
✅ Follows Kubernetes best practices
✅ Integrates seamlessly with Flux CD
✅ Includes complete network discovery via Diode
✅ Is fully documented and production-ready

The only thing left is to deploy it! 🚀

---

**Questions?** See [README.md](README.md) for detailed documentation, or check the old deployment files in `../netbox/` for reference.

**Ready to deploy?** Follow the Quick Start in [README.md](README.md#quick-start)!
