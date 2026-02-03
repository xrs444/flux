# HomeProd Infrastructure Resource Optimization

## Summary of Changes Made

### 1. Immediate CPU Fix - Dashy Status Checks ✅

**Problem**: Dashy was hammering 21 services with health checks, causing massive CPU consumption across the cluster.
- Manyfold: ~570m CPU (67 requests/second)
- Dashy itself: 909m CPU (nearly 1 full core)

**Solution**:
- **File**: `flux/apps/dashy/configmap-dashy.yaml`
  - Changed `statusCheck: true` → `statusCheck: false`
  - Increased `statusCheckInterval: 300` → `3600` (if re-enabled)

- **File**: `flux/apps/dashy/deployment-dashy.yaml`
  - Added `nodeSelector` to move to `talos-mpp-bzt` (xsvr3 - least loaded)
  - Reduced CPU request: `500m` → `100m`
  - Reduced CPU limit: `2000m` → `500m`
  - Reduced memory request: `512Mi` → `256Mi`
  - Reduced memory limit: `2Gi` → `1Gi`

**Expected Impact**: Immediate reduction of 1.5+ CPU cores cluster-wide

---

### 2. Workload Distribution - Node Affinity ✅

**File**: `flux/apps/manyfold/deployment-manyfold.yaml`
- Added `nodeSelector` to schedule on `talos-mpp-bzt` (xsvr3)
- Moves Manyfold away from the congested xsvr1 node

**Recommended Additional Changes** (manual follow-up):

#### Schedule on talos-h30-ei4 (xsvr2 - 80GB RAM node):
- **Longhorn components**: Instance managers, CSI controllers
- **Databases**: PostgreSQL pods, Redis if used
- **Omada Controller**: 1904Mi memory usage - perfect for big RAM node
- **Large storage workloads**: Anything needing lots of cache

#### Schedule on talos-gvt-qu2 (xsvr1 - Fast CPU node):
- **Tdarr**: Media transcoding (CPU intensive)
- **Paperless-NGX**: Document processing
- **Traefik**: Ingress controller (can stay here, fast CPU helps)

#### Schedule on talos-mpp-bzt (xsvr3 - Balanced node):
- **Dashy**: Already moved ✅
- **Manyfold**: Already moved ✅
- **Jellyfin**: Streaming/playback
- **Jitsi**: Video conferencing
- **Ntfy, Apprise**: Lightweight services

---

### 3. VM Resource Allocation Updates ✅

#### xsvr1 (AMD Ryzen 7 7700 - 16 threads, 61 GiB RAM)

**File**: `nix/hosts/nixos/xsvr1/vms.nix`

| VM | Previous | Updated | Change |
|----|----------|---------|--------|
| v-k8s-xsvr1 | 4 vCPU, 16 GB | **8 vCPU, 24 GB** | +4 vCPU, +8 GB |
| v-xhac1 | 4 vCPU, 8 GB | **4 vCPU, 6 GB** | -2 GB |
| v-xpbx1 | 2 vCPU, 6 GB | **2 vCPU, 4 GB** | -2 GB |
| **Total** | **10 vCPU, 30 GB** | **14 vCPU, 34 GB** | **+4 vCPU, +4 GB** |

**Host Remaining**: 2 threads, 27 GB for Prometheus, Grafana, Kanidm, Samba

---

#### xsvr2 (Intel Atom C3758 - 8 cores, 128 GiB RAM) 🎉

**File**: `nix/hosts/nixos/xsvr2/vms.nix`

| VM | Previous | Updated | Change |
|----|----------|---------|--------|
| v-k8s-xsvr2 | 4 vCPU, 16 GB | **6 vCPU, 80 GB** | +2 vCPU, **+64 GB!** |
| **Total** | **4 vCPU, 16 GB** | **6 vCPU, 80 GB** | **+2 vCPU, +64 GB** |

**Host Remaining**: 2 cores, 48 GB for host services + buffers

**NOTE**: v-ts-xsvr2 not found in Nix config (may be manually managed). Consider allocating 8 GB if needed.

---

#### xsvr3 (Intel i5-8500 - 6 cores, 32 GiB RAM)

**File**: `nix/hosts/nixos/xsvr3/vms.nix`

| VM | Previous | Updated | Change |
|----|----------|---------|--------|
| v-k8s-xsvr3 | 4 vCPU, 16 GB | **5 vCPU, 24 GB** | +1 vCPU, +8 GB |
| **Total** | **4 vCPU, 16 GB** | **5 vCPU, 24 GB** | **+1 vCPU, +8 GB** |

**Host Remaining**: 1 core, 8 GB for host services

---

### Kubernetes Cluster Totals

| Resource | Previous | Updated | Increase |
|----------|----------|---------|----------|
| **Total RAM** | 48 GB | **128 GB** | **+167%** 🚀 |
| **Total vCPUs** | 12 | **19** | **+58%** |

**Node Specialization**:
- **talos-gvt-qu2** (xsvr1): 24 GB, 8 vCPU - Fast CPU (Ryzen 7) - CPU-intensive apps
- **talos-h30-ei4** (xsvr2): **80 GB**, 6 vCPU - MASSIVE RAM - Memory-intensive apps, databases, storage
- **talos-mpp-bzt** (xsvr3): 24 GB, 5 vCPU - Balanced - Streaming, lightweight services

---

## Deployment Steps

### Phase 1: Immediate Fix (Do This NOW)

1. **Apply Dashy configuration changes**:
   ```bash
   cd /Users/xrs444/Repositories/HomeProd/flux
   git add apps/dashy/configmap-dashy.yaml apps/dashy/deployment-dashy.yaml
   git commit -m "Fix Dashy CPU usage: disable status checks and move to xsvr3

- Disable statusCheck to prevent flood of health check requests
- Move to talos-mpp-bzt (xsvr3) with nodeSelector
- Reduce resource limits to prevent monopolizing cluster resources
- This fixes ~1.5 CPU cores of excessive usage cluster-wide

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
   git push
   ```

2. **Apply Manyfold node affinity**:
   ```bash
   git add apps/manyfold/deployment-manyfold.yaml
   git commit -m "Move Manyfold to xsvr3 to reduce load on xsvr1

- Add nodeSelector to schedule on talos-mpp-bzt (xsvr3)
- Reduces congestion on xsvr1 which was handling both Dashy and Manyfold

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
   git push
   ```

3. **Wait for Flux to reconcile** (or force):
   ```bash
   flux reconcile kustomization apps
   ```

4. **Verify Dashy and Manyfold moved**:
   ```bash
   kubectl get pods -n dashy -o wide
   kubectl get pods -n manyfold -o wide
   ```

---

### Phase 2: VM Resource Reallocation (Requires Reboots)

**IMPORTANT**: These changes require VM shutdowns/reboots. Plan maintenance window.

1. **Update and deploy xsvr1 configuration**:
   ```bash
   cd /Users/xrs444/Repositories/HomeProd/nix
   git add hosts/nixos/xsvr1/vms.nix
   git commit -m "Optimize xsvr1 VM resources: increase K8s, reduce HAC/PBX

- v-k8s-xsvr1: 4→8 vCPU, 16→24 GB (was CPU starved at 120%)
- v-xhac1: 8→6 GB (Home Assistant doesn't need 8GB)
- v-xpbx1: 6→4 GB (FreePBX overallocated)
- Total: +4 vCPU, +4 GB for K8s, leaves 27GB for host

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

   # Deploy to xsvr1
   nixos-rebuild switch --flake .#xsvr1 --target-host thomas-local@xsvr1.lan
   ```

2. **Shutdown VMs on xsvr1, rebuild, restart**:
   ```bash
   ssh thomas-local@xsvr1.lan
   # Gracefully shutdown VMs
   virsh shutdown v-k8s-xsvr1
   virsh shutdown v-xhac1
   virsh shutdown v-xpbx1

   # Wait for shutdown, then start them up
   virsh start v-k8s-xsvr1
   virsh start v-xhac1
   virsh start v-xpbx1
   ```

3. **Update and deploy xsvr2 configuration** (HUGE WIN):
   ```bash
   cd /Users/xrs444/Repositories/HomeProd/nix
   git add hosts/nixos/xsvr2/vms.nix
   git commit -m "MASSIVELY increase xsvr2 K8s VM: 16→80 GB RAM

- v-k8s-xsvr2: 4→6 vCPU, 16→80 GB RAM
- xsvr2 has 128GB RAM and was only using 21GB (17%)
- CPU increased to max out Atom cores (leave 2 for host)
- This node becomes the memory-heavy workload specialist
- Leaves 48GB for host services and buffers

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

   nixos-rebuild switch --flake .#xsvr2 --target-host thomas-local@xsvr2.lan
   ```

4. **Shutdown and restart xsvr2 VM**:
   ```bash
   ssh thomas-local@xsvr2.lan
   virsh shutdown v-k8s-xsvr2
   virsh start v-k8s-xsvr2
   ```

5. **Update and deploy xsvr3 configuration**:
   ```bash
   cd /Users/xrs444/Repositories/HomeProd/nix
   git add hosts/nixos/xsvr3/vms.nix
   git commit -m "Increase xsvr3 K8s VM resources

- v-k8s-xsvr3: 4→5 vCPU, 16→24 GB
- Was CPU starved at 220%, leave 1 core for host
- Leaves 8GB for host services

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

   nixos-rebuild switch --flake .#xsvr3 --target-host thomas-local@xsvr3.lan
   ```

6. **Shutdown and restart xsvr3 VM**:
   ```bash
   ssh thomas-local@xsvr3.lan
   virsh shutdown v-k8s-xsvr3
   virsh start v-k8s-xsvr3
   ```

---

### Phase 3: Verify and Monitor

1. **Check Kubernetes node resources**:
   ```bash
   kubectl top nodes
   kubectl describe nodes | grep -A 5 "Allocated resources"
   ```

2. **Verify talos-h30-ei4 has 80GB**:
   ```bash
   kubectl get node talos-h30-ei4 -o json | jq '.status.capacity.memory'
   # Should show ~80Gi
   ```

3. **Monitor cluster CPU usage**:
   ```bash
   kubectl top pods -A --sort-by=cpu | head -20
   ```

4. **Check host resource usage**:
   ```bash
   ssh thomas-local@xsvr1.lan "free -h && uptime"
   ssh thomas-local@xsvr2.lan "free -h && uptime"
   ssh thomas-local@xsvr3.lan "free -h && uptime"
   ```

---

## Expected Outcomes

### Immediate (Phase 1):
- ✅ Dashy CPU usage: 909m → ~100m (90% reduction)
- ✅ Manyfold CPU usage: 570m → ~100m (82% reduction, no more request flood)
- ✅ xsvr1 load: 2.4 → ~1.0 (40% reduction)
- ✅ Cluster-wide savings: ~1.5 CPU cores freed up

### After VM Reallocation (Phase 2):
- ✅ K8s cluster RAM: 48 GB → 128 GB (+167%)
- ✅ K8s cluster vCPUs: 12 → 19 (+58%)
- ✅ xsvr1 RAM pressure: 88% → ~70% (safer headroom)
- ✅ xsvr2 utilization: 17% → ~60% (much better use of 128GB!)
- ✅ No more CPU throttling on Talos VMs

### Long-term Benefits:
- Nodes can specialize (CPU vs RAM intensive workloads)
- Room to grow cluster without hardware upgrades
- Better performance for memory-hungry apps (databases, caches)
- Faster transcoding and processing with more vCPUs

---

## Optional: Additional Workload Tuning

Consider adding `nodeSelector` or `affinity` rules for these apps:

### High Memory Apps → talos-h30-ei4 (xsvr2, 80GB):
- Omada Controller (1904Mi)
- Longhorn instance managers
- PostgreSQL databases
- Any future database workloads

### CPU Intensive Apps → talos-gvt-qu2 (xsvr1, Ryzen 7):
- Tdarr (transcoding)
- Paperless-NGX (document processing)
- Keep Traefik here

### Balanced/Light Apps → talos-mpp-bzt (xsvr3):
- Jellyfin streaming
- Jitsi
- Notification services (Ntfy, Apprise)

---

## Rollback Plan

If issues occur:

1. **Revert Dashy changes**:
   ```bash
   cd /Users/xrs444/Repositories/HomeProd/flux
   git revert HEAD~2..HEAD  # Reverts last 2 commits
   git push
   ```

2. **Revert VM configs**:
   ```bash
   cd /Users/xrs444/Repositories/HomeProd/nix
   git revert HEAD~3..HEAD  # Reverts last 3 commits
   # Rebuild each host
   nixos-rebuild switch --flake .#xsvr1 --target-host thomas-local@xsvr1.lan
   nixos-rebuild switch --flake .#xsvr2 --target-host thomas-local@xsvr2.lan
   nixos-rebuild switch --flake .#xsvr3 --target-host thomas-local@xsvr3.lan
   ```

---

## Files Modified

### Flux Repository:
- ✅ `flux/apps/dashy/configmap-dashy.yaml` - Disabled status checks
- ✅ `flux/apps/dashy/deployment-dashy.yaml` - Added nodeSelector, reduced resources
- ✅ `flux/apps/manyfold/deployment-manyfold.yaml` - Added nodeSelector

### Nix Repository:
- ✅ `nix/hosts/nixos/xsvr1/vms.nix` - Optimized VM allocations
- ✅ `nix/hosts/nixos/xsvr2/vms.nix` - MASSIVELY increased K8s VM to 80GB
- ✅ `nix/hosts/nixos/xsvr3/vms.nix` - Increased K8s VM resources

---

**Generated**: 2026-01-31
**By**: Claude Code Resource Optimization Analysis
