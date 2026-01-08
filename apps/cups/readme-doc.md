# CUPS - Common Unix Printing System

## Overview

CUPS (Common Unix Printing System) is the standard open-source printing system for Linux and Unix-like operating systems. It provides a portable printing layer with a web-based management interface.

## Features

- Web-based printer management interface
- Support for multiple printer protocols (IPP, LPD, SMB, etc.)
- Printer discovery and driver management
- Print job queue management
- User authentication and access control
- PDF printing support
- Network printer sharing

## Access

- **URL**: https://cups.xrs444.net
- **Default Admin**: admin/admin (change after first login)
- **Port**: 631 (IPP/HTTP)
- **LPD Port**: 515 (Line Printer Daemon)

## Storage

- **Data PVC**: 5Gi on Longhorn storage
- **Mount Paths**:
  - `/etc/cups` - Configuration
  - `/var/log/cups` - Logs
  - `/var/spool/cups` - Print job spool

## Resources

- **Requests**: 100m CPU, 256Mi memory
- **Limits**: 1000m CPU, 1Gi memory

## Configuration

The deployment uses the `olbat/cupsd` Docker image which provides a containerized CUPS server.

### Adding Printers

1. Access https://cups.xrs444.net
2. Navigate to Administration tab
3. Click "Add Printer"
4. Select your printer from discovered devices or add by URI
5. Configure printer driver and options
6. Set default options and access policies

### Printer Protocols Supported

- **IPP** (Internet Printing Protocol)
- **LPD** (Line Printer Daemon)
- **SMB** (Windows printer sharing)
- **HTTP** (Direct HTTP printing)
- **AppSocket/JetDirect** (Raw printing)

## Client Configuration

### Linux/macOS
```bash
# Add printer using CUPS client
lpadmin -p printer-name -E -v ipp://cups.xrs444.net:631/printers/printer-name
```

### Windows
1. Open "Printers & Scanners" in Settings
2. Add a printer
3. Select "Add a printer using TCP/IP"
4. Enter hostname: cups.xrs444.net
5. Port: 631
6. Protocol: Internet Printing Protocol (IPP)

## Security Notes

- Change default admin password immediately after deployment
- Configure authentication for printer access
- Use SSL/TLS for remote printer connections
- Restrict access via CUPS access control lists

## Monitoring

- View print jobs at https://cups.xrs444.net/jobs
- Check printer status at https://cups.xrs444.net/printers
- Review logs in the web interface or via kubectl logs

## Troubleshooting

### Printer Not Discovered
- Ensure printer is on the same network
- Check firewall rules allow port 631
- Verify printer supports IPP or supported protocol

### Print Jobs Stuck
- Check printer status in web interface
- Restart printer if needed
- Cancel and resubmit job
- Check logs for errors

## Links

- CUPS Documentation: https://www.cups.org/documentation.html
- Container Image: https://hub.docker.com/r/olbat/cupsd
