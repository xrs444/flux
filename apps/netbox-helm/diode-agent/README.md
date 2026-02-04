# Diode Discovery Agent

Automated network discovery agent that scans your infrastructure and pushes device information to NetBox via Diode Server.

## Features

- **Kubernetes Discovery**: Automatically discovers K8s nodes and adds them to NetBox
- **Network Scanning**: Uses nmap to discover active hosts on specified network ranges
- **SNMP Discovery**: Queries devices via SNMP for detailed inventory information
- **LLDP/CDP Support**: Can discover network topology (requires SSH access)
- **Scheduled Execution**: Runs as a CronJob for regular discovery updates

## Architecture

```
┌─────────────────────────────────────┐
│   Diode Discovery Agent (CronJob)  │
│  ┌───────────────────────────────┐ │
│  │ Kubernetes Discovery          │ │
│  │ Network Scanner (nmap)        │ │
│  │ SNMP Query Engine             │ │
│  │ LLDP/CDP Parser               │ │
│  └───────────────┬───────────────┘ │
└──────────────────┼─────────────────┘
                   │ gRPC
                   ▼
       ┌──────────────────────┐
       │   Diode Server       │
       │  (NetBox sidecar)    │
       └──────────┬───────────┘
                  │ REST API
                  ▼
         ┌────────────────┐
         │    NetBox      │
         └────────────────┘
```

## Setup

### 1. Build and Push the Container Image

```bash
cd flux/apps/netbox/diode-agent

# Build the image
docker build -t your-registry.example.com/diode-discovery-agent:latest .

# Push to your container registry
docker push your-registry.example.com/diode-discovery-agent:latest
```

### 2. Configure Discovery Settings

Edit [configmap-diode-agent.yaml](configmap-diode-agent.yaml):

- **NETWORK_SCAN_RANGES**: Set your network CIDR ranges (comma-separated)
- **DEFAULT_SITE**: NetBox site name for discovered devices
- **DEFAULT_DEVICE_ROLE**: Default role for discovered devices
- **DISCOVERY_ENABLED_METHODS**: Enable/disable discovery methods

### 3. Configure Credentials

Create sealed secrets for SNMP and SSH credentials:

```bash
# Create temporary secret
kubectl create secret generic diode-agent-secret \
  --namespace=diode-agent \
  --from-literal=SNMP_COMMUNITY="your-community-string" \
  --from-literal=SSH_USERNAME="admin" \
  --from-literal=SSH_PASSWORD="your-password" \
  --dry-run=client -o yaml > /tmp/diode-agent-secret.yaml

# Seal the secret
kubeseal --format=yaml --cert=<your-cert> \
  < /tmp/diode-agent-secret.yaml \
  > sealedsecret-diode-agent.yaml

# Clean up
rm /tmp/diode-agent-secret.yaml
```

### 4. Update CronJob Image

Edit [cronjob-discovery.yaml](cronjob-discovery.yaml) line 26 to use your container image:

```yaml
image: your-registry.example.com/diode-discovery-agent:latest
```

### 5. Adjust Schedule (Optional)

Default schedule is hourly. Edit the `schedule` field in [cronjob-discovery.yaml](cronjob-discovery.yaml):

```yaml
# Examples:
schedule: "0 * * * *"      # Every hour
schedule: "*/30 * * * *"   # Every 30 minutes
schedule: "0 0 * * *"      # Daily at midnight
schedule: "0 */6 * * *"    # Every 6 hours
```

### 6. Deploy

Add to your Flux kustomization:

```bash
# If not already present in flux/apps/kustomization.yaml
# Add: - netbox/diode-agent

# Commit and push
git add flux/apps/netbox/diode-agent/
git commit -m "Add Diode discovery agent"
git push

# Force reconciliation (optional)
flux reconcile kustomization flux-system --with-source
```

## Usage

### Manual Run

Trigger a discovery job manually:

```bash
kubectl create job --from=cronjob/diode-discovery-agent -n diode-agent manual-discovery-$(date +%s)
```

### View Logs

```bash
# List jobs
kubectl get jobs -n diode-agent

# View logs from latest job
kubectl logs -n diode-agent -l app=diode-discovery-agent --tail=100

# Follow logs in real-time
kubectl logs -n diode-agent -l app=diode-discovery-agent -f
```

### Check Job Status

```bash
# View CronJob status
kubectl get cronjob -n diode-agent

# View recent jobs
kubectl get jobs -n diode-agent --sort-by=.metadata.creationTimestamp
```

## Discovery Methods

### Kubernetes Discovery

Automatically enabled when running in-cluster. Discovers:
- All Kubernetes nodes
- Node IP addresses
- Node roles (master/worker)
- System information (OS, kernel, container runtime)

**Requirements:**
- ServiceAccount with cluster read permissions (already configured)

### Network Scanning (nmap)

Scans specified CIDR ranges for active hosts.

**Configuration:**
```yaml
NETWORK_SCAN_RANGES: "192.168.1.0/24,10.0.0.0/24"
```

**Discovers:**
- Active IP addresses
- Hostnames (via reverse DNS)

**Requirements:**
- NET_RAW capability (already configured)
- Network access to target ranges

### SNMP Discovery

Queries devices via SNMP for detailed information.

**Configuration:**
```yaml
SNMP_COMMUNITY: "public"  # In secret
SNMP_VERSION: "2c"
```

**Discovers:**
- Device hostname
- System description
- Serial numbers
- Location and contact info
- Device type (via sysDescr matching)

**Requirements:**
- SNMP enabled on target devices
- Valid community string or SNMPv3 credentials

### LLDP/CDP Discovery

Discovers network topology via LLDP/CDP protocols.

**Configuration:**
```yaml
LLDP_ENABLED: "true"
SSH_USERNAME: "admin"  # In secret
SSH_PASSWORD: "..."    # In secret
```

**Discovers:**
- Neighbor relationships
- Port connections
- Network topology

**Requirements:**
- SSH access to network devices
- LLDP/CDP enabled on switches

## Troubleshooting

### No Devices Discovered

1. Check logs: `kubectl logs -n diode-agent -l app=diode-discovery-agent --tail=100`
2. Verify network connectivity to target ranges
3. Check SNMP credentials and community strings
4. Ensure network ranges are correctly configured

### Permission Errors

The agent needs:
- `NET_RAW` capability for nmap scanning
- ServiceAccount with K8s read permissions
- Network access to target devices

### SNMP Timeouts

Increase timeout settings in [configmap-diode-agent.yaml](configmap-diode-agent.yaml):

```yaml
SNMP_TIMEOUT: "10"
SNMP_RETRIES: "3"
```

### CronJob Not Running

```bash
# Check CronJob status
kubectl describe cronjob diode-discovery-agent -n diode-agent

# Check for suspended jobs
kubectl get cronjob diode-discovery-agent -n diode-agent -o yaml | grep suspend
```

### Devices Not Appearing in NetBox

1. Verify Diode Server is running: `kubectl logs -n netbox deployment/netbox -c diode-server`
2. Check NetBox has required device types and sites configured
3. Verify API token has write permissions
4. Review device data in agent logs for validation errors

## Customization

### Adding Custom Discovery Methods

Edit [discovery-script.py](discovery-script.py) to add new discovery methods:

```python
# Add your custom discovery class
class CustomDiscovery:
    def discover(self) -> List[Dict[str, Any]]:
        # Your discovery logic
        return devices

# Add to main() function
if 'custom' in enabled_methods:
    custom = CustomDiscovery()
    devices = custom.discover()
    all_devices.extend(devices)
```

### Device Type Mapping

Edit `_map_device_type()` in [discovery-script.py](discovery-script.py) to customize device type detection:

```python
def _map_device_type(self, sys_descr: str) -> str:
    if 'your-vendor' in sys_descr.lower():
        return 'your-device-type'
    # ...
```

### Custom Tags and Fields

Modify device dictionaries in discovery methods to add custom tags or fields:

```python
device = {
    'name': hostname,
    'tags': ['auto-discovered', 'custom-tag'],
    'custom_fields': {
        'discovered_by': 'diode-agent',
        'last_seen': datetime.utcnow().isoformat(),
    }
}
```

## Advanced Configuration

### Multiple Site Discovery

Deploy multiple CronJobs with different configurations for different sites:

```bash
cp cronjob-discovery.yaml cronjob-discovery-site2.yaml
# Edit site-specific settings
# Deploy both
```

### Filtering Discovered Devices

Add filtering logic to discovery methods to exclude certain devices:

```python
# In discovery method
if self._should_exclude(device):
    continue
```

### Integration with Existing Monitoring

Export discovery data to other systems by modifying the `DiodeClient`:

```python
def ingest_device(self, device_data: Dict[str, Any]) -> bool:
    # Send to Diode
    self._send_to_diode(device_data)
    # Also send to monitoring system
    self._send_to_prometheus(device_data)
```

## Resources

- [NetBox Labs Diode Documentation](https://netboxlabs.com/docs/diode/)
- [NetBox Device API](https://demo.netbox.dev/api/docs/)
- [nmap Network Scanning](https://nmap.org/)
- [PySNMP Documentation](https://pysnmp.readthedocs.io/)

## Security Considerations

- **Credentials**: Always use sealed secrets for SNMP community strings and SSH passwords
- **Network Access**: Limit agent network access using NetworkPolicies
- **Least Privilege**: Agent runs as non-root with minimal capabilities
- **API Tokens**: Use dedicated NetBox API tokens with minimal required permissions
- **Log Sensitivity**: Logs may contain discovered IP addresses and hostnames

## Support

For issues or questions:
1. Check agent logs for error messages
2. Verify configuration in ConfigMap and Secret
3. Test connectivity manually from a pod in the same namespace
4. Review NetBox and Diode logs for ingestion errors
