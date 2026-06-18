# xlab-mgmt — Lab Control Plane

This namespace is the management endpoint for the Nutanix homelab, designed to remain available when the lab itself is powered down or rebuilding.

## What lives here

| Resource | Purpose |
|---|---|
| PowerDNS Authoritative | Serves `lab.xrs444.net` at `172.21.0.53:53` |
| `powerdns-api` ClusterIP | REST API at port 8081 — writable by Windmill/IaC |
| Longhorn PVC | SQLite database for zone data |
| `f/lab/` in Windmill | Scripts for lab power-up/down (Prism API + IPMI) |

## Network layout

| VLAN | Name | Subnet | Contents |
|---|---|---|---|
| 2001 | LabPhysical | 172.25.1.0/24 | xntnx1/2/3 hosts, CVMs, AHV |
| 2002 | LabVirtual | 172.25.2.0/24 | VMs running on Nutanix |

## DNS

Zone: `lab.xrs444.net.`
Nameserver: `172.21.0.53` (Cilium LoadBalancer IP from the `172.21.0.0/24` pool)

**Configure lab clients to use `172.21.0.53` as their DNS server.**
The zone seed (`configmap-zone-seed.yaml`) documents the initial records.
After first deploy the zone is live in SQLite — use the API to make changes.

## PowerDNS API

Base URL (in-cluster only): `http://powerdns-api.xlab-mgmt.svc.cluster.local:8081`
Auth header: `X-API-Key: <value from powerdns-api-key Secret>`

```bash
# Get the key from the cluster
KEY=$(kubectl -n xlab-mgmt get secret powerdns-api-key -o jsonpath='{.data.api-key}' | base64 -d)

# List zones
curl -H "X-API-Key: $KEY" http://powerdns-api.xlab-mgmt.svc.cluster.local:8081/api/v1/servers/localhost/zones

# Add a record (replace or create rrset)
curl -s -X PATCH \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  http://powerdns-api.xlab-mgmt.svc.cluster.local:8081/api/v1/servers/localhost/zones/lab.xrs444.net. \
  -d '{"rrsets":[{"name":"myvm.lab.xrs444.net.","type":"A","ttl":3600,"changetype":"REPLACE","records":[{"content":"172.25.2.50","disabled":false}]}]}'

# Delete a record
curl -s -X PATCH \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  http://powerdns-api.xlab-mgmt.svc.cluster.local:8081/api/v1/servers/localhost/zones/lab.xrs444.net. \
  -d '{"rrsets":[{"name":"myvm.lab.xrs444.net.","type":"A","changetype":"DELETE"}]}'
```

Run these from inside the cluster (e.g. `kubectl run -it --rm curl --image=curlimages/curl`), or from a Windmill job that targets the ClusterIP.

## Windmill

Scripts for lab management live at `f/lab/` in the Windmill workspace (`windmill.xrs444.net`).

Resources:
- `u/admin/lab_powerdns_api` — PowerDNS API URL + key (from the `powerdns-api-key` Secret)
- `u/admin/lab_nutanix_prism` — Prism Central creds (from `lab-nutanix-prism` Secret)
- `u/admin/lab_ipmi_xntnx{1,2,3}` — BMC creds (from `lab-ipmi` Secret)

## Sealed secrets

To seal a new or updated secret, generate the key and run:
```bash
kubeseal --controller-namespace sealed-secrets --controller-name sealed-secrets
```
See the comments in each `sealedsecret-*.yaml` file for the exact commands.
