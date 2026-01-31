# New Applications Added

## Summary

Added 8 new applications to the HomeProd Kubernetes cluster:

1. **NocoDB** - No-code database platform
2. **Loki** - Log aggregation system with Promtail
3. **Paperless-ngx** - Document management system
4. **Jitsi** - Video conferencing platform
5. **Ntfy** - Push notification service
6. **Diskover** - File system indexer and search
7. **Linkwarden** - Bookmark and link management
8. **Garage** - S3-compatible object storage

## Kanidm OIDC Integration

The following applications support Kanidm OIDC authentication:

- **NocoDB**: Configure via NC_OIDC_* environment variables
- **Paperless-ngx**: Configure via PAPERLESS_APPS and PAPERLESS_SOCIALACCOUNT_PROVIDERS
- **Linkwarden**: Configure via OAUTH_* environment variables
- **Jitsi**: Requires JWT authentication setup (more complex)

## TODO Items

### Secrets and Configuration

1. **NocoDB**: Generate OIDC client credentials
2. **Paperless-ngx**: Generate secure PAPERLESS_SECRET_KEY
3. **Jitsi**: Generate secure secrets for Jicofo and JVB components
4. **Linkwarden**: Generate secure NEXTAUTH_SECRET
5. **Garage**: Generate 32-byte hex RPC secret and admin token

### Loki Log Collection

Promtail DaemonSet has been deployed to collect logs from all pods and send to Loki.
All applications will automatically have their logs collected.

### Storage

All applications use Longhorn storage class for persistent volumes:

- NocoDB: 10Gi
- Loki: 50Gi
- Paperless-ngx: 70Gi total (data + media + consume)
- Jitsi: 5Gi
- Ntfy: 5Gi
- Diskover: 20Gi
- Linkwarden: 10Gi
- Garage: 100Gi

### Domains

Applications will be available at:

- https://nocodb.xrs444.net
- https://loki.xrs444.net
- https://paperless.xrs444.net
- https://jitsi.xrs444.net
- https://ntfy.xrs444.net
- https://diskover.xrs444.net
- https://linkwarden.xrs444.net
- https://s3.xrs444.net (Garage S3 API)
- https://garage.xrs444.net (Garage web UI)
