# Network segmentation — Firewalla inter-VLAN zone matrix

Phase 2 of the network-segmentation project (see `.claude/plans/starting-with-this-let-s-piped-gem.md`
in the parent repo for the full multi-layer design; Phase 1, the in-cluster
CiliumNetworkPolicy rollout, is complete and covers 8 namespaces).

No write API exists for Firewalla rules (`mcp__mcp-gateway__firewalla__*`
exposes read/pause/resume only), and there is no rule IaC anywhere in this
repo. This document is the checked-in policy spec; applying it is a manual
step in the Firewalla app. **Nothing in this document has been applied yet.**

## Current state, confirmed live 2026-09-15

Firewalla box `xfw` (Gold Pro), 175 active rules total. Of those, only 13
target actual network ranges/intranet traffic — the other 162 are Advanced
Threat Filtering / category / domain / app rules (ad-block, malware
lookalike-domain lists, etc.), out of scope for this document.

**The dominant rule, by a wide margin, is a global allow:**

```text
allow  net 172.16.0.0/12  bidirection  (no scope)  — 100,804,391 hits
```

This single rule permits full bidirectional traffic between **every VLAN
in the network** (all of them fall inside 172.16.0.0/12 except the WiFi
SSIDs at 172.19.x, which are also inside that same /12). This is the
concrete confirmation of AUDIT-PLAN's F3 finding and the reason this
document exists — there is currently no inter-VLAN segmentation at all.

Other network-scoped rules found:

| Rule | Purpose |
|---|---|
| `allow net 100.64.0.0/10` (bidirection, global) | Tailscale CGNAT range |
| `allow net 10.244.0.0/16` (bidirection, global) | k8s Pod CIDR — BGP announces PodCIDR onto the physical network |
| `allow net 172.21.0.0/24` (bidirection, global) | k8s LoadBalancer pool |
| `allow net 192.168.0.0/24` (bidirection, global) | Explains a device on this repo's VLAN scheme that doesn't fit — resolved live: a standalone RIPE Atlas probe at `192.168.6.142`, its own self-contained subnet, unrelated to any VLAN here |
| `allow intranet unknown` (bidirection, no scope, oldest rule — 2023) | Baseline "same-VLAN traffic is fine" allow |
| `block intranet unknown` outbound, `scope: network 5b32fb40-45ff-45ac-a56b-19ebe7dc1296` | **Unresolved** — this network ID has zero associated devices in current device tracking, so it can't be named from live data. Likely one of the two undocumented placeholder VLANs (11 or 18) in its pre-use state. Check the Firewalla app directly. |
| `block intranet unknown` outbound, `scope: network 60f3f58a-29eb-45f3-a7f5-38e17c90e7e6` | Same — unresolved, zero devices. |
| `block intranet unknown` bidirection, `scope: group 17` | Firewalla device-group 17 = **Quarantine**. Existing device-level containment, unrelated to VLAN design — leave as-is. |

So there is already *some* per-network outbound-intranet blocking
infrastructure in the box (two `network`-scoped rules), but it's
irrelevant in practice — the blanket `/12` allow has 100M+ hits and
nothing suggests the two scoped blocks are doing meaningful work (0 hits
on both). The real posture is default-allow-everywhere.

## VLAN inventory (corrected/expanded from live Firewalla device data)

Firewalla's own network names, cross-referenced against live device IPs —
this fills several gaps the original plan flagged as undocumented.

| Firewalla network name | Subnet | Matches repo VLAN | Notes |
|---|---|---|---|
| FW | 172.18.10.0/24 | 10 | Firewall transit / server-mgmt |
| Lab Connection | 172.18.11.0/24 | 11 | **Resolved** — was "empty placeholder" in the original plan; has 1 device (`172.18.11.249`) |
| Network Management | 172.18.4.0/24 | 14 | Switches, APs, IPMI |
| Printers | 172.18.5.0/24 | 15 | |
| Telephony | 172.18.6.0/24 | 16 | Asterisk/xpbx1, SIP phones |
| HomeAutomation | 172.18.7.0/24 | 17 | Home Assistant + IoT |
| Wired Clients | 172.18.100.0/24 | 100 | Desks/office switches |
| WanIPlayWithMadness | 172.19.112.0/24 | 112 | WiFi SSID |
| TotalEclipseOfTheUART | 172.19.114.0/24 | 114 | WiFi SSID |
| Home Physical Servers | 172.20.1.0/24 | 20 | xsvr1-4, Kanidm |
| Home VMs | 172.20.2.0/24 | 21 | KVM guests |
| k8s | 172.20.3.0/24 | 22 | Talos nodes |
| LabPhysical | 172.25.1.0/24 | (lab range) | Nutanix cluster |
| LabVirtual | 172.25.2.0/24 | (lab range) | Nutanix VMs |
| LabIPMI | 172.25.4.0/24 | (lab range) | iLOs |
| RiPE ATLAS | 192.168.6.0/24 (standalone) | — | Single probe device, not integrated into the VLAN scheme — explains the otherwise-mysterious `192.168.0.0/24` allow rule |

**Still unresolved, not found in live device data:** VLAN 18 (tagged-only
on the switch, no prefix ever documented), VLAN 1000 "Atlas" (the
switch's own untagged-port VLAN — a different thing from the RIPE Atlas
probe above, confusingly similar name), VLAN 111/115 (two more WiFi
SSIDs referenced in the switch config but with no devices currently
online to reveal their subnet), and the two empty-device network UUIDs
from the rules table above. None of these can be resolved further via
the Firewalla MCP tools available — check the Firewalla app's Network
list directly for names/subnets.

## Zone model

Four trust tiers, mapped onto the VLANs above:

- **Zone A — Infrastructure** (Network Management 172.18.4.0/24, FW
  172.18.10.0/24, Home Physical Servers 172.20.1.0/24, k8s 172.20.3.0/24,
  Home VMs 172.20.2.0/24): the stuff that runs everything else. Trusted
  to reach most things; most other zones should not be able to reach
  *into* it except on specific ports.
- **Zone B — Trusted clients** (Wired Clients 172.18.100.0/24, and
  whichever WiFi SSID is the trusted one — confirm which of
  112/114/111/115 that is before applying anything, the switch config
  doesn't label intent, only device names do): admin/family devices.
  Needs broad outbound reach, doesn't need broad inbound reach.
- **Zone C — Semi-trusted / IoT-adjacent** (HomeAutomation 172.18.7.0/24,
  Telephony 172.18.6.0/24, Printers 172.18.5.0/24): devices that need
  specific, narrow paths to specific infrastructure services, nothing
  more.
- **Zone D — Lab** (Lab Connection 172.18.11.0/24, LabPhysical
  172.25.1.0/24, LabVirtual 172.25.2.0/24, LabIPMI 172.25.4.0/24):
  experimental/non-production. Should not be trusted to reach production
  infrastructure by default.

## Concrete rules to add (specific, not the whole matrix)

These are the items the original plan already identified by name, now
with confirmed subnets to scope them:

1. **`xcog1` (172.20.1.x, LiteLLM :4000)** — currently open to every VLAN
   via the blanket `/12` allow, including a paid DeepSeek-tier proxy.
   Restrict inbound on :4000 to Zone A (specifically k8s 172.20.3.0/24)
   and HomeAutomation 172.18.7.0/24 (HA) only. Already designed in
   `nix/docs/xcog1-llm-deployment-plan.md:110-125`, never applied.
2. **`xcog1` Wyoming ports (10300/10200/10400)** — HomeAutomation
   172.18.7.0/24 only.
3. **NFS (`172.20.1.10:2049`, xsvr1)** — currently exported to all of
   172.20.0.0/16 plus the tailnet at the NFS layer itself; restrict at
   Firewalla to Zone A (172.20.1.0/24, 172.20.3.0/24) only. `no_root_squash`
   on several exports raises the stakes here.
4. **Exporter ports (9080/9100/9633/9134/9177/9324)** — restrict inbound
   to the Prometheus source only. Prometheus itself now runs in-cluster
   (`monitoring` namespace) and reaches these via k8s 172.20.3.0/24's
   egress, confirmed live in the Phase 1 flow capture
   (`monitoring -> 172.20.3.201/.202` on exactly these ports) — so the
   Firewalla-side rule is "allow 172.20.3.0/24 -> these ports," not a
   single host.
5. **VLAN 14 (Network Management, 172.18.4.0/24)** — admin/Zone-A access
   only; this is switches/APs/IPMI, the highest-value target on the
   network if compromised.
6. **`samba-dc` (172.21.0.11) and `xlab-mgmt`/powerdns (172.21.0.53) UDP
   ports** — found during Phase 1's T2 planning for these (not-yet-onboarded)
   namespaces: Cilium's `loadBalancer.mode: hybrid` means UDP traffic to
   these direct-LoadBalancer services is always SNAT'd to the node IP, so
   the in-cluster CiliumNetworkPolicy layer structurally cannot restrict
   *who* reaches those UDP ports — Firewalla is the only enforcement point
   available. Restrict to the three real hosts confirmed live during that
   investigation: `xdt1-t` (172.18.100.100), `xlt1-t` LAN (172.18.100.10)
   and WiFi (172.19.112.1), plus `xfw` itself for powerdns (device
   identity, not an IP — it's the router). TCP ports on those same two services
   *can* be restricted at the CNP layer once T2 onboards them; this
   Firewalla rule is specifically for the UDP half.
7. **Known-broken path to fix, not just document:** Prometheus →
   `172.18.6.1` (xpbx1, Telephony VLAN) currently returns `no route to
   host` per an existing buglog entry. Whatever rule scopes exporter
   access to Zone A (#4 above) needs to explicitly include this target,
   or the fix for #4 will leave this one still broken.

## Structural constraints (apply to the whole matrix, not just one rule)

- **Firewalla cannot see individual k8s workloads.** Cilium masquerades
  all pod→LAN egress to the node IP (`ipMasqAgent` covers only pod CIDR,
  service CIDR, and 172.21.0.0/24). Any rule scoped to "k8s 172.20.3.0/24"
  is necessarily cluster-wide, not per-app — per-workload control is
  Cilium's job (Phase 1/3), not this layer's.
- **Tailscale clients are indistinguishable from `xfw` itself** at this
  layer — SNAT is deliberate (`nix/hosts/nixable/xfw/default.nix:305-320`,
  needed for Firewalla's own ACL chains to key off known networks). Any
  rule that needs to differentiate tailnet clients has to live in
  Tailscale ACLs, not here.
- **UDP vs TCP asymmetry for direct-LoadBalancer k8s services** (see
  rule #6): this isn't specific to samba-dc/powerdns, it's a property of
  every one of the 6 direct-LB namespaces on UDP ports. Any future rule
  touching syncthing (22000/UDP, 21027/UDP) or rustdesk (21116/UDP) hits
  the same constraint.

## Verification, once rules are applied

- From a device on Wired Clients (172.18.100.0/24, Zone B): `nc -vz
  xcog1.lan 4000` should **time out** — rule #1 scopes xcog1 to Zone A +
  HomeAutomation only, and Wired Clients is neither.
- From HomeAutomation (172.18.7.0/24): `nc -vz xcog1.lan 4000` should
  **succeed** — confirms the allow side of the same rule.
- From any VLAN not in Zone A: `nc -vz xsvr1.lan 2049` (NFS) should time
  out.
- Re-dump `get_network_rules` after changes and diff against this
  document — the same drift check used for the in-cluster side.
- Confirm Prometheus in-cluster targets (`172.20.3.201/.202` exporters,
  and `172.18.6.1` xpbx1 specifically) still show "up" in Grafana after
  the exporter-scoping rule (#4/#7) lands — this is the one rule with a
  documented history of breaking a real target if scoped too narrowly.

## Open items to resolve before this can be fully applied

- VLAN 18, VLAN 1000, VLAN 111/115 subnets — unresolved via any tool
  available this session; check the Firewalla app directly.
- The "trusted WiFi SSID" question in the Zone B definition — which of
  112/114/111/115 is actually the trusted family SSID isn't determinable
  from device names alone; confirm with the user before scoping Zone B.
- The two zero-device `network`-scoped block rules — worth deleting or
  understanding before adding new rules alongside them, so the ruleset
  doesn't accumulate dead/unexplained state on top of new live state.
