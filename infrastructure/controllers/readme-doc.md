# infrastructure/controllers

## Overview

Core infrastructure controllers that provide essential cluster services. These are deployed before any configurations or applications.

## Directories

- **cert-manager/** - Automated TLS certificate management with Let's Encrypt
- **charts/** - Chart definitions for infrastructure components
- **cilium/** - CNI, network policies, and advanced networking capabilities
- **helmrepositories/** - External Helm chart repository definitions
- **longhorn/** - Distributed block storage system with web UI and OAuth2 protection
- **sealedsecrets/** - Encrypted secrets management for GitOps workflows
- **shared-secrets/** - Secrets shared across namespaces via Reflector
- **traefik/** - Ingress controller with OAuth2 proxy integration (v38+, CRDs managed by chart)

## Files

- **kustomization.yaml** - Lists all controller directories to deploy
- **kustomization-controllers.yaml** - Flux Kustomization wrapper (not actively used)

## Deployment Order

1. Helm Repositories - Required for Helm-based controllers
2. Cilium - CNI must be running for pod networking
3. Cert-Manager - TLS management before ingress
4. Sealed Secrets - Secret management infrastructure
5. Traefik - Ingress after networking is ready (CRDs managed by chart v38+)
6. Longhorn - Storage after basic services are running
7. Shared Secrets - After secret management is ready

## Configuration

- **Reconciliation**: 15m interval
- **Timeout**: 10m (allows for slower infrastructure deployments)
- **Pruning**: Disabled (`prune: false`) to prevent accidental deletion
- **Wait**: Enabled to ensure readiness before proceeding

## Controller Details

### Traefik

- Ingress controller v38+ with Helm-managed CRDs
- Includes OAuth2 proxy for authentication
- Dashboard protected by OAuth2
- Middleware for API and dashboard access
- Kanidm integration for SSO

### Longhorn

- Multiple storage classes (standard, reclaim, ephemeral)
- Web UI with OAuth2 protection
- Backup and snapshot capabilities
- Distributed across cluster nodes

### Cert-Manager

- Automated certificate lifecycle
- Let's Encrypt integration
- Wildcard certificate support
- Automatic renewal

### Cilium

- CNI plugin for pod networking
- Network policy enforcement
- Service mesh capabilities
- eBPF-based performance

## Orphan review (`infra-controllers` runs with `prune: false`)

`prune: false` protects core infrastructure from an accidental delete, but it also means an
object removed from git is **never** removed from the cluster. Review periodically (and after
removing anything from `infrastructure/controllers/`).

**Find orphans** — live objects Flux labelled as owned by `infra-controllers` that are no
longer in its inventory:

```sh
# Current inventory ids (ns_name_group_kind)
kubectl -n flux-system get kustomization infra-controllers -o json \
  | python3 -c "import sys,json;print('\n'.join(e['id'] for e in json.load(sys.stdin)['status']['inventory']['entries']))" > inv.txt

# Live objects carrying the ownership label, across every listable kind
for r in $(kubectl api-resources --verbs=list -o name | grep -vE '^(events|events.events.k8s.io|endpoints|endpointslices.discovery.k8s.io|leases.coordination.k8s.io)$'); do
  kubectl get $r -A -l kustomize.toolkit.fluxcd.io/name=infra-controllers,kustomize.toolkit.fluxcd.io/namespace=flux-system -o json 2>/dev/null \
    | python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: sys.exit()
for i in d.get('items',[]):
  m=i['metadata']; a=i['apiVersion']; g=a.split('/')[0] if '/' in a else ''
  print('%s_%s_%s_%s'%(m.get('namespace',''),m['name'],g,i['kind']))"
done > live.txt

# Orphans = in live.txt, not in inv.txt (use a set diff — `comm` needs identical sort order)
python3 -c "print(*sorted(set(open('live.txt').read().split())-set(open('inv.txt').read().split())),sep='\n')"
```

**Before deleting each candidate**, confirm it is really unused: not referenced in git
(`git grep <name>`), no pod mounts/uses it (`kubectl get pods -A -o json | grep <name>`), and
nothing selects it. Save the live manifest first (`kubectl get ... -o yaml > backup.yaml`),
then `kubectl delete` it by hand and re-run the diff to confirm it is gone.

First review: 2026-11-25 removed 9 orphans — the `nfs-mounter` namespace/DaemonSet/Service
(a privileged `hostPath: /` pod nothing used), three `*-metrics-nodeport` Services, two stale
Longhorn oauth2-proxy SealedSecrets, and a duplicate `kube-system` cilium `HelmRepository`.
