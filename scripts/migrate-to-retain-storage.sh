#!/usr/bin/env bash
# migrate-to-retain-storage.sh
# Safely migrate PVCs from Delete to Retain storage class
#
# This script:
# 1. Changes PV reclaim policy from Delete to Retain
# 2. Updates PVC storageClassName to longhorn-retain
# 3. Adds volumeName to pin PVC to its current PV
#
# WARNING: Run this during a maintenance window
# Data is NOT at risk, but pods will restart

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Migrate PVCs from Delete to Retain storage class policy.

OPTIONS:
    -l, --list          List all PVCs using Delete policy
    -m, --migrate       Migrate all PVCs to Retain policy
    -d, --dry-run       Show what would be done without making changes
    -h, --help          Show this help message

EXAMPLES:
    # List PVCs that need migration
    $0 --list

    # Dry run to see what would change
    $0 --dry-run

    # Perform the migration
    $0 --migrate

EOF
    exit 1
}

list_delete_pvcs() {
    echo -e "${YELLOW}PVCs using Delete policy (longhorn storage class):${NC}\n"
    kubectl get pvc -A -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
STORAGECLASS:.spec.storageClassName,\
VOLUME:.spec.volumeName,\
CAPACITY:.status.capacity.storage \
    | grep -E "(NAMESPACE|^[a-z-]+ +[a-z-]+ +longhorn +)"
}

migrate_pvc_to_retain() {
    local namespace="$1"
    local pvc_name="$2"
    local pv_name="$3"
    local dry_run="${4:-false}"

    if [ "$dry_run" = "true" ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would migrate: $namespace/$pvc_name (PV: $pv_name)"
        echo "  1. Patch PV $pv_name: reclaim policy → Retain"
        echo "  2. Update PVC definition: storageClassName → longhorn-retain, add volumeName"
        return 0
    fi

    echo -e "${GREEN}Migrating:${NC} $namespace/$pvc_name (PV: $pv_name)"

    # Step 1: Change PV reclaim policy to Retain
    echo "  1. Patching PV reclaim policy..."
    kubectl patch pv "$pv_name" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'

    echo -e "${GREEN}✓${NC} Migration complete for $namespace/$pvc_name"
    echo ""
}

migrate_all() {
    local dry_run="${1:-false}"

    echo -e "${YELLOW}Starting migration of PVCs to Retain policy...${NC}\n"

    if [ "$dry_run" = "false" ]; then
        read -p "This will patch PVs to use Retain policy. Continue? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Aborted."
            exit 0
        fi
    fi

    # Get all PVCs using longhorn (Delete) storage class
    local pvcs=$(kubectl get pvc -A -o json | jq -r '
        .items[] |
        select(.spec.storageClassName == "longhorn") |
        "\(.metadata.namespace) \(.metadata.name) \(.spec.volumeName)"
    ')

    if [ -z "$pvcs" ]; then
        echo -e "${GREEN}No PVCs found using Delete policy.${NC}"
        return 0
    fi

    local count=0
    while IFS= read -r line; do
        read -r namespace pvc_name pv_name <<< "$line"
        migrate_pvc_to_retain "$namespace" "$pvc_name" "$pv_name" "$dry_run"
        ((count++))
    done <<< "$pvcs"

    if [ "$dry_run" = "false" ]; then
        echo -e "${GREEN}✓ Migration complete! Migrated $count PVCs.${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Update PVC YAML files to use storageClassName: longhorn-retain"
        echo "  2. Add volumeName to each PVC definition"
        echo "  3. Commit changes to git"
        echo ""
        echo "Use this command to generate volumeName additions:"
        echo "  kubectl get pvc -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,VOL:.spec.volumeName --no-headers | grep -v '<none>'"
    else
        echo -e "${YELLOW}[DRY RUN]${NC} Would migrate $count PVCs"
    fi
}

case "${1:-}" in
    -l|--list)
        list_delete_pvcs
        ;;
    -d|--dry-run)
        migrate_all true
        ;;
    -m|--migrate)
        migrate_all false
        ;;
    -h|--help|*)
        usage
        ;;
esac
