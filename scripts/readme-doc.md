# scripts

## Overview

Utility scripts for Flux repository maintenance, validation, cleanup operations, and secret management.

## Scripts

### validate.sh
Validates Flux custom resources and Kustomize overlays before committing changes to ensure manifests are correct.

**Purpose:**
- Prevent invalid manifests from being committed
- Catch errors before Flux attempts reconciliation
- Ensure Kustomize builds succeed
- Validate against Kubernetes and Flux schemas

**Prerequisites:**
- `yq` v4.34 or later
- `kustomize` v5.3 or later
- `kubeconform` v0.6 or later

**Usage:**
```bash
./scripts/validate.sh
```

**What It Validates:**
- Flux Kustomization resources
- HelmRelease definitions
- Kubernetes manifest syntax and structure
- Kustomize overlay validity
- CRD compliance and schema adherence
- Resource references and dependencies

**CI Integration:**
This script runs automatically in CI pipelines to validate pull requests.

### cleanup-released-pvs.sh
Cleans up PersistentVolumes in "Released" state that are no longer bound to PersistentVolumeClaims.

**Purpose:**
- Remove orphaned PVs after PVC deletion
- Free up storage capacity in Longhorn
- Prevent accumulation of unused volumes
- Maintain clean storage state

**Usage:**
```bash
./scripts/cleanup-released-pvs.sh
```

**Safety:**
- Only affects PVs in "Released" state
- Does not touch "Bound" or "Available" volumes
- Lists PVs before deletion
- Prompts for confirmation in interactive mode

**When to Run:**
- After deleting applications with persistent storage
- During storage maintenance windows
- When Longhorn shows Released volumes
- Before storage capacity planning

### gen-kanidm-oauth2-secret.sh
Generates SealedSecret for Kanidm OAuth2 client credentials that can be safely committed to Git.

**Purpose:**
- Create encrypted OAuth2 secrets for GitOps workflows
- Used by OAuth2 proxies (Traefik dashboard, Longhorn UI, etc.)
- Enable secure secret management in Git repository
- Automate secret creation with consistent format

**Usage:**
```bash
./scripts/gen-kanidm-oauth2-secret.sh <client-id> <client-secret> <namespace>
```

**Output:**
- SealedSecret YAML that can be committed to Git
- Encrypted with cluster's public key
- Only decryptable by Sealed Secrets controller in the cluster

**Workflow:**
1. Create OAuth2 client in Kanidm
2. Run script with client credentials
3. Save output to appropriate directory
4. Commit SealedSecret to Git
5. Flux deploys and Sealed Secrets controller decrypts

## Best Practices

### Development Workflow
1. Make changes to Flux manifests
2. Run `./scripts/validate.sh` locally
3. Fix any validation errors
4. Review changes with `git diff`
5. Commit and push
6. CI validates automatically
7. Flux reconciles after merge to main

### Storage Maintenance
- Run cleanup script periodically (monthly recommended)
- Check Longhorn UI for storage usage trends
- Review PV status before running cleanup
- Monitor for recurring Released volumes (may indicate config issues)

### Secret Management
- Never commit plaintext secrets to Git
- Always use Sealed Secrets for sensitive data
- Use `gen-kanidm-oauth2-secret.sh` for OAuth2 credentials
- Rotate credentials regularly (quarterly recommended)
- Test secret decryption after committing
- Keep sealed-secrets controller public key backed up

## Troubleshooting

### Validation Failures
- Check YAML syntax and indentation
- Verify resource apiVersion matches installed CRDs
- Ensure all referenced resources exist
- Test Kustomize build manually: `kustomize build <directory>`

### Cleanup Issues
- Verify kubectl context is correct cluster
- Check PV status: `kubectl get pv`
- Ensure Longhorn is healthy
- Review pod logs if PVs won't delete

### Secret Generation
- Verify kubeseal is installed and configured
- Check sealed-secrets controller is running
- Ensure correct namespace in secret metadata
- Test with `kubeseal --validate` if available
