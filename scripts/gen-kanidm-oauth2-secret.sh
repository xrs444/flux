#!/usr/bin/env bash
# gen-kanidm-oauth2-secret.sh
# Usage: ./gen-kanidm-oauth2-secret.sh <app-name> <namespace> [secret-name]
# Fetches OAuth2 client credentials from kanidm and generates a Kubernetes SealedSecret manifest for the app.

set -euo pipefail

KANIDM_CLI="kanidm"
APP_NAME="${1:-}"
NAMESPACE="${2:-default}"
SECRET_NAME="${3:-oauth2-secret-$APP_NAME}"

if [[ -z "$APP_NAME" ]]; then
  echo "Usage: $0 <app-name> <namespace> [secret-name]" >&2
  exit 1
fi

# Fetch client credentials from kanidm (requires kanidm CLI to be authenticated)
CLIENT_JSON="$($KANIDM_CLI client get "$APP_NAME" --json 2>/dev/null)"
if [[ -z "$CLIENT_JSON" ]]; then
  echo "Error: Could not fetch client details for '$APP_NAME' from kanidm." >&2
  exit 2
fi

CLIENT_ID=$(echo "$CLIENT_JSON" | jq -r '.uuid // .id // .client_id // .clientId // .client_id')
CLIENT_SECRET=$(echo "$CLIENT_JSON" | jq -r '.secret // .client_secret // .clientSecret // .client_secret')

if [[ -z "$CLIENT_ID" || -z "$CLIENT_SECRET" ]]; then
  echo "Error: Missing client_id or client_secret in kanidm response." >&2
  exit 3
fi

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
EOF

# Seal the secret using kubeseal (must have access to the cluster's sealing key)
if ! command -v kubeseal >/dev/null 2>&1; then
  echo "Error: kubeseal is not installed or not in PATH." >&2
  rm -f "$TMP_SECRET"
  exit 4
fi

kubeseal --format yaml < "$TMP_SECRET"

rm -f "$TMP_SECRET"

>&2 echo "Generated SealedSecret manifest for app '$APP_NAME' in namespace '$NAMESPACE' (secret: $SECRET_NAME)"
