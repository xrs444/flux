# Manyfold - 3D Print File Manager

## Overview
Manyfold is a self-hosted digital asset manager specifically designed for 3D printing files. It helps organize, tag, search, and visualize STL files and other 3D model formats.

## Configuration

### Storage
- **Data PVC**: 10Gi for storing 3D model files and assets
- **Database PVC**: 5Gi for PostgreSQL database

### Database
Uses PostgreSQL 16 (Alpine) as a sidecar container within the same pod for simplified deployment and backup.

### Access
- **URL**: https://manyfold.xrs444.net
- **Port**: 3214

### Environment Variables
- `TZ`: America/Phoenix
- `DATABASE_ADAPTER`: postgresql
- `DATABASE_HOST`: localhost (sidecar)
- `DATABASE_PORT`: 5432
- `DATABASE_NAME`: manyfold
- `DATABASE_USER`: manyfold
- `DATABASE_PASSWORD`: manyfold (change in production)
- `SECRET_KEY_BASE`: changeme-generate-a-secure-key (must be changed)

## Security Notes

⚠️ **IMPORTANT**: Before deploying to production:
1. Generate a secure `SECRET_KEY_BASE` using: `openssl rand -hex 64`
2. Change the database password from default
3. Consider using Kubernetes Secrets for sensitive values

## Resources
- **Manyfold Container**:
  - Requests: 100m CPU, 256Mi memory
  - Limits: 2000m CPU, 2Gi memory
- **PostgreSQL Container**:
  - Requests: 100m CPU, 128Mi memory
  - Limits: 1000m CPU, 512Mi memory

## Health Checks
- **Liveness Probe**: HTTP GET /health on port 3214
  - Initial delay: 60s, Period: 10s
- **Readiness Probe**: HTTP GET /health on port 3214
  - Initial delay: 30s, Period: 5s

## Features
- Organize 3D printing files (STL, OBJ, etc.)
- Tag and categorize models
- Built-in 3D model viewer
- Search and filter capabilities
- Multi-library support

## Links
- Project: https://github.com/manyfold3d/manyfold
- Documentation: https://docs.manyfold.app/
- Container: ghcr.io/manyfold3d/manyfold
