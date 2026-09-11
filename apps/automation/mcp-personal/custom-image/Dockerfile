# Custom image for the per-identity personal-scope MCP servers
# (mcp-vikunja-{t,s}, mcp-caldav-{t,s}). One image, four Deployments — the
# only difference between them is the supergateway --stdio command and the
# credential env block (see ../deployment-mcp-*.yaml).
#
# Why a custom image rather than `npx -y <pkg>` on a stock node image:
# supergateway's stateless streamableHttp gateway spawns the --stdio command
# INSIDE the POST handler (src/gateways/stdioToStatelessStreamableHttp.ts in
# supercorp-ai/supergateway), i.e. once per MCP tool call — not once per pod.
# `npx -y` would put an npm registry round-trip in the hot path of every
# conversation turn, and would silently float `latest` past the Renovate
# review gate ../../../../renovate.json already demands for Hermes-facing
# MCP servers. Installing globally at build time makes each spawn a bare
# exec of a pinned binary.
#
# Versions below are tracked by the mcp-personal-image-npm regex manager in
# renovate.json — bump via PR, never edit `latest` in.
#
# tini as PID 1: supergateway spawns children with { shell: true }. Node
# reaps its own direct children, but tini guarantees no orphaned `sh`
# survives a container-level signal — same reason `docker run --init`
# exists; there is no Kubernetes-native equivalent.
#
# curl: used for in-pod debugging (kubectl exec ... curl .../healthz) and
# by the optional credential-preflight initContainer in the Deployments.
FROM node:22-alpine

RUN apk add --no-cache tini curl

RUN npm install -g --omit=dev \
      supergateway@3.4.3 \
      caldav-mcp@0.10.0 \
      @democratize-technology/vikunja-mcp@0.2.0 \
  && npm cache clean --force

USER node
WORKDIR /home/node

ENTRYPOINT ["/sbin/tini", "--"]
