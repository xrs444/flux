# NocoDB with SSO Authentication Shim

This deployment integrates NocoDB (free version) with Kanidm SSO using an authentication shim pattern.

## Architecture

```text
User → Traefik → oauth2-proxy (Kanidm SSO) → Auth Shim → NocoDB
```

1. **oauth2-proxy**: Authenticates users via Kanidm OIDC (shared instance in `traefik` namespace)
2. **Auth Shim**: Lightweight Node.js sidecar that:
   - Receives authenticated user email from oauth2-proxy headers
   - Maps SSO identity to NocoDB local credentials
   - Automatically logs into NocoDB API
   - Proxies requests with NocoDB auth token
3. **NocoDB**: Runs in standard mode, unaware of SSO

## Components

- **[configmap-auth-shim.yaml](configmap-auth-shim.yaml)**: Auth shim code (pure Node.js, no dependencies)
- **[deployment-nocodb.yaml](deployment-nocodb.yaml)**: NocoDB + auth-shim sidecar
- **[service-nocodb.yaml](service-nocodb.yaml)**: Routes to auth-shim (port 3000)
- **[middleware-nocodb-auth.yaml](middleware-nocodb-auth.yaml)**: Traefik ForwardAuth to oauth2-proxy
- **[ingressroute-nocodb.yaml](ingressroute-nocodb.yaml)**: Traefik route with oauth2 middleware
- **user-mapping-sealedsecret-nocodb.yaml**: User credential mapping (sealed secret)

## Setup

### 1. Create User Mapping SealedSecret

The auth shim needs to know which NocoDB credentials to use for each SSO user.

```bash
# Create a temporary plain secret file
cat > /tmp/user-mapping-secret.yaml <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: nocodb-user-mapping
  namespace: nocodb
type: Opaque
stringData:
  mapping: |
    {
      "alice@xrs444.net": {
        "email": "alice@xrs444.net",
        "password": "alice-nocodb-password"
      },
      "bob@xrs444.net": {
        "email": "bob@xrs444.net",
        "password": "bob-nocodb-password"
      }
    }
EOF

# Seal it with kubeseal
kubeseal --format=yaml \
  --controller-name=sealed-secrets \
  --controller-namespace=sealed-secrets \
  < /tmp/user-mapping-secret.yaml \
  > apps/nocodb/user-mapping-sealedsecret-nocodb.yaml

# Clean up the temporary file
rm /tmp/user-mapping-secret.yaml
```

### 2. Create NocoDB User Accounts

Before users can access NocoDB via SSO, you must create their local NocoDB accounts:

1. Temporarily disable oauth2-proxy by removing the middleware from [ingressroute-nocodb.yaml](ingressroute-nocodb.yaml)
2. Access NocoDB directly at <https://nocodb.xrs444.net>
3. Create user accounts matching the credentials in the user mapping
4. Re-enable oauth2-proxy middleware
5. Apply the sealed secret to the cluster

### 3. Enable the Sealed Secret

Uncomment the sealed secret in [kustomization.yaml](kustomization.yaml):

```yaml
resources:
  # ...
  - user-mapping-sealedsecret-nocodb.yaml  # Uncomment this line
```

### 4. Deploy

```bash
# Verify the configuration
kubectl kustomize flux/apps/nocodb

# Apply via Flux (GitOps)
git add .
git commit -m "Add NocoDB SSO auth shim"
git push

# Or apply directly
kubectl apply -k flux/apps/nocodb
```

## How It Works

### Authentication Flow

1. User visits `https://nocodb.xrs444.net`
2. Traefik applies `nocodb-oauth2` middleware
3. Traefik calls oauth2-proxy ForwardAuth endpoint
4. oauth2-proxy redirects to Kanidm if not authenticated
5. After Kanidm login, oauth2-proxy returns success with `X-Auth-Request-Email` header
6. Traefik forwards request to auth-shim with email header
7. Auth-shim:
   - Checks session cache for existing NocoDB token
   - If none, looks up user credentials from mapping secret
   - Calls NocoDB `/api/v1/auth/user/signin` API
   - Caches the token in memory
   - Sets `nc-session` cookie
8. Auth-shim proxies request to NocoDB with `xc-auth` token header
9. NocoDB sees authenticated request and serves content

### Session Management

- Sessions are cached in-memory for 7 days (configurable via `SESSION_TTL_SECONDS`)
- Expired sessions are cleaned up hourly
- `nc-session` cookie prevents re-login on every request
- Multi-replica deployment requires Redis for shared session store (future enhancement)

## Security Considerations

### Credential Storage

- NocoDB credentials are stored in a Kubernetes Secret (sealed with Bitnami Sealed Secrets)
- The auth-shim has access to plaintext credentials (necessary for API login)
- Limit RBAC access to the `nocodb-user-mapping` secret

### Session Security

- Sessions use cryptographically random IDs
- Cookies are `HttpOnly`, `Secure`, `SameSite=Lax`
- Session validation checks both ID and associated email
- Sessions expire after TTL

### Network Security

- Auth-shim runs as sidecar (localhost communication with NocoDB)
- Only auth-shim is exposed via Kubernetes Service
- NocoDB port 8080 is not exposed outside the pod
- oauth2-proxy enforces HTTPS and PKCE

## Maintenance

### Adding Users

1. Create NocoDB account (temporarily disable oauth2-proxy)
2. Update user mapping secret
3. Reseal and commit

### Removing Users

1. Delete NocoDB account via UI
2. Remove from user mapping secret
3. Reseal and commit

### Updating the Shim

Edit [configmap-auth-shim.yaml](configmap-auth-shim.yaml) and the deployment will automatically pick up changes on next restart.

### Troubleshooting

```bash
# Check auth-shim logs
kubectl logs -n nocodb deployment/nocodb -c auth-shim

# Check oauth2-proxy
kubectl logs -n traefik deployment/oauth2-proxy

# Test oauth2-proxy auth endpoint
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -v http://oauth2-proxy.traefik.svc.cluster.local:4180/oauth2/auth

# Check if user mapping is loaded
kubectl get secret -n nocodb nocodb-user-mapping -o jsonpath='{.data.mapping}' | base64 -d
```

## Limitations

- **Single replica only**: In-memory session store doesn't support multiple replicas (add Redis for HA)
- **Manual user provisioning**: NocoDB accounts must be created manually before SSO access
- **Password rotation**: Requires updating sealed secret and restarting pod
- **No automatic user sync**: Adding/removing users in Kanidm doesn't auto-provision in NocoDB

## Future Enhancements

- Redis session store for multi-replica support
- Automatic NocoDB user provisioning via API
- Role mapping from Kanidm groups to NocoDB roles
- Metrics and observability (Prometheus exports)
