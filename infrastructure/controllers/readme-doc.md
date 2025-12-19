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
- **traefik/** - Ingress controller with OAuth2 proxy integration
- **traefik-crds/** - Traefik Custom Resource Definitions

## Files

- **kustomization.yaml** - Lists all controller directories to deploy
- **kustomization-controllers.yaml** - Flux Kustomization wrapper (not actively used)

## Deployment Order

1. Helm Repositories - Required for Helm-based controllers
2. Cilium - CNI must be running for pod networking
3. Cert-Manager - TLS management before ingress
4. Sealed Secrets - Secret management infrastructure
5. Traefik (CRDs then controller) - Ingress after networking is ready
6. Longhorn - Storage after basic services are running
7. Shared Secrets - After secret management is ready

## Configuration

- **Reconciliation**: 15m interval
- **Timeout**: 10m (allows for slower infrastructure deployments)
- **Pruning**: Disabled (`prune: false`) to prevent accidental deletion
- **Wait**: Enabled to ensure readiness before proceeding

## Controller Details

### Traefik
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
