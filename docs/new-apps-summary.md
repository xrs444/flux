# New Applications Added

## Summary

Added 7 new applications to the HomeProd Kubernetes cluster:

1. **Loki** - Log aggregation system with Promtail
2. **Paperless-ngx** - Document management system
3. **Jitsi** - Video conferencing platform
4. **Ntfy** - Push notification service
5. **Diskover** - File system indexer and search
6. **Linkwarden** - Bookmark and link management
7. **Garage** - S3-compatible object storage

## Kanidm OIDC Integration

The following applications support Kanidm OIDC authentication:

- **Paperless-ngx**: Configure via PAPERLESS_APPS and PAPERLESS_SOCIALACCOUNT_PROVIDERS
- **Linkwarden**: Configure via OAUTH_* environment variables
- **Jitsi**: Requires JWT authentication setup (more complex)

## TODO Items

### Secrets and Configuration

1. **Paperless-ngx**: Generate secure PAPERLESS_SECRET_KEY
2. **Jitsi**: Generate secure secrets for Jicofo and JVB components
3. **Linkwarden**: Generate secure NEXTAUTH_SECRET
4. **Garage**: Generate 32-byte hex RPC secret and admin token

### Loki Log Collection

Promtail DaemonSet has been deployed to collect logs from all pods and send to Loki.
All applications will automatically have their logs collected.

### Storage

All applications use Longhorn storage class for persistent volumes:

- Loki: 50Gi
- Paperless-ngx: 70Gi total (data + media + consume)
- Jitsi: 5Gi
- Ntfy: 5Gi
- Diskover: 20Gi
- Linkwarden: 10Gi
- Garage: 100Gi

### Domains

Applications will be available at:

- https://loki.xrs444.net
- https://paperless.xrs444.net
- https://jitsi.xrs444.net
- https://ntfy.xrs444.net
- https://diskover.xrs444.net
- https://linkwarden.xrs444.net
- https://s3.xrs444.net (Garage S3 API)
- https://garage.xrs444.net (Garage web UI)
