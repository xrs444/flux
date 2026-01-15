# This Flux repo is in flux!

The configurations in this repo are still under development, and so are not guaranteed to be correct, working or anything other than a possibly interesting example. I will try run a list of what is working, what is not and what is yet to do, but don't expect to be able to deploy this verbatim and have it all work out the box.

# HomeProd Flux GitOps Repository

This repository contains the Flux GitOps configuration for the HomeProd Talos cluster, managing infrastructure controllers and applications using a GitOps workflow. All Kubernetes resources are declaratively managed and automatically reconciled by Flux.

It is the sister repo to https://github.com/xrs444/nix, which covers configuration of the hosts, clients and VMs.

## Repository Structure

\`\`\`
flux/
├── cluster/           # Flux system configuration and top-level Kustomizations
├── apps/              # Application deployments and services
├── infrastructure/    # Core infrastructure controllers and configs
├── charts/            # Custom Helm charts
└── scripts/           # Utility scripts for validation and maintenance
\`\`\`

## Architecture Overview

This Flux deployment follows a layered approach with clear dependency management:

1. **Flux System** (\`cluster/flux-system/\`) - Core Flux components and GitRepository source
2. **Infrastructure Controllers** (\`infrastructure/controllers/\`) - Essential cluster services (Cert-Manager, Traefik, Longhorn, Cilium, etc.)
3. **Infrastructure Configs** (\`infrastructure/configs/\`) - Configuration resources (ClusterIssuers, secrets, etc.)
4. **Applications** (\`apps/\`) - User-facing applications and services

## Key Components

### Infrastructure Controllers
- **Traefik**: Ingress controller with OAuth2 authentication
- **Cert-Manager**: Automated TLS certificate management
- **Longhorn**: Distributed block storage for persistent volumes
- **Cilium**: CNI and network policy enforcement
- **Sealed Secrets**: Encrypted secrets management

### Applications
- **Atuin**: Shell history sync server
- **Audiobookshelf**: Audiobook and podcast server
- **CraftyController**: Minecraft server management (custom Helm chart)
- **FreePBX**: VoIP PBX system
- **Jellyfin**: Media streaming server
- **LubeLogger**: Vehicle maintenance tracking
- **Mealie**: Recipe management
- **n8n**: Workflow automation platform
- **Omada**: TP-Link network controller
- **Metrics Server**: Cluster-wide resource metrics
- **Kube-State-Metrics**: Kubernetes object metrics for monitoring

## Flux Reconciliation Flow

\`\`\`
GitRepository (flux-system)
    ↓
cluster/infrastructure.yaml
    ↓
├── infra-controllers (infrastructure/controllers/)
│   ├── Helm repositories
│   ├── Cert-Manager
│   ├── Cilium
│   ├── Longhorn
│   ├── Traefik
│   └── Sealed Secrets
    ↓
├── infra-configs (infrastructure/configs/)
│   ├── ClusterIssuers
│   ├── Reflector
│   └── Additional configs
    ↓
cluster/apps.yaml
    ↓
└── apps (apps/)
        └── Individual application deployments
\`\`\`

## Documentation

See individual \`readme-doc.md\` files in each directory for detailed component documentation:
- [cluster/readme-doc.md](cluster/readme-doc.md) - Flux system and top-level Kustomizations
- [infrastructure/readme-doc.md](infrastructure/readme-doc.md) - Infrastructure controllers and configs
- [apps/readme-doc.md](apps/readme-doc.md) - Application deployments
- [charts/readme-doc.md](charts/readme-doc.md) - Custom Helm charts
- [scripts/readme-doc.md](scripts/readme-doc.md) - Utility scripts

## Quick Reference

### Check Flux Status
\`\`\`bash
flux check
flux get kustomizations
flux get helmreleases -A
\`\`\`

### Manual Reconciliation
\`\`\`bash
flux reconcile kustomization flux-system --with-source
\`\`\`

### Validation
\`\`\`bash
./scripts/validate.sh
\`\`\`


### Todo
- Add ROMm for retro gaming fun
- Finish SSO for everything that can use it
- Migrate Omada from existing VM
- Use Ntfy for Github action alerts
- Move PV/PVCs from storage folder to the relevant app folder.
- Configure Longhorn groups for backup
- Confgure Atuin backup to NFS
- Set up storage for Manyfold
- Migrate Freepbx from existing VM
- Build Dashy dashboard
- Add Apprise to feed to Ntfy
- BorgWarehouse for Borg backups
- Immich
- Configure Garage
- Audiobookshelf
- NoCoDB Auth proxy for oauth2
- Configure Jitsi
