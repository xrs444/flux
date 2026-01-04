# Tdarr - Automated Media Transcoding and Organization

## Overview

Tdarr is an automated media library application for managing, transcoding, and organizing video files. It watches designated folders for new media files and processes them according to configured rules.

## Features

- **Automated Processing**: Watches ingest folders for new media files
- **Intelligent Transcoding**: Converts media to desired formats/codecs
- **Health Checking**: Scans libraries for corrupt or problem files
- **Distributed Processing**: Supports worker nodes for distributed transcoding
- **Plugin System**: Extensible with community and custom plugins
- **Metadata Handling**: Preserves or modifies file metadata
- **Storage Optimization**: Reduces file sizes while maintaining quality

## Architecture

### Storage Volumes

- **Config** (`/app/configs`): Tdarr configuration and database (10Gi Longhorn)
- **Server** (`/app/server`): Temporary transcoding workspace (100Gi Longhorn)
- **Media Ingest** (`/media/ingest`): Source folder for new media (NFS: `xsvr1:/zfs/media/ingest`)
- **Movies Output** (`/media/movies`): Processed movie files (NFS: `xsvr1:/zfs/media/movies`, shared with Jellyfin)
- **TV Shows Output** (`/media/tvshows`): Processed TV show files (NFS: `xsvr1:/zfs/media/tvshows`, shared with Jellyfin)

### Network Access

- **Web UI**: Port 8265 (accessible via `tdarr.xrs444.net`)
- **Server Port**: Port 8266 (for worker node connections)

## Configuration

### Initial Setup

1. Access the web UI at `https://tdarr.xrs444.net`
2. Complete initial configuration wizard
3. Configure libraries:
   - Source library: `/media/ingest`
   - Output for movies: `/media/movies`
   - Output for TV shows: `/media/tvshows`
4. Set up transcode/health check flows using plugins

### Recommended Plugins

- **Check File Health**: Scan for corrupt files
- **Remux Container**: Change container format without re-encoding
- **Transcode Video**: Convert to H.264/H.265/AV1
- **Normalize Audio**: Standardize audio levels
- **Clean Filenames**: Rename files based on metadata

### Media Workflow

1. **Ingest**: Place new media files in `/media/ingest` (NFS shared folder on xsvr1)
2. **Process**: Tdarr detects, transcodes, and checks files
3. **Output**: Processed files moved to `/media/movies` or `/media/tvshows` based on content type
4. **Access**: Jellyfin serves content directly from the same NFS shares

## Integration with Jellyfin

Tdarr shares NFS volumes with Jellyfin for seamless media delivery:

- **Movies**: Both access `xsvr1:/zfs/media/movies`
- **TV Shows**: Both access `xsvr1:/zfs/media/tvshows`

Processed media is immediately available in Jellyfin without copying or moving between storage systems.## Resource Requirements

- **CPU**: 500m request (bursts higher during transcoding)
- **Memory**: 2Gi request, 4Gi limit
- **Storage**:
  - 10Gi Longhorn for config
  - 100Gi Longhorn for temp workspace
  - NFS shares for media (managed by xsvr1 ZFS pool)

## Deployment

```bash
kubectl apply -k flux/apps/tdarr
```

## Monitoring

Check deployment status:

```bash
kubectl get pods -n tdarr
kubectl logs -n tdarr -l app=tdarr
```

## Notes

- Transcoding is CPU/GPU intensive - adjust resources as needed
- Consider adding GPU support for hardware acceleration
- Worker nodes can be deployed separately for distributed processing
- Default timezone set to America/Phoenix
- Runs as UID/GID 1000
