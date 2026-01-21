# BorgWarehouse - Borg Backup Repository Manager

BorgWarehouse provides a web UI and SSH server for managing BorgBackup repositories across multiple devices.

## Architecture

- **Web UI**: Accessible at `https://borgwarehouse.xrs444.net`
- **SSH Server**: Port 2222 (configured in BorgWarehouse)
- **Storage**: NFS mount from xsvr1 at `/zfs/devicebackups`
- **Config**: Longhorn PVC for application data

## Deployment

The deployment includes:
- Kubernetes namespace: `borgwarehouse`
- NFS PV/PVC for backup storage (10Ti from xsvr1)
- Longhorn PVC for configuration (1Gi)
- Traefik IngressRoute for HTTPS access

## Initial Setup

1. **Deploy to Kubernetes**:
   ```bash
   cd flux/apps/borgwarehouse
   kubectl apply -k .
   ```

2. **Access Web UI**:
   - Navigate to `https://borgwarehouse.xrs444.net`
   - Create initial admin account

3. **Create Repository**:
   - Log in to BorgWarehouse UI
   - Create a new repository for each device/host
   - Note the SSH connection details and passphrase

## Client Configuration (NixOS)

### Per-Host Configuration Example

Create a host-specific configuration file:

```nix
# nix/hosts/nixos/xcomm1/default.nix (or similar)
{
  services.borgbackup-client = {
    enable = true;
    repository = "ssh://username@borgwarehouse.xrs444.net:2222/repos/xcomm1";

    paths = [
      "/home"
      "/etc"
      "/var/lib"
    ];

    exclude = [
      "*.cache"
      "*/cache/*"
      "*/.cache/*"
      "*/Cache/*"
      "*/.local/share/Trash"
      "*/node_modules"
    ];

    schedule = "daily";

    prune.keep = {
      daily = 7;
      weekly = 4;
      monthly = 6;
      yearly = 1;
    };
  };

  # Borg passphrase secret
  sops.secrets."borg-passphrase" = {
    sopsFile = ../../../secrets/borg-xcomm1.yaml;
    key = "passphrase";
  };
}
```

### Setting Up Secrets

1. **Generate passphrase** (use the one from BorgWarehouse):
   ```bash
   cd nix/secrets
   cat > borg-hostname.yaml <<EOF
   passphrase: YOUR_BORGWAREHOUSE_PASSPHRASE_HERE
   EOF

   # Encrypt with sops
   sops -e -i borg-hostname.yaml
   ```

2. **Initialize repository** (first time only):
   ```bash
   # SSH into the host
   sudo borg init --encryption=repokey-blake2 ssh://username@borgwarehouse.xrs444.net:2222/repos/hostname
   ```

3. **Test backup**:
   ```bash
   sudo systemctl start borgbackup-job-hostname
   sudo systemctl status borgbackup-job-hostname
   ```

## Backup Schedule

Backups run automatically based on the `schedule` parameter:
- `daily`: Once per day
- `hourly`: Once per hour
- `*-*-* 02:00:00`: Custom systemd timer format

View backup status:
```bash
sudo systemctl list-timers | grep borg
```

## Monitoring

Check backup logs:
```bash
sudo journalctl -u borgbackup-job-hostname -f
```

List backups:
```bash
sudo borg list ssh://username@borgwarehouse.xrs444.net:2222/repos/hostname
```

## Storage

- **Backend**: NFS export from xsvr1:/zfs/devicebackups
- **Capacity**: 10Ti (adjustable)
- **Access**: ReadWriteMany (shared across multiple BorgWarehouse pods)

## Security Notes

- All backups are encrypted with repokey-blake2
- Passphrases stored in sops-encrypted secrets
- SSH keys managed by BorgWarehouse
- Repository access controlled per-user in BorgWarehouse UI

## Troubleshooting

### Connection Issues

Check SSH connectivity:
```bash
ssh -p 2222 username@borgwarehouse.xrs444.net
```

### Storage Issues

Check NFS mount in pod:
```bash
kubectl exec -n borgwarehouse deployment/borgwarehouse -- df -h /repos
```

### Permission Issues

Ensure the NFS export has correct permissions:
```bash
# On xsvr1
ls -la /zfs/devicebackups
```

## Restoration

To restore from backup:
```bash
# List archives
sudo borg list ssh://username@borgwarehouse.xrs444.net:2222/repos/hostname

# Extract specific archive
sudo borg extract ssh://username@borgwarehouse.xrs444.net:2222/repos/hostname::archive-name

# Mount archive for browsing
sudo mkdir /mnt/borg-mount
sudo borg mount ssh://username@borgwarehouse.xrs444.net:2222/repos/hostname::archive-name /mnt/borg-mount
# Browse files...
sudo borg umount /mnt/borg-mount
```
