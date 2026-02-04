# Diode Discovery Agent - Quick Start

Get network discovery running in 5 steps!

## Prerequisites

- NetBox with Diode Server deployed (already done ✓)
- Docker installed for building the container
- Access to a container registry
- `kubeseal` installed for creating sealed secrets

## Step 1: Build and Push Container

```bash
cd flux/apps/netbox/diode-agent

# Set your registry
export CONTAINER_REGISTRY="your-registry.example.com"

# Build
./build.sh

# Push
docker push ${CONTAINER_REGISTRY}/diode-discovery-agent:latest
```

## Step 2: Update CronJob Image

Edit `cronjob-discovery.yaml` line 26:

```yaml
image: your-registry.example.com/diode-discovery-agent:latest
```

## Step 3: Configure Network Ranges

Edit `configmap-diode-agent.yaml` to set your network ranges:

```yaml
# Replace with your actual network ranges
NETWORK_SCAN_RANGES: "192.168.1.0/24,10.0.0.0/24"

# Set your site name (must exist in NetBox)
DEFAULT_SITE: "homelab"
```

## Step 4: Create Sealed Secrets

```bash
# Create temporary secret with your credentials
kubectl create secret generic diode-agent-secret \
  --namespace=diode-agent \
  --from-literal=SNMP_COMMUNITY="public" \
  --from-literal=SSH_USERNAME="admin" \
  --from-literal=SSH_PASSWORD="" \
  --dry-run=client -o yaml > /tmp/diode-agent-secret.yaml

# Seal it (replace with your sealed-secrets cert path)
kubeseal --format=yaml --cert=<path-to-cert> \
  < /tmp/diode-agent-secret.yaml \
  > sealedsecret-diode-agent.yaml

# Clean up
rm /tmp/diode-agent-secret.yaml
```

## Step 5: Deploy

```bash
# Add to Flux (if not already included)
# Edit flux/apps/kustomization.yaml and add:
#   - netbox/diode-agent

# Or apply directly with kubectl
kubectl apply -k flux/apps/netbox/diode-agent/

# Commit and push
git add flux/apps/netbox/diode-agent/
git commit -m "Deploy Diode discovery agent"
git push
```

## Test It

Run a manual discovery:

```bash
# Trigger a job
kubectl create job --from=cronjob/diode-discovery-agent \
  -n diode-agent manual-discovery-$(date +%s)

# Watch the logs
kubectl logs -n diode-agent -l app=diode-discovery-agent -f
```

## Expected Output

You should see logs like:

```
2024-01-15 10:30:00 - INFO - Starting NetBox Diode Discovery Agent
2024-01-15 10:30:01 - INFO - Running Kubernetes discovery
2024-01-15 10:30:02 - INFO - Discovered K8s node: worker-01
2024-01-15 10:30:02 - INFO - Discovered K8s node: worker-02
2024-01-15 10:30:02 - INFO - Kubernetes discovery found 2 nodes
2024-01-15 10:30:03 - INFO - Running network scan
2024-01-15 10:30:15 - INFO - Discovered device: 192.168.1.1
2024-01-15 10:30:16 - INFO - Discovered device: 192.168.1.10
2024-01-15 10:30:25 - INFO - Network scan found 15 devices
2024-01-15 10:30:26 - INFO - Pushing 17 devices to Diode
2024-01-15 10:30:30 - INFO - Discovery complete. Successfully ingested 17/17 devices
```

## Troubleshooting

### "Permission denied" errors

The ServiceAccount needs cluster read permissions. Verify:

```bash
kubectl get clusterrolebinding diode-agent -o yaml
```

### "Cannot connect to Diode Server"

Check Diode Server is running:

```bash
kubectl get pods -n netbox
kubectl logs -n netbox deployment/netbox -c diode-server
```

### "No devices discovered"

- Verify network ranges are correct
- Check network connectivity from the pod
- Review logs for specific errors

### Image pull errors

```bash
# Verify image exists
docker images | grep diode-discovery

# Check image name in cronjob matches pushed image
kubectl get cronjob diode-discovery-agent -n diode-agent -o yaml | grep image:
```

## Next Steps

1. **Adjust Schedule**: Edit the CronJob schedule for your needs (default: hourly)
2. **Add SNMP**: Configure SNMP credentials for detailed device info
3. **Enable LLDP**: Add SSH credentials for topology discovery
4. **Create Sites in NetBox**: Ensure sites referenced in config exist
5. **Define Device Types**: Add device types that match discovered devices
6. **Review Data**: Check NetBox for discovered devices and validate data

## Need Help?

See the full [README.md](README.md) for detailed documentation, customization options, and troubleshooting.

## Important Notes

⚠️ **Before first run:**
- Ensure your NetBox API token is configured (see main DIODE_SETUP_INSTRUCTIONS.md)
- Create the "homelab" site in NetBox (or change DEFAULT_SITE)
- Verify network ranges are correct to avoid scanning unintended networks

🔒 **Security:**
- Never commit unsealed secrets
- Use least-privilege SNMP community strings
- Restrict network access using NetworkPolicies
- Review discovered data before trusting it

📊 **Monitoring:**
- Set up alerts for failed CronJobs
- Monitor Diode Server logs for ingestion errors
- Track discovery success rates over time
