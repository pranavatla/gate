#!/bin/bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "ALTER ROLE gate_readonly WITH PASSWORD '${GATE_READONLY_PW}';"
