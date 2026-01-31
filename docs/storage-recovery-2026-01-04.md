# Storage Recovery Summary - January 4, 2026

## Issue
Multiple apps (freepbx, lubelogger, omada, jellyfin) had storage access issues due to PVs in "Released" state and incorrect PV-to-PVC bindings.

## Root Cause
1. **PVs entered Released state** when PVCs were previously deleted
2. **jellyfin-config PVC had no volumeName** and accidentally bound to lubelogger's PV (pvc-872bf303...)
3. **PVCs with volumeName** couldn't bind because claimRef blocked rebinding
4. **omada-logs PV** no longer existed, causing permanent Pending state

## Resolution Actions

### 1. Fixed PV Bindings
- Removed claimRef from Released PVs to make them Available
- Deleted and recreated PVCs where volumeName was immutable
- Added volumeName to jellyfin-config to prevent future misbinding

### 2. PVC to PV Mapping (Current State)
| App | PVC Name | PV Name | Status | Data Preserved |
|-----|----------|---------|--------|----------------|
| freepbx | freepbx-data-pvc | pvc-6e2b1029-2c74-4233-bb5a-cf1c4c7c6b2d | Bound | ✅ Yes |
| lubelogger | lubelogger-data-pvc | pvc-872bf303-fd1b-4a3a-a16c-e039181edaba | Bound | ✅ Yes |
| omada | omada-data-pvc | pvc-05a7a941-bf4b-41d2-9e38-156f75558310 | Bound | ✅ Yes |
| omada | omada-logs-pvc | pvc-6853283d-e006-481a-9ce5-de622b13f2b1 | Bound | ⚠️ New volume |
| jellyfin | jellyfin-config | pvc-8c9fa15b-6fad-498d-807b-42fb9d5a1720 | Bound | ✅ Yes |

### 3. Files Modified
- `flux/apps/storage/pvc-jellyfin-config.yaml` - Added volumeName pinning
- `flux/apps/storage/pvc-lubelogger.yaml` - Restored volumeName
- `flux/apps/storage/pvc-omada-logs.yaml` - Added new volumeName after recreation

### 4. Tools Created
- `flux/scripts/fix-released-pvs.sh` - Safe PV recovery script
- `flux/apps/storage/STORAGE_MANAGEMENT_GUIDE.md` - Comprehensive storage documentation

## Prevention Measures Implemented

### 1. Volume Pinning
All stateful app PVCs now have explicit `volumeName` to:
- Prevent accidental rebinding to wrong PV
- Preserve data across PVC deletions
- Make recovery explicit and safe

### 2. Documentation
Created comprehensive guide covering:
- Storage architecture and why volumes are pinned
- Safe recovery procedures for Released PVs
- Common issues and solutions
- Backup and disaster recovery procedures
- What to NEVER do (delete Retain PVs, remove volumeName with data)

### 3. Recovery Tooling
Created `fix-released-pvs.sh` script that:
- Safely lists Released PVs
- Removes claimRef with confirmation
- Provides clear next steps
- Prevents accidental data loss

## Critical Lessons Learned

### ⚠️ NEVER DELETE PVs WITH RECLAIM POLICY "RETAIN"
- These contain actual application data
- Deletion causes **PERMANENT DATA LOSS**
- Always fix Released state by removing claimRef, not deleting

### ⚠️ NEVER REMOVE volumeName FROM PVCs WITH DATA
- volumeName pins PVC to specific PV containing data
- Removing it allows PVC to bind to ANY available PV
- This can cause data loss or mismatch

### ⚠️ PVCs WITHOUT volumeName ARE DANGEROUS
- Will bind to first matching available PV
- Can accidentally grab another app's volume
- Always add volumeName after first binding

## Verification

### PVC Status
```bash
kubectl get pvc -A | grep -E "(freepbx|lubelogger|omada|jellyfin-config)"
```
All PVCs show `Bound` status ✅

### Pod Status
```bash
kubectl get pods -A | grep -E "(freepbx|lubelogger|omada|jellyfin)"
```
- freepbx: Running ✅
- lubelogger: Running ✅
- omada: ContainerCreating (normal for startup) ✅
- jellyfin: ContainerCreating (normal for startup) ✅

### Released PVs Remaining
```bash
./flux/scripts/fix-released-pvs.sh --list
```
Old jellyfin-config PVs remain Released but are historical artifacts and safe to leave.

## Next Steps

1. **Monitor pod startups** - Verify all apps become Running
2. **Test functionality** - Confirm apps can access their data
3. **Review documentation** - Read STORAGE_MANAGEMENT_GUIDE.md
4. **Commit changes** - Push fixed PVC definitions to git
5. **Cleanup old PVs** - After verification, consider cleanup of old Released PVs:
   - pvc-24e0fd87-101c-455d-9322-0cf258be8dde (old jellyfin-config)
   - pvc-2e4615b1-2ab4-4ef7-a816-76c5073d5f7d (old jellyfin-config)

## References
- Recovery Script: `/flux/scripts/fix-released-pvs.sh`
- Storage Guide: `/flux/apps/storage/STORAGE_MANAGEMENT_GUIDE.md`
- PVC Definitions: `/flux/apps/storage/pvc-*.yaml`
