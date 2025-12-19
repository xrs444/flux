# infrastructure/configs

## Overview

Configuration resources that depend on infrastructure controllers. Deployed after controllers are ready and healthy.

## Directories

- **cluster-issuers/** - Let's Encrypt certificate issuers (staging and production)
- **helmrepositories/** - Additional Helm chart repositories for configurations
- **reflector/** - Reflector deployment for secret/ConfigMap replication across namespaces

## Files

- **kustomization.yaml** - Lists all configuration directories
- **kustomization-configs.yaml** - Flux Kustomization wrapper (not actively used)

## Deployment Order

These configurations are deployed after all controllers from `infrastructure/controllers/` are ready:

1. Helm Repositories - Additional chart sources
2. ClusterIssuers - Let's Encrypt issuers (requires Cert-Manager)
3. Reflector - Secret replication (requires basic cluster services)

## Configuration Details

### ClusterIssuers

The cluster-issuers directory configures:
- Let's Encrypt production issuer for trusted certificates
- Wildcard certificate for `*.xrs444.net` domain
- Automatic certificate renewal before expiry
- Certificate stored in `letsencrypt-wildcard-cert` namespace

**Key Resources:**
- `cluster-issuer-letsencrypt-prod.yaml` - Production issuer definition
- `certificate-wildcard-cert-letsencrypt-prod.yaml` - Wildcard cert request
- `namespace-letsencrypt-wildcard-cert.yaml` - Dedicated namespace
- `kustomization-letsencrypt-wildcard-cert.yaml` - Flux Kustomization

### Reflector

Reflector enables automatic replication of:
- Secrets across namespaces (e.g., TLS certificates, OAuth2 credentials)
- ConfigMaps for shared configuration

**Benefits:**
- Single source of truth for shared secrets
- Automatic updates when source changes
- Reduces manual secret management

### Helm Repositories

Additional chart repositories for infrastructure configs that aren't included in the controllers section.

## Reconciliation Settings

- **Interval**: 15m reconciliation interval
- **Timeout**: 5m (sufficient for config resources)
- **Pruning**: Enabled (`prune: true`) - safe to remove when not needed
- **Dependencies**: Requires `infra-controllers` to be healthy
