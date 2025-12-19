# infrastructure

## Overview

Core infrastructure components divided into controllers and configurations. Controllers are deployed first, then configurations that depend on them.

## Directories

- **controllers/** - Core cluster services and operators
- **configs/** - Configuration resources that depend on controllers

## Deployment Stages

### Stage 1: Controllers
Essential cluster services deployed from `infrastructure/controllers/`:
- Cert-Manager - TLS certificate management
- Cilium - CNI and network policies
- Longhorn - Distributed block storage
- Traefik - Ingress controller with OAuth2
- Sealed Secrets - Encrypted secrets for GitOps
- Helm Repositories - Chart sources

### Stage 2: Configs
Configuration resources deployed from `infrastructure/configs/` after controllers are ready:
- ClusterIssuers - Let's Encrypt certificate issuers
- Reflector - Secret/ConfigMap replication across namespaces
- Additional infrastructure configurations

## Reconciliation

Infrastructure is managed by two Flux Kustomizations defined in `cluster/infrastructure.yaml`:

1. **infra-controllers** (15m interval, 10m timeout, prune: false)
2. **infra-configs** (15m interval, 5m timeout, prune: true, depends on infra-controllers)

Controllers use `prune: false` to prevent accidental deletion of critical infrastructure.
