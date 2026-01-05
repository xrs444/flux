#!/usr/bin/env bash
# fix-released-pvs.sh
# Safe recovery script for Released PersistentVolumes
#
# WARNING: This script handles data-bearing volumes. Use with extreme caution.
# NEVER delete PVs without verifying they don't contain important data.
#
# When a PVC is deleted, its PV with 'Retain' policy enters 'Released' state.
# The PV retains the old claimRef, preventing rebinding.
#
# Safe recovery process:
# 1. Verify the PV contains the correct data (check volume path in Longhorn UI)
# 2. Remove the claimRef to make PV Available
# 3. Create new PVC with volumeName pointing to the specific PV
# 4. Verify pod mounts the volume and data is intact

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Safe recovery script for Released PersistentVolumes.

OPTIONS:
    -l, --list          List all Released PVs and their claims
    -f, --fix PV_NAME   Fix a specific Released PV by removing claimRef
    -h, --help          Show this help message

EXAMPLES:
    # List all Released PVs
    $0 --list

    # Fix a specific Released PV (makes it Available for rebinding)
    $0 --fix pvc-6e2b1029-2c74-4233-bb5a-cf1c4c7c6b2d

IMPORTANT:
    - This script only removes claimRef - it does NOT delete data
    - Always verify PVC has correct volumeName before fixing
    - Check Longhorn UI to confirm data integrity before proceeding
    - For new volumes, remove volumeName from PVC spec instead

EOF
    exit 1
}

list_released_pvs() {
    echo -e "${YELLOW}Released PersistentVolumes:${NC}\n"
    kubectl get pv -o custom-columns=\
NAME:.metadata.name,\
CAPACITY:.spec.capacity.storage,\
RECLAIM:.spec.persistentVolumeReclaimPolicy,\
STATUS:.status.phase,\
CLAIM:.spec.claimRef.name,\
NAMESPACE:.spec.claimRef.namespace,\
STORAGECLASS:.spec.storageClassName \
    | grep -E "(NAME|Released)" || echo "No Released PVs found."
}

fix_released_pv() {
    local pv_name="$1"

    # Verify PV exists and is Released
    if ! kubectl get pv "$pv_name" &>/dev/null; then
        echo -e "${RED}ERROR: PV '$pv_name' not found${NC}" >&2
        exit 1
    fi

    local status=$(kubectl get pv "$pv_name" -o jsonpath='{.status.phase}')
    if [ "$status" != "Released" ]; then
        echo -e "${RED}ERROR: PV '$pv_name' is not in Released state (current: $status)${NC}" >&2
        exit 1
    fi

    local claim_name=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.claimRef.name}')
    local claim_ns=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.claimRef.namespace}')

    echo -e "${YELLOW}PV Details:${NC}"
    echo "  Name: $pv_name"
    echo "  Previous Claim: $claim_ns/$claim_name"
    echo "  Status: $status"
    echo ""

    read -p "Remove claimRef to make this PV Available? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi

    echo -e "${GREEN}Removing claimRef from PV...${NC}"
    kubectl patch pv "$pv_name" --type json -p '[{"op": "remove", "path": "/spec/claimRef"}]'

    echo -e "${GREEN}✓ PV '$pv_name' is now Available for rebinding${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Verify the PVC in flux/apps/storage/ has volumeName: $pv_name"
    echo "  2. Apply: kubectl apply -k flux/apps/storage/"
    echo "  3. Verify binding: kubectl get pvc -n $claim_ns"
}

# Parse arguments
case "${1:-}" in
    -l|--list)
        list_released_pvs
        ;;
    -f|--fix)
        if [ -z "${2:-}" ]; then
            echo -e "${RED}ERROR: PV name required${NC}" >&2
            usage
        fi
        fix_released_pv "$2"
        ;;
    -h|--help|*)
        usage
        ;;
esac
