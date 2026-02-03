# Immich, ROMM, and RustDesk Deployment Guide

This guide covers the deployment of three new applications to the HomeProd Kubernetes cluster:

1. **Immich** - Photo and video management platform with AI-powered features
2. **ROMM** - ROM collection manager for retro gaming
3. **RustDesk** - Open-source remote desktop solution

All applications are configured with Kanidm OIDC authentication (where applicable), NFS storage for media, and integrated with Prometheus/Apprise for monitoring and alerting.

## Architecture Overview

### Immich
- **Components**: Server, Microservices, Machine Learning, PostgreSQL, Redis
- **Storage**:
  - NFS: `/zfs/documents/photos` → 10Ti (library storage)
  - Longhorn: 50Gi (upload buffer), 20Gi (database)
- **Authentication**: Kanidm OIDC via `oauth2_immich` client
- **Endpoints**:
  - Web UI: `https://immich.xrs444.net`
  - API: `https://immich.xrs444.net/api`

### ROMM
- **Components**: ROMM web server, MariaDB database
- **Storage**:
  - NFS: `/zfs/media/games` → 5Ti (ROM library)
  - Longhorn: 10Gi (resources/metadata), 5Gi (config), 5Gi (database)
- **Authentication**: Kanidm OIDC via `oauth2_romm` client
- **Endpoints**: `https://romm.xrs444.net`

### RustDesk
- **Components**: hbbs (relay server), hbbr (rendezvous server)
- **Storage**: Longhorn 5Gi (shared data volume)
- **Authentication**: None (uses public key authentication)
- **Endpoints**:
  - Web UI: `https://rustdesk.xrs444.net`
  - Relay Server (hbbs): LoadBalancer ports 21115-21118
  - Rendezvous Server (hbbr): LoadBalancer ports 21117, 21119

## Pre-Deployment Steps

### 1. Create OAuth2 Client Secret Files

The OAuth2 clients and groups are already defined in the Kanidm provisioning configuration (`nix/modules/services/kanidm/provision.nix`). You need to create the secret files that will be used by the provisioning system:

```bash
# SSH to the Kanidm server
ssh xsvr1

# Generate random secrets for OAuth2 clients
IMMICH_SECRET=$(openssl rand -base64 32)
ROMM_SECRET=$(openssl rand -base64 32)

# Create the secret files
echo -n "$IMMICH_SECRET" | sudo tee /run/secrets/kanidm_oauth2_immich_secret > /dev/null
echo -n "$ROMM_SECRET" | sudo tee /run/secrets/kanidm_oauth2_romm_secret > /dev/null

# Set proper permissions
sudo chmod 600 /run/secrets/kanidm_oauth2_immich_secret
sudo chmod 600 /run/secrets/kanidm_oauth2_romm_secret
sudo chown kanidm:kanidm /run/secrets/kanidm_oauth2_immich_secret
sudo chown kanidm:kanidm /run/secrets/kanidm_oauth2_romm_secret

# Save the secrets for the Kubernetes sealed secrets step
echo "Immich OAuth2 Secret: $IMMICH_SECRET"
echo "ROMM OAuth2 Secret: $ROMM_SECRET"

# Note: You may want to add these to your secrets management system
```

### 2. Deploy Kanidm Configuration

Apply the updated Kanidm provisioning configuration:

```bash
# From your local machine, deploy the updated NixOS configuration
cd /Users/xrs444/Repositories/HomeProd

# Add and commit the Kanidm provision changes
git add nix/modules/services/kanidm/provision.nix
git commit -m "Add Immich and ROMM OAuth2 clients to Kanidm provisioning"
git push

# Deploy to xsvr1
nixos-rebuild switch --flake .#xsvr1 --target-host xsvr1 --use-remote-sudo
```

After the rebuild, the OAuth2 clients (`oauth2_immich`, `oauth2_romm`) and groups (`immich`, `immich-admin`, `romm`, `romm-admin`) will be automatically created in Kanidm.

### 3. Create Sealed Secrets

Create sealed secrets for OAuth2 credentials and database passwords:

#### Immich OAuth2 Secret

```bash
# Use the secret generated in step 1
kubectl create secret generic immich-oauth2 \
  --from-literal=client-secret='<IMMICH_SECRET_FROM_STEP_1>' \
  --namespace immich --dry-run=client -o yaml | \
kubeseal --controller-name=sealed-secrets \
  --controller-namespace=kube-system -o yaml > \
  flux/apps/immich/sealedsecret-immich-oauth2.yaml
```

#### Immich Database Secret

```bash
# Generate a random password
IMMICH_DB_PASSWORD=$(openssl rand -base64 32)

kubectl create secret generic immich-db \
  --from-literal=password="$IMMICH_DB_PASSWORD" \
  --namespace immich --dry-run=client -o yaml | \
kubeseal --controller-name=sealed-secrets \
  --controller-namespace=kube-system -o yaml > \
  flux/apps/immich/sealedsecret-immich-db.yaml
```

#### ROMM OAuth2 Secret

```bash
# Use the secret generated in step 1
kubectl create secret generic romm-oauth2 \
  --from-literal=client-secret='<ROMM_SECRET_FROM_STEP_1>' \
  --namespace romm --dry-run=client -o yaml | \
kubeseal --controller-name=sealed-secrets \
  --controller-namespace=kube-system -o yaml > \
  flux/apps/romm/sealedsecret-romm-oauth2.yaml
```

#### ROMM Database Secret

```bash
# Generate random passwords
ROMM_DB_PASSWORD=$(openssl rand -base64 32)
ROMM_DB_ROOT_PASSWORD=$(openssl rand -base64 32)

kubectl create secret generic romm-db \
  --from-literal=password="$ROMM_DB_PASSWORD" \
  --from-literal=root-password="$ROMM_DB_ROOT_PASSWORD" \
  --namespace romm --dry-run=client -o yaml | \
kubeseal --controller-name=sealed-secrets \
  --controller-namespace=kube-system -o yaml > \
  flux/apps/romm/sealedsecret-romm-db.yaml
```

### 4. Verify NFS Storage

Ensure the NFS paths exist and are accessible:

```bash
# SSH to NFS server
ssh xsvr1  # or xsvr2, depending on your setup

# Verify/create directories
sudo mkdir -p /zfs/documents/photos
sudo mkdir -p /zfs/media/games

# Set appropriate permissions
sudo chown -R 1000:1000 /zfs/documents/photos
sudo chown -R 1000:1000 /zfs/media/games

# Verify NFS exports
sudo exportfs -v | grep -E '(photos|games)'
```

### 5. Update DNS Records

Add DNS records for the new services (if not using wildcard DNS):

```
immich.xrs444.net    → <traefik-loadbalancer-ip>
romm.xrs444.net      → <traefik-loadbalancer-ip>
rustdesk.xrs444.net  → <traefik-loadbalancer-ip>
```

## Deployment

### Option 1: Automatic Deployment (Recommended)

Flux will automatically deploy the applications once you commit the manifests:

```bash
cd /Users/xrs444/Repositories/HomeProd

# Stage all new files
git add flux/apps/immich/
git add flux/apps/romm/
git add flux/apps/rustdesk/
git add flux/apps/kustomization.yaml

# Commit
git commit -m "Add Immich, ROMM, and RustDesk deployments

- Immich: Photo/video management with Kanidm OIDC, NFS storage at /zfs/documents/photos
- ROMM: ROM collection manager with Kanidm OIDC, NFS storage at /zfs/media/games
- RustDesk: Remote desktop solution with LoadBalancer services

All applications configured with:
- Kanidm authentication (Immich, ROMM)
- NFS storage for media files
- Longhorn storage for databases and configs
- Prometheus monitoring integration
- Apprise alerting ready"

# Push to trigger Flux reconciliation
git push
```

### Option 2: Manual Deployment (Testing)

For testing before committing:

```bash
# Deploy Immich
kubectl apply -k flux/apps/immich/

# Deploy ROMM
kubectl apply -k flux/apps/romm/

# Deploy RustDesk
kubectl apply -k flux/apps/rustdesk/
```

## Post-Deployment Verification

### Check Pod Status

```bash
# Immich
kubectl get pods -n immich
kubectl logs -n immich -l app=immich-server

# ROMM
kubectl get pods -n romm
kubectl logs -n romm -l app=romm

# RustDesk
kubectl get pods -n rustdesk
kubectl logs -n rustdesk -l app=rustdesk-hbbs
```

### Verify Services

```bash
# Check LoadBalancer IPs
kubectl get svc -n immich
kubectl get svc -n romm
kubectl get svc -n rustdesk

# Check IngressRoutes
kubectl get ingressroute -n immich
kubectl get ingressroute -n romm
kubectl get ingressroute -n rustdesk
```

### Test Web Access

```bash
# Test endpoints
curl -I https://immich.xrs444.net
curl -I https://romm.xrs444.net
curl -I https://rustdesk.xrs444.net

# Or open in browser:
# https://immich.xrs444.net
# https://romm.xrs444.net
# https://rustdesk.xrs444.net
```

### Verify OIDC Authentication

1. Navigate to `https://immich.xrs444.net`
2. Click "Login with Kanidm" button
3. Should redirect to Kanidm login page
4. After authentication, should return to Immich
5. Repeat for ROMM at `https://romm.xrs444.net`

### Check Storage Mounts

```bash
# Verify NFS mounts in Immich
kubectl exec -n immich -it deployment/immich-server -- df -h | grep /usr/src/app/upload/library

# Verify NFS mounts in ROMM
kubectl exec -n romm -it deployment/romm -- df -h | grep /romm/library

# Check PVC status
kubectl get pvc -n immich
kubectl get pvc -n romm
kubectl get pvc -n rustdesk
```

## RustDesk Client Configuration

To connect RustDesk clients to your self-hosted server:

### Get the Public Key

```bash
# Extract the public key from the hbbs server
kubectl exec -n rustdesk deployment/rustdesk-hbbs -- cat /data/id_ed25519.pub
```

### Configure RustDesk Client

1. Open RustDesk client
2. Click the three dots menu → Settings → Network
3. Set:
   - **ID Server**: `rustdesk.xrs444.net`
   - **Relay Server**: `rustdesk.xrs444.net`
   - **API Server**: `https://rustdesk.xrs444.net`
   - **Key**: `<paste-public-key-from-above>`
4. Click "Apply"

## Monitoring and Alerting

### Prometheus Metrics

The external Prometheus instance on xsvr1 will automatically scrape metrics from:

- Kubelet (pod CPU/memory metrics)
- kube-state-metrics (deployment/pod states)
- Individual application metrics endpoints (if exposed)

No additional configuration is needed as the apps are part of the Kubernetes cluster.

### Apprise Alerts

To configure custom alerts for these applications, edit the Prometheus rules on xsvr1:

```bash
ssh xsvr1
sudo vim /etc/nixos/modules/services/monitoring/prometheus.nix
```

Example alert for Immich:

```nix
{
  alert = "ImmichServerDown";
  expr = ''kube_deployment_status_replicas_available{deployment="immich-server",namespace="immich"} == 0'';
  for = "5m";
  labels.severity = "critical";
  annotations = {
    summary = "Immich server is down";
    description = "Immich server has been unavailable for 5 minutes.";
  };
}
```

After editing, rebuild xsvr1:

```bash
sudo nixos-rebuild switch --flake .#xsvr1
```

### Grafana Dashboards

Create custom dashboards in Grafana (http://xsvr1:3000) to visualize:

- Immich photo processing queue length
- ROMM ROM scanning progress
- RustDesk active connections
- Pod resource usage (CPU/memory)
- Database query performance

## Troubleshooting

### Immich Issues

#### Database Connection Errors

```bash
# Check PostgreSQL pod
kubectl get pods -n immich -l app=immich-postgres
kubectl logs -n immich -l app=immich-postgres

# Test database connectivity
kubectl exec -n immich deployment/immich-server -- \
  pg_isready -h immich-postgres -p 5432 -U immich
```

#### OIDC Authentication Not Working

```bash
# Check OAuth2 environment variables
kubectl exec -n immich deployment/immich-server -- env | grep OAUTH

# Verify secret is properly created
kubectl get secret -n immich immich-oauth2 -o yaml

# Check Kanidm client configuration
ssh xsvr1
kanidm system oauth2 get oauth2_immich
```

#### Machine Learning Pod OOMKilled

The ML pod may need more memory for larger photo libraries:

```bash
# Edit deployment to increase memory limit
kubectl edit deployment -n immich immich-machine-learning

# Change limits.memory from 8Gi to 16Gi
```

### ROMM Issues

#### ROM Scanning Not Working

```bash
# Check logs
kubectl logs -n romm -l app=romm

# Verify NFS mount and permissions
kubectl exec -n romm deployment/romm -- ls -la /romm/library

# Check if games directory is accessible from NFS server
ssh xsvr1
ls -la /zfs/media/games
```

#### MariaDB Connection Errors

```bash
# Check MariaDB pod
kubectl get pods -n romm -l app=romm-mariadb
kubectl logs -n romm -l app=romm-mariadb

# Verify database exists
kubectl exec -n romm deployment/romm-mariadb -- \
  mysql -u romm -p"$(kubectl get secret -n romm romm-db -o jsonpath='{.data.password}' | base64 -d)" \
  -e "SHOW DATABASES;"
```

### RustDesk Issues

#### Clients Can't Connect

```bash
# Check if LoadBalancer IPs are assigned
kubectl get svc -n rustdesk

# Verify hbbs and hbbr pods are running
kubectl get pods -n rustdesk

# Check logs
kubectl logs -n rustdesk -l app=rustdesk-hbbs
kubectl logs -n rustdesk -l app=rustdesk-hbbr

# Ensure ports are accessible (from external client)
nc -zv rustdesk.xrs444.net 21115
nc -zv rustdesk.xrs444.net 21116
nc -zv rustdesk.xrs444.net 21117
```

#### Public Key Mismatch

If clients show "Key mismatch" error:

```bash
# Get the current public key
kubectl exec -n rustdesk deployment/rustdesk-hbbs -- cat /data/id_ed25519.pub

# Delete old keys if needed (will regenerate on restart)
kubectl exec -n rustdesk deployment/rustdesk-hbbs -- rm /data/id_ed25519 /data/id_ed25519.pub
kubectl rollout restart deployment -n rustdesk rustdesk-hbbs
kubectl rollout restart deployment -n rustdesk rustdesk-hbbr

# Get new public key and reconfigure clients
kubectl exec -n rustdesk deployment/rustdesk-hbbs -- cat /data/id_ed25519.pub
```

### General Kubernetes Issues

```bash
# Check Flux reconciliation status
kubectl get kustomization -n flux-system

# Force Flux to reconcile
flux reconcile kustomization apps --with-source

# Check PVC binding
kubectl get pvc -A | grep -E '(immich|romm|rustdesk)'

# Check PV status
kubectl get pv | grep -E '(immich|romm|rustdesk)'

# View events for a namespace
kubectl get events -n immich --sort-by='.lastTimestamp'
kubectl get events -n romm --sort-by='.lastTimestamp'
kubectl get events -n rustdesk --sort-by='.lastTimestamp'
```

## Maintenance

### Updating Applications

Flux will automatically update applications when you change the image tags in the deployment manifests. To update manually:

```bash
# Update Immich
kubectl set image deployment/immich-server -n immich \
  immich-server=ghcr.io/immich-app/immich-server:v1.XX.X

# Update ROMM
kubectl set image deployment/romm -n romm \
  romm=rommapp/romm:vX.X.X

# Update RustDesk
kubectl set image deployment/rustdesk-hbbs -n rustdesk \
  hbbs=rustdesk/rustdesk-server:X.X.X
kubectl set image deployment/rustdesk-hbbr -n rustdesk \
  hbbr=rustdesk/rustdesk-server:X.X.X
```

### Backup Considerations

#### Immich Backups

Important data to backup:
- PostgreSQL database: `immich-db` PVC
- Upload directory: `immich-upload` PVC
- Photo library: NFS `/zfs/documents/photos` (backed up via ZFS snapshots)

```bash
# Backup database using pg_dump
kubectl exec -n immich deployment/immich-postgres -- \
  pg_dump -U immich immich | gzip > immich-backup-$(date +%Y%m%d).sql.gz
```

#### ROMM Backups

Important data to backup:
- MariaDB database: `romm-db` PVC
- Configuration: `romm-config` PVC
- ROM library: NFS `/zfs/media/games` (backed up via ZFS snapshots)

```bash
# Backup database using mysqldump
kubectl exec -n romm deployment/romm-mariadb -- \
  mysqldump -u romm -p"$(kubectl get secret -n romm romm-db -o jsonpath='{.data.password}' | base64 -d)" \
  romm | gzip > romm-backup-$(date +%Y%m%d).sql.gz
```

#### RustDesk Backups

Important data to backup:
- Keys and configuration: `rustdesk-data` PVC

```bash
# Backup keys
kubectl exec -n rustdesk deployment/rustdesk-hbbs -- tar czf - /data | \
  cat > rustdesk-backup-$(date +%Y%m%d).tar.gz
```

### Scaling

Immich components can be scaled horizontally:

```bash
# Scale microservices for better performance
kubectl scale deployment -n immich immich-microservices --replicas=2

# Scale machine learning (requires sufficient cluster resources)
kubectl scale deployment -n immich immich-machine-learning --replicas=2
```

## Security Considerations

1. **OIDC Secrets**: OAuth2 client secrets are encrypted with Sealed Secrets and only decryptable by the cluster
2. **Database Passwords**: Auto-generated random passwords stored as Sealed Secrets
3. **TLS/HTTPS**: All web interfaces use Let's Encrypt certificates via Traefik
4. **Network Policies**: Consider adding NetworkPolicy resources to restrict pod-to-pod communication
5. **RustDesk**: Uses public key authentication; keep the private key (`id_ed25519`) secure

## References

- [Immich Documentation](https://immich.app/docs)
- [ROMM Documentation](https://github.com/rommapp/romm)
- [RustDesk Documentation](https://rustdesk.com/docs/)
- [Kanidm OIDC Integration Guide](kanidm-oidc-integration.md)
- [Monitoring Setup Guide](MONITORING_SETUP.md)
- [Apprise Setup Guide](APPRISE_SETUP.md)

## Next Steps

1. Configure user permissions in Kanidm groups
2. Import existing photos into Immich
3. Organize ROM collection in `/zfs/media/games` for ROMM scanning
4. Set up RustDesk clients on workstations
5. Create Grafana dashboards for application monitoring
6. Configure backup automation for databases
7. Set up retention policies for Immich photos
8. Create alert rules for application-specific metrics
