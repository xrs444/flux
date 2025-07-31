#!/bin/bash

# Script to remove claim refs from PVs in Released state
# This allows PVs to transition back to Available state

echo "Finding PersistentVolumes in Released state..."

# Get all PVs in Released state
RELEASED_PVS=$(kubectl get pv --no-headers | grep Released | awk '{print $1}')

if [ -z "$RELEASED_PVS" ]; then
    echo "No PersistentVolumes found in Released state."
    exit 0
fi

echo "Found the following PVs in Released state:"
echo "$RELEASED_PVS"
echo

read -p "Do you want to remove claim refs from these PVs? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    exit 0
fi

# Remove claim refs from each PV
for pv in $RELEASED_PVS; do
    echo "Removing claim ref from PV: $pv"
    kubectl patch pv "$pv" --type json -p='[{"op": "remove", "path": "/spec/claimRef"}]'
    
    if [ $? -eq 0 ]; then
        echo "✓ Successfully removed claim ref from $pv"
    else
        echo "✗ Failed to remove claim ref from $pv"
    fi
done

echo
echo "Operation completed. Checking final state..."
kubectl get pv --no-headers | grep -E "Available|Released"