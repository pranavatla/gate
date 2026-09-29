#!/bin/bash
set -euo pipefail

BUCKET="gate-backups-361739112666"
LATEST=$(aws s3 ls "s3://$BUCKET/postgres/" --region ap-south-1 | sort | tail -1 | awk '{print $4}')
echo "Restoring latest backup: $LATEST"
aws s3 cp "s3://$BUCKET/postgres/$LATEST" /tmp/restore.sql.gz --region ap-south-1 --only-show-errors

docker rm -f gate-restore-test >/dev/null 2>&1 || true
docker run -d --name gate-restore-test --memory 256m \
  -e POSTGRES_PASSWORD=restoretest pgvector/pgvector:pg17 >/dev/null

until [ "$(docker logs gate-restore-test 2>&1 | grep -c 'ready to accept connections')" -ge 2 ]; do
  sleep 1
done

gunzip -c /tmp/restore.sql.gz | docker exec -i gate-restore-test \
  psql -v ON_ERROR_STOP=1 -q -U postgres -d postgres >/dev/null

Q="SELECT (SELECT count(*) FROM tenants) AS tenants,
          (SELECT count(*) FROM api_keys) AS api_keys,
          (SELECT count(*) FROM model_prices) AS prices,
          (SELECT count(*) FROM usage_events) AS events;"

echo "Production:"
(cd /opt/gate/app && docker compose exec -T gate-postgres psql -U gate -d gate -c "$Q")
echo "Restored copy:"
docker exec gate-restore-test psql -U postgres -d postgres -c "$Q"

docker rm -f gate-restore-test >/dev/null
rm -f /tmp/restore.sql.gz
echo "Restore test finished; scratch database removed."
