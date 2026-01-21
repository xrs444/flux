# Flux Repository Utilities
# Validation, storage management, and secret generation tasks

# Validate Flux manifests and Kustomize overlays
validate:
    #!/usr/bin/env bash
    # Downloads Flux OpenAPI schemas and validates Flux custom resources
    # and Kustomize overlays using kubeconform.
    # Prerequisites: yq v4.34, kustomize v5.3, kubeconform v0.6

    set -o errexit
    set -o pipefail

    # mirror kustomize-controller build options
    kustomize_flags=("--load-restrictor=LoadRestrictionsNone")
    kustomize_config="kustomization.yaml"

    # skip Kubernetes Secrets due to SOPS fields failing validation
    kubeconform_flags=("-skip=Secret")
    kubeconform_config=("-strict" "-ignore-missing-schemas" "-schema-location" "default" "-schema-location" "/tmp/flux-crd-schemas" "-verbose")

    echo "INFO - Downloading Flux OpenAPI schemas"
    mkdir -p /tmp/flux-crd-schemas/master-standalone-strict
    curl -sL https://github.com/fluxcd/flux2/releases/latest/download/crd-schemas.tar.gz | tar zxf - -C /tmp/flux-crd-schemas/master-standalone-strict

    find . -type f -name '*.yaml' ! -path './charts/*' ! -path './*/charts/*' -print0 | while IFS= read -r -d $'\0' file;
      do
        echo "INFO - Validating $file"
        yq e 'true' "$file" > /dev/null
    done

    echo "INFO - Validating clusters"
    find ./cluster -maxdepth 2 -type f -name '*.yaml' -print0 | while IFS= read -r -d $'\0' file;
      do
        kubeconform "${kubeconform_flags[@]}" "${kubeconform_config[@]}" "${file}"
        if [[ ${PIPESTATUS[0]} != 0 ]]; then
          exit 1
        fi
    done

    echo "INFO - Validating kustomize overlays"
    find . -type f -name $kustomize_config -print0 | while IFS= read -r -d $'\0' file;
      do
        echo "INFO - Validating kustomization ${file/%$kustomize_config}"
        kustomize build "${file/%$kustomize_config}" "${kustomize_flags[@]}" | \
          kubeconform "${kubeconform_flags[@]}" "${kubeconform_config[@]}"
        if [[ ${PIPESTATUS[0]} != 0 ]]; then
          exit 1
        fi
    done

# Clean up PersistentVolumes in Released state
cleanup-released-pvs:
    #!/usr/bin/env bash
    # Removes claim refs from PVs in Released state, allowing them to
    # transition back to Available state

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

# List all Released PVs
list-released-pvs:
    #!/usr/bin/env bash
    echo "Released PersistentVolumes:"
    echo
    kubectl get pv -o custom-columns=\
    NAME:.metadata.name,\
    CAPACITY:.spec.capacity.storage,\
    RECLAIM:.spec.persistentVolumeReclaimPolicy,\
    STATUS:.status.phase,\
    CLAIM:.spec.claimRef.name,\
    NAMESPACE:.spec.claimRef.namespace,\
    STORAGECLASS:.spec.storageClassName \
        | grep -E "(NAME|Released)" || echo "No Released PVs found."

# Fix a specific Released PV by removing its claimRef
fix-released-pv PV_NAME:
    #!/usr/bin/env bash
    set -euo pipefail

    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m'

    pv_name="{{PV_NAME}}"

    # Verify PV exists and is Released
    if ! kubectl get pv "$pv_name" &>/dev/null; then
        echo -e "${RED}ERROR: PV '$pv_name' not found${NC}" >&2
        exit 1
    fi

    status=$(kubectl get pv "$pv_name" -o jsonpath='{.status.phase}')
    if [ "$status" != "Released" ]; then
        echo -e "${RED}ERROR: PV '$pv_name' is not in Released state (current: $status)${NC}" >&2
        exit 1
    fi

    claim_name=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.claimRef.name}')
    claim_ns=$(kubectl get pv "$pv_name" -o jsonpath='{.spec.claimRef.namespace}')

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

# Generate Kanidm OAuth2 SealedSecret
gen-oauth2-secret APP_NAME NAMESPACE SECRET_NAME="":
    #!/usr/bin/env bash
    # Fetches OAuth2 client credentials from kanidm and generates a
    # Kubernetes SealedSecret manifest

    set -euo pipefail

    KANIDM_CLI="kanidm"
    KANIDM_URL="${KANIDM_URL:-https://idm.xrs444.net}"
    KANIDM_USER="${KANIDM_USER:-idm_admin}"
    APP_NAME="{{APP_NAME}}"
    NAMESPACE="{{NAMESPACE}}"
    SECRET_NAME="{{SECRET_NAME}}"

    # Set default secret name if not provided
    if [[ -z "$SECRET_NAME" ]]; then
      SECRET_NAME="oauth2-secret-$APP_NAME"
    fi

    # Fetch client credentials from kanidm
    CLIENT_JSON="$($KANIDM_CLI --url "$KANIDM_URL" system oauth2 get "$APP_NAME" --name "$KANIDM_USER" --output json 2>/dev/null)"
    if [[ -z "$CLIENT_JSON" ]]; then
      echo "Error: Could not fetch client details for '$APP_NAME' from kanidm." >&2
      exit 2
    fi

    CLIENT_ID=$(echo "$CLIENT_JSON" | jq -r '.attrs.uuid[0] // .uuid // empty')
    if [[ -z "$CLIENT_ID" ]]; then
      echo "Error: Could not extract client_id (uuid) from kanidm response." >&2
      exit 3
    fi

    # Get the basic secret separately
    CLIENT_SECRET="$($KANIDM_CLI --url "$KANIDM_URL" system oauth2 show-basic-secret "$APP_NAME" --name "$KANIDM_USER" 2>/dev/null | grep -v '^$' | tail -1)"
    if [[ -z "$CLIENT_SECRET" ]]; then
      echo "Error: Could not fetch client_secret from kanidm." >&2
      exit 3
    fi

    # Generate cookie secret for OAuth2 proxy (32 bytes)
    COOKIE_SECRET_RAW=$(openssl rand -base64 32 | tr -d '\n=' | head -c 32)
    COOKIE_SECRET=$(printf "%s" "$COOKIE_SECRET_RAW" | base64 | tr -d '\n')

    # Create a temporary Secret manifest
    TMP_SECRET=$(mktemp)
    cat <<EOF > "$TMP_SECRET"
    apiVersion: v1
    kind: Secret
    metadata:
      name: $SECRET_NAME
      namespace: $NAMESPACE
    type: Opaque
    data:
      client-id: $(printf "%s" "$CLIENT_ID" | base64 | tr -d '\n')
      client-secret: $(printf "%s" "$CLIENT_SECRET" | base64 | tr -d '\n')
      cookie-secret: $COOKIE_SECRET
    EOF

    # Seal the secret using kubeseal
    if ! command -v kubeseal >/dev/null 2>&1; then
      echo "Error: kubeseal is not installed or not in PATH." >&2
      rm -f "$TMP_SECRET"
      exit 4
    fi

    kubeseal --format yaml --controller-name sealed-secrets --controller-namespace sealed-secrets < "$TMP_SECRET"

    rm -f "$TMP_SECRET"

    >&2 echo "Generated SealedSecret manifest for app '$APP_NAME' in namespace '$NAMESPACE' (secret: $SECRET_NAME)"

# List PVCs using Delete policy
list-delete-pvcs:
    #!/usr/bin/env bash
    echo "PVCs using Delete policy (longhorn storage class):"
    echo
    kubectl get pvc -A -o custom-columns=\
    NAMESPACE:.metadata.namespace,\
    NAME:.metadata.name,\
    STORAGECLASS:.spec.storageClassName,\
    VOLUME:.spec.volumeName,\
    CAPACITY:.status.capacity.storage \
        | grep -E "(NAMESPACE|^[a-z-]+ +[a-z-]+ +longhorn +)"

# Migrate PVCs from Delete to Retain storage class (dry-run)
migrate-to-retain-dry-run:
    @just _migrate-to-retain true

# Migrate PVCs from Delete to Retain storage class
migrate-to-retain:
    @just _migrate-to-retain false

# Internal: Perform PVC migration to Retain policy
_migrate-to-retain DRY_RUN:
    #!/usr/bin/env bash
    set -euo pipefail

    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m'

    dry_run="{{DRY_RUN}}"

    echo -e "${YELLOW}Starting migration of PVCs to Retain policy...${NC}"
    echo

    if [ "$dry_run" = "false" ]; then
        read -p "This will patch PVs to use Retain policy. Continue? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Aborted."
            exit 0
        fi
    fi

    # Get all PVCs using longhorn (Delete) storage class
    pvcs=$(kubectl get pvc -A -o json | jq -r '
        .items[] |
        select(.spec.storageClassName == "longhorn") |
        "\(.metadata.namespace) \(.metadata.name) \(.spec.volumeName)"
    ')

    if [ -z "$pvcs" ]; then
        echo -e "${GREEN}No PVCs found using Delete policy.${NC}"
        exit 0
    fi

    count=0
    while IFS= read -r line; do
        read -r namespace pvc_name pv_name <<< "$line"

        if [ "$dry_run" = "true" ]; then
            echo -e "${YELLOW}[DRY RUN]${NC} Would migrate: $namespace/$pvc_name (PV: $pv_name)"
            echo "  1. Patch PV $pv_name: reclaim policy → Retain"
            echo "  2. Update PVC definition: storageClassName → longhorn-retain, add volumeName"
        else
            echo -e "${GREEN}Migrating:${NC} $namespace/$pvc_name (PV: $pv_name)"
            echo "  1. Patching PV reclaim policy..."
            kubectl patch pv "$pv_name" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
            echo -e "${GREEN}✓${NC} Migration complete for $namespace/$pvc_name"
            echo ""
        fi

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
