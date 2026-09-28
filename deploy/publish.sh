#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

BUCKET=$(terraform -chdir=infra/terraform output -raw backup_bucket)
DEST="s3://$BUCKET/deploy"

aws s3 sync deploy/app/    "$DEST/app/"     --delete
aws s3 sync infra/grafana/ "$DEST/grafana/" --delete
aws s3 sync db/            "$DEST/db-init/" --delete --exclude "*" --include "00*.sql" --include "seed_prices.sql"
aws s3 cp   deploy/db-init/zz_readonly_password.sh "$DEST/db-init/zz_readonly_password.sh"

echo "Published to $DEST"
aws s3 ls "$DEST/" --recursive | awk '{print $4}'
