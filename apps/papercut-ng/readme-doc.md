# PaperCut NG - Print Management System

## Overview

PaperCut NG is the free version of PaperCut print management software. It provides print tracking, quotas, and monitoring for your network printers.

## Features

- Print job tracking and monitoring
- User-based print quotas
- Print cost tracking
- Printer usage statistics
- Web-based administration interface
- Support for various printer protocols

## Access

- **URL**: https://papercut.xrs444.net
- **Default Admin**: admin/admin (change after first login)

## Storage

- **Data PVC**: 10Gi on Longhorn storage
- **Mount Path**: /app/data

## Resources

- **Requests**: 200m CPU, 512Mi memory
- **Limits**: 2000m CPU, 2Gi memory

## Ports

- **9191**: HTTP web interface
- **9192**: HTTPS web interface

## Configuration

The deployment uses the official PaperCut NG Docker image. Configuration is persisted to the data volume.

## Notes

- Initial setup wizard runs on first access
- Configure printers through the web interface
- Set up user accounts and print quotas as needed
- Monitor print jobs and costs through the dashboard
