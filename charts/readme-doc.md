# charts

## Overview

Custom Helm charts for applications that don't have suitable upstream charts or require significant customization for the HomeProd environment.

## Charts

### craftycontroller/
Custom Helm chart for CraftyController Minecraft server management platform.

**Features:**
- Kanidm OAuth2 authentication integration for SSO
- Persistent storage for Minecraft server data
- Configurable resource requests and limits
- Ingress with automatic TLS certificate
- Namespace isolation

**Chart Files:**
- `Chart.yaml` - Chart metadata, version, and dependencies
- `values.yaml` - Default configuration values
- `templates/` - Kubernetes manifest templates:
  - `deployment.yaml` - Main application deployment
  - `service.yaml` - ClusterIP service
  - `ingress.yaml` - Traefik ingress with TLS
  - `pvc.yaml` - Persistent volume claim
  - `namespace.yaml` - Dedicated namespace

**Configuration:**
The chart supports customization via values:
```yaml
ingress:
  hosts:
    - host: crafty.xrs444.net
persistence:
  size: 50Gi
resources:
  limits:
    cpu: 2000m
    memory: 4Gi
auth:
  kanidm:
    enabled: true
    url: "https://auth.xrs444.net"
```

**Usage:**

Referenced by `apps/craftycontroller/helmrelease.yaml`:
```yaml
chart:
  spec:
    chart: ./flux/charts/craftycontroller
    sourceRef:
      kind: GitRepository
      name: flux-system
      namespace: flux-system
```

## Creating New Charts

To add a new custom Helm chart:

1. Create chart directory: `charts/<chart-name>/`
2. Add `Chart.yaml` with metadata and version
3. Add `values.yaml` with default values and documentation
4. Create `templates/` directory with Kubernetes manifests
5. Use Helm templating for configurable values
6. Test locally before committing
7. Reference in app HelmRelease with GitRepository source

## Chart Development

Test charts locally before committing:
```bash
# Render templates with default values
helm template charts/craftycontroller

# Lint for issues
helm lint charts/craftycontroller

# Test with custom values
helm template charts/craftycontroller -f custom-values.yaml
```

## Best Practices

- Version charts using semantic versioning in Chart.yaml
- Document all values in values.yaml with comments
- Use sensible defaults that work out of the box
- Include resource requests and limits
- Support ingress configuration
- Enable OAuth2/authentication where appropriate
- Test with Flux HelmRelease before production use
