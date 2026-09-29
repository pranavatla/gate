#!/bin/bash
set -euo pipefail

REGION="ap-south-1"
OUT="/opt/gate/app/.env"

get() {
  aws ssm get-parameter --region "$REGION" --name "/gate/prod/$1" \
    --with-decryption --query Parameter.Value --output text
}

ANTHROPIC=$(get ANTHROPIC_API_KEY)
OPENAI=$(get OPENAI_API_KEY)
GEMINI=$(get GEMINI_API_KEY)
PG=$(get POSTGRES_PASSWORD)
RO=$(get GATE_READONLY_PW)
GF=$(get GRAFANA_ADMIN_PW)
BEDROCK=$(get BEDROCK_API_KEY)

umask 077
{
  echo "ANTHROPIC_API_KEY=$ANTHROPIC"
  echo "OPENAI_API_KEY=$OPENAI"
  echo "GEMINI_API_KEY=$GEMINI"
  echo "POSTGRES_PASSWORD=$PG"
  echo "GATE_READONLY_PW=$RO"
  echo "GF_SECURITY_ADMIN_PASSWORD=$GF"
  echo "BEDROCK_API_KEY=$BEDROCK"
} > "$OUT.tmp"

mv "$OUT.tmp" "$OUT"
chmod 600 "$OUT"
echo "Wrote $OUT with $(wc -l < "$OUT") secrets"
