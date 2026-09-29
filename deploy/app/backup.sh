#!/bin/bash
set -euo pipefail

BUCKET="gate-backups-361739112666"
STAMP=$(date -u +%Y-%m-%dT%H%M%SZ)
FILE="/tmp/gate-$STAMP.sql.gz"

cd /opt/gate/app
docker compose exec -T gate-postgres pg_dump -U gate -d gate --no-owner --no-privileges | gzip -9 > "$FILE"

SIZE=$(stat -c %s "$FILE")
if [ "$SIZE" -lt 1000 ]; then
  echo "ERROR: backup suspiciously small ($SIZE bytes), not uploading"
  rm -f "$FILE"
  exit 1
fi

aws s3 cp "$FILE" "s3://$BUCKET/postgres/$STAMP.sql.gz" --region ap-south-1 --only-show-errors
rm -f "$FILE"
echo "Backup uploaded: postgres/$STAMP.sql.gz ($SIZE bytes)"
