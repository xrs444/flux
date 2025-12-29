# Kanidm OIDC Integration Guide

## Applications Supporting Kanidm OIDC

### 1. NocoDB

**Location**: `flux/apps/nocodb/deployment-nocodb.yaml`

**Environment Variables Needed**:
```yaml
- name: NC_OIDC_ISSUER
  value: "https://idm.xrs444.net/oauth2/openid/nocodb"
- name: NC_OIDC_CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: nocodb-oidc-secret
      key: client_id
- name: NC_OIDC_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: nocodb-oidc-secret
      key: client_secret
```

**Nix Config**: Create sealed secret in nix config with Kanidm OAuth2 credentials

---

### 2. Paperless-ngx

**Location**: `flux/apps/paperless-ngx/deployment-paperless-ngx.yaml`

**Environment Variables Needed**:
```yaml
- name: PAPERLESS_APPS
  value: "allauth.socialaccount.providers.openid_connect"
- name: PAPERLESS_SOCIALACCOUNT_PROVIDERS
  value: |
    {
      "openid_connect": {
        "SERVERS": [{
          "id": "kanidm",
          "name": "Kanidm",
          "server_url": "https://idm.xrs444.net/oauth2/openid/paperless/.well-known/openid-configuration",
          "token_auth_method": "client_secret_basic"
        }]
      }
    }
```

**Nix Config**: Create sealed secret with Kanidm OAuth2 credentials for paperless client

---

### 3. Linkwarden

**Location**: `flux/apps/linkwarden/deployment-linkwarden.yaml`

**Environment Variables Needed**:
```yaml
- name: OAUTH_PROVIDER
  value: "generic"
- name: OAUTH_ID
  valueFrom:
    secretKeyRef:
      name: linkwarden-oidc-secret
      key: client_id
- name: OAUTH_SECRET
  valueFrom:
    secretKeyRef:
      name: linkwarden-oidc-secret
      key: client_secret
- name: OAUTH_ISSUER
  value: "https://idm.xrs444.net/oauth2/openid/linkwarden"
```

**Nix Config**: Create sealed secret with Kanidm OAuth2 credentials for linkwarden client

---

### 4. Jitsi (Advanced)

**Location**: `flux/apps/jitsi/configmap-jitsi.yaml` and `deployment-jitsi.yaml`

**Configuration Needed**:
- Enable JWT authentication in Jitsi
- Configure Prosody XMPP server with JWT plugin
- Set up token verification with Kanidm

**Notes**: Jitsi JWT authentication is more complex and requires:
1. Prosody JWT authentication module
2. Kanidm to issue JWT tokens
3. Custom integration work

**Nix Config**: This will require significant configuration in the nix setup to generate
appropriate JWT tokens and configure Jitsi properly.

---

## Nix Configuration Tasks

In your nix configuration (`nix/` directory), you will need to:

1. **Create Kanidm OAuth2 clients** for each application:
   - nocodb
   - paperless
   - linkwarden
   - jitsi (if implementing)

2. **Generate SealedSecrets** for each application containing:
   - client_id
   - client_secret

3. **Configure redirect URIs** in Kanidm for each client:
   - NocoDB: https://nocodb.xrs444.net/auth/callback
   - Paperless: https://paperless.xrs444.net/accounts/oidc/kanidm/login/callback/
   - Linkwarden: https://linkwarden.xrs444.net/api/auth/callback/generic

4. **Set appropriate scopes** for each client:
   - openid
   - profile
   - email
   - groups (if needed)

## Reference

Similar to the existing `oauth2-proxy-sealedsecret-longhorn.yaml` pattern in
`flux/infrastructure/controllers/longhorn/`
