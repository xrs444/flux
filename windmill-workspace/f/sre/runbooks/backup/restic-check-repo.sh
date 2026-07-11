#!/bin/bash
set -euo pipefail

OUTPUT=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
  automation@xsvr2.lan "sudo /etc/restic-offsite-check" 2>&1) && STATUS="ok" || STATUS="failed"

if [ "$STATUS" = "ok" ]; then
  echo "restic check passed against sftp:restic@cmrnas.xrs444.net:/home/restic-xsvr2"
  echo "$OUTPUT"
else
  echo "restic check FAILED"
  echo "$OUTPUT"
  exit 1
fi
