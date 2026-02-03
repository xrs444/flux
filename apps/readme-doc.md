# apps

## Overview

Application deployments for the HomeProd K3s cluster. Each application is organized in its own subdirectory with Kubernetes manifests or Helm releases.

## Applications

- **atuin/** - Shell history sync server for command history synchronization across machines
- **audiobookshelf/** - Audiobook and podcast server with web interface
- **craftycontroller/** - Minecraft server management platform (custom Helm chart with Kanidm OAuth2)
- **freepbx/** - VoIP PBX system for home telephony
- **helmrepositories/** - External Helm chart repository definitions
- **jellyfin/** - Media streaming server for movies, TV shows, and music
- **kube-state-metrics/** - Kubernetes object state metrics for Prometheus
- **lubelogger/** - Vehicle maintenance and fuel tracking application
- **mealie/** - Recipe management and meal planning
- **metrics-server/** - Cluster-wide resource usage metrics
- **omada/** - TP-Link Omada network controller for managing APs and switches
- **podinfo/** - Demo application for testing deployments and GitOps
- **storage/** - Storage class configurations and policies

## Files

- **kustomization.yaml** - Kustomize configuration listing all application resources
- **kustomization-apps.yaml** - Flux Kustomization wrapper (reconciliation settings)

## Application Structure

Each application directory typically contains:
- `namespace.yaml` - Dedicated Kubernetes namespace
- `deployment-<app>.yaml` - Deployment definition with containers and volumes
- `service-<app>.yaml` - Service for network access
- `pvc-<app>-*.yaml` - Persistent Volume Claims for data storage
- `kustomization.yaml` - Lists all resources for the application

Applications using Helm charts contain:
- `helmrelease.yaml` - Flux HelmRelease definition
- `namespace.yaml` - Namespace for the application
- `service-*.yaml` - Additional services (e.g., NodePort for game servers)
- `kustomization.yaml` - Resource list

## Adding New Applications

1. Create directory: `apps/<app-name>/`
2. Add Kubernetes manifests (namespace, deployment, service, PVCs)
3. Create `kustomization.yaml` listing all resources
4. Add reference to `apps/kustomization.yaml`
5. Commit and push - Flux reconciles automatically

## Dependencies

- Applications depend on `infra-configs` Kustomization
- Storage requires Longhorn to be healthy
- Ingress requires Traefik to be running
- TLS certificates require Cert-Manager and ClusterIssuers
