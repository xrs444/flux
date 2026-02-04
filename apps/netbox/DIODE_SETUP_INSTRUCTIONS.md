# Diode Setup Instructions

## Step 1: Create NetBox API Token

After your NetBox deployment is updated, you need to create an API token for Diode:

1. Log into NetBox at your configured URL
2. Go to your user profile (top right) → API Tokens
3. Click "Add API Token"
4. Set:
   - **Description**: `Diode Server`
   - **Write enabled**: ✓ (checked)
   - **Allowed IPs**: Leave empty (optional: restrict to pod network)
5. Copy the generated token

## Step 2: Create and Seal the Secret

Create a temporary secret file with your token:

```bash
# Create a temporary secret file
cat > /tmp/netbox-secret-temp.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: netbox-secret
  namespace: netbox
type: Opaque
stringData:
  SECRET_KEY: "<your-existing-secret-key>"
  DB_PASSWORD: "<your-existing-db-password>"
  REDIS_PASSWORD: "<your-existing-redis-password>"
  DIODE_API_TOKEN: "<paste-your-netbox-api-token-here>"
EOF

# Seal the secret
kubeseal --format=yaml --cert=<path-to-sealed-secrets-cert> \
  < /tmp/netbox-secret-temp.yaml \
  > /tmp/netbox-secret-sealed.yaml

# Copy the encryptedData section to sealedsecret-netbox.yaml
# Then delete the temporary files
rm /tmp/netbox-secret-temp.yaml /tmp/netbox-secret-sealed.yaml
```

## Step 3: Update the Sealed Secret

Copy the `encryptedData.DIODE_API_TOKEN` field from the sealed secret into `flux/apps/netbox/sealedsecret-netbox.yaml`.

## Step 4: Apply the Changes

```bash
# From your flux repository
git add flux/apps/netbox/
git commit -m "Add Diode Server for network discovery"
git push

# Flux will automatically reconcile the changes
# Or force reconciliation:
flux reconcile kustomization flux-system --with-source
```

## Step 5: Verify Diode is Running

```bash
# Check pod status
kubectl get pods -n netbox

# Check Diode logs
kubectl logs -n netbox deployment/netbox -c diode-server

# Verify Diode is listening
kubectl exec -n netbox deployment/netbox -c diode-server -- nc -zv localhost 8081
```

## Using Diode for Network Discovery

### Option A: Use diode-agent for automated discovery

Deploy the diode-agent as a DaemonSet or standalone deployment that runs network discovery tools (LLDP, SNMP, etc.) and pushes to Diode Server.

### Option B: Manual ingestion via diode CLI

Install the diode CLI locally and push data:

```bash
# Install diode CLI
# See: https://github.com/netboxlabs/diode

# Configure diode to point to your Diode Server
diode config set target grpc://netbox.your-domain.net:8081

# Ingest data
diode ingest device --name "switch-01" --device-type "cisco-switch" ...
```

## Next Steps

1. **Set up network discovery**: Configure LLDP/CDP discovery scripts or use existing network monitoring tools
2. **Create ingestion pipelines**: Write scripts to discover devices and push via Diode
3. **Automate discovery**: Set up cron jobs or Kubernetes CronJobs to periodically discover and sync devices

## Troubleshooting

**Diode can't connect to NetBox:**
- Check that both containers can communicate via localhost
- Verify the API token has write permissions
- Check Diode logs for connection errors

**Ingestion fails:**
- Verify Diode Server is exposed externally (via Service/Ingress)
- Check that the gRPC port (8081) is accessible
- Review Diode logs for detailed error messages

## Resources

- [Diode Documentation](https://netboxlabs.com/docs/diode/)
- [Diode GitHub](https://github.com/netboxlabs/diode)
- [NetBox API Documentation](https://demo.netbox.dev/api/docs/)
