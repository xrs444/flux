# Storage Management Guide

## Critical Storage Architecture Rules

### ⚠️ NEVER DELETE PVs WITH RECLAIM POLICY "RETAIN"

PersistentVolumes (PVs) with `storageClass: longhorn-retain` contain application data and configurations. Deleting them causes **PERMANENT DATA LOSS**.

## Storage Architecture Overview

### Centralized PVC Definitions
All PersistentVolumeClaims (PVCs) are defined in `/flux/apps/storage/`, **NOT** in individual app directories. This:
- Centralizes storage management
- Prevents accidental PVC recreation
- Makes volume bindings explicit and traceable

### Volume Pinning Strategy
PVCs for stateful apps use `volumeName` to pin to specific PVs:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data-pvc
  namespace: app
spec:
  storageClassName: "longhorn-retain"
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  volumeName: pvc-6e2b1029-2c74-4233-bb5a-cf1c4c7c6b2d  # Pin to specific PV
```

**Why pin volumes?**
- Preserves data across PVC deletions
- Prevents accidental rebinding to wrong PV
- Makes disaster recovery explicit and safe

## Common Storage Issues and Solutions

### Issue 1: PVC Stuck in "Pending" Status

**Symptom:** PVC shows `Pending` and events show "waiting for a volume to be created, either by external provisioner or manually"

**Diagnosis:**
```bash
kubectl get pvc -A | grep Pending
kubectl describe pvc <pvc-name> -n <namespace>
```

**Common Causes:**

#### Cause A: PV is in "Released" State
When a PVC is deleted, its PV with `Retain` policy keeps the old `claimRef`, preventing rebinding.

**Solution:**
```bash
# 1. List Released PVs
./flux/scripts/fix-released-pvs.sh --list

# 2. Verify the PV contains correct data (check Longhorn UI)

# 3. Fix the Released PV
./flux/scripts/fix-released-pvs.sh --fix <pv-name>

# 4. Verify PVC now binds
kubectl get pvc -n <namespace>
```

#### Cause B: volumeName Points to Non-Existent PV
PVC has `volumeName` referencing a PV that was deleted.

**Solution:**
```bash
# If data is lost and you need new volume:
# 1. Remove volumeName from PVC definition in flux/apps/storage/
# 2. Apply changes
kubectl apply -k flux/apps/storage/

# If data exists on different PV:
# 1. Find the correct PV containing the data
# 2. Update volumeName in flux/apps/storage/pvc-<app>.yaml
# 3. Apply changes
```

#### Cause C: PV Bound to Wrong PVC
A PV without `volumeName` grabbed the wrong available PV (e.g., jellyfin-config bound to lubelogger's PV).

**Solution:**
```bash
# 1. Delete the incorrectly bound PVC (will make PV Released)
kubectl delete pvc <pvc-name> -n <namespace>

# 2. Fix the Released PV
./flux/scripts/fix-released-pvs.sh --fix <pv-name>

# 3. Update the CORRECT PVC to have volumeName pointing to this PV
# Edit flux/apps/storage/pvc-<correct-app>.yaml

# 4. Apply changes
kubectl apply -k flux/apps/storage/
```

### Issue 2: App CrashLoopBackOff Due to Storage

**Symptom:** Pod restarts continuously, logs show permission errors or missing directories

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
kubectl get pvc -n <namespace>
```

**Solutions:**
- Verify PVC is `Bound` (not `Pending`)
- Check pod volumeMount paths match PVC mountPath
- Verify Longhorn volume is healthy in Longhorn UI
- Check node where volume is attached has connectivity

## Safe Recovery Procedures

### Recovering from Released PV State

**DO:**
✅ Use `fix-released-pvs.sh` script
✅ Verify data in Longhorn UI before fixing
✅ Ensure PVC has correct `volumeName` before applying
✅ Test with non-critical apps first
✅ Take Longhorn snapshots before major changes

**DON'T:**
❌ Delete PVs with `Retain` policy
❌ Delete PVCs without backing up data first
❌ Remove `volumeName` from PVCs with existing data
❌ Run `kubectl delete pv` without understanding implications
❌ Use `kubectl apply --prune` on storage resources

### Creating New Volumes for Fresh Installs

For apps that need new storage (no existing data):

```yaml
# flux/apps/storage/pvc-newapp.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: newapp-data-pvc
  namespace: newapp
spec:
  storageClassName: "longhorn-retain"
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  # NO volumeName - let Longhorn create new volume
```

After first binding, **add the volumeName** to pin it:
```bash
# 1. Get the bound PV name
kubectl get pvc newapp-data-pvc -n newapp -o jsonpath='{.spec.volumeName}'

# 2. Update PVC definition with volumeName
# 3. Commit changes to git
```

## Storage Classes

| Storage Class | Reclaim Policy | Use Case |
|--------------|----------------|----------|
| `longhorn` | Delete | Ephemeral data, caches |
| `longhorn-retain` | Retain | **Stateful apps, databases, configs** |
| `longhorn-ephemeral` | Delete | Temporary workloads |
| `longhorn-static` | Delete | Pre-provisioned volumes |

## Monitoring Storage Health

```bash
# Check PV/PVC status across cluster
kubectl get pv,pvc --all-namespaces

# Find Released PVs that need attention
kubectl get pv | grep Released

# Check Longhorn volume health
kubectl get volumes -n longhorn-system

# View storage usage
kubectl top nodes
```

## Backup and Disaster Recovery

### Before Making Storage Changes

1. **Take Longhorn snapshots** of all important volumes
2. **Document current PV/PVC mappings**:
   ```bash
   kubectl get pvc -A -o custom-columns=\
   NAMESPACE:.metadata.namespace,\
   NAME:.metadata.name,\
   VOLUME:.spec.volumeName,\
   STATUS:.status.phase > storage-snapshot.txt
   ```
3. **Test recovery procedure** on non-critical app
4. **Have rollback plan ready**

### Regular Maintenance

- **Weekly**: Review Released PVs and clean up if safe
- **Monthly**: Verify all PVCs have correct `volumeName` pinning
- **Quarterly**: Test recovery procedures
- **Before major updates**: Full Longhorn backup

## Troubleshooting Checklist

When apps have storage issues:

- [ ] Check PVC status: `kubectl get pvc -n <namespace>`
- [ ] Check PV status: `kubectl get pv | grep <app>`
- [ ] Verify volumeName matches: `kubectl get pvc <pvc> -n <ns> -o yaml | grep volumeName`
- [ ] Check Longhorn UI for volume health
- [ ] Review pod events: `kubectl describe pod <pod> -n <namespace>`
- [ ] Check storage class exists: `kubectl get storageclass`
- [ ] Verify Longhorn CSI is healthy: `kubectl get pods -n longhorn-system`
- [ ] Check node storage capacity: `kubectl top nodes`

## Key Files

- **PVC Definitions**: `/flux/apps/storage/pvc-*.yaml`
- **PV Definitions** (NFS): `/flux/apps/storage/pv-*.yaml`
- **Storage Kustomization**: `/flux/apps/storage/kustomization.yaml`
- **Recovery Script**: `/flux/scripts/fix-released-pvs.sh`
- **Cleanup Script**: `/flux/scripts/cleanup-released-pvs.sh`

## Getting Help

If unsure about any storage operation:
1. **Stop** - Don't delete anything
2. **Document** current state with kubectl outputs
3. **Check Longhorn UI** to verify data location
4. **Review this guide** for safe procedures
5. **Test on non-critical app** first
6. **Back up** before making changes
