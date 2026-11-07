#!/usr/bin/env bash
# Installs the exact validator toolchain versions that validate.sh and
# .github/workflows/test.yml expect, into ./.validator-bin. Keeps local runs
# reproducible with CI instead of whatever yq/kustomize/kubeconform happens
# to already be on PATH (the most common mismatch: Python yq vs mikefarah's
# Go yq — only the latter supports `yq e`/`yq -o` the way validate.sh uses it).
#
# Versions here MUST match .github/workflows/test.yml's action `version:`
# inputs and validate.sh's CRD_SCHEMA_VERSION — bump all three together.
#
# Usage: ./scripts/install-validator-toolchain.sh
#   then: PATH="$PWD/.validator-bin:$PATH" ./scripts/validate.sh

set -euo pipefail

YQ_VERSION="v4.54.2"
KUSTOMIZE_VERSION="v5.8.3"
KUBECONFORM_VERSION="v0.8.0"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$SCRIPT_DIR/../.validator-bin"
mkdir -p "$BIN_DIR"

case "$(uname -s)_$(uname -m)" in
  Linux_x86_64) OS=linux; ARCH=amd64 ;;
  Linux_aarch64) OS=linux; ARCH=arm64 ;;
  Darwin_x86_64) OS=darwin; ARCH=amd64 ;;
  Darwin_arm64) OS=darwin; ARCH=arm64 ;;
  *) echo "Unsupported platform: $(uname -s) $(uname -m)" >&2; exit 1 ;;
esac

echo "Installing yq ${YQ_VERSION} ..."
curl -sfL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_${OS}_${ARCH}" \
  -o "$BIN_DIR/yq"
chmod +x "$BIN_DIR/yq"

echo "Installing kustomize ${KUSTOMIZE_VERSION} ..."
curl -sfL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_${OS}_${ARCH}.tar.gz" \
  | tar xz -C "$BIN_DIR" kustomize

echo "Installing kubeconform ${KUBECONFORM_VERSION} ..."
curl -sfL "https://github.com/yannh/kubeconform/releases/download/${KUBECONFORM_VERSION}/kubeconform-${OS}-${ARCH}.tar.gz" \
  | tar xz -C "$BIN_DIR" kubeconform

echo "Installed to $BIN_DIR:"
"$BIN_DIR/yq" --version
"$BIN_DIR/kustomize" version
"$BIN_DIR/kubeconform" -v
