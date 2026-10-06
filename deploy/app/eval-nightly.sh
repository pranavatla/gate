#!/bin/bash
set -uo pipefail

SETS="atla-chatbot/facts-core atla-chatbot/facts-guard-v2"
ROUTE="bedrock/global.amazon.nova-2-lite-v1:0"
PROMPT="atla-chatbot@6"

cd /opt/gate/app

EVAL_GATE_KEY=$(aws ssm get-parameter --region ap-south-1 \
  --name /gate/prod/EVAL_GATE_KEY --with-decryption \
  --query Parameter.Value --output text) || { echo "could not read EVAL_GATE_KEY"; exit 1; }
export EVAL_GATE_KEY

RUN="docker compose exec -T -e EVAL_GATE_KEY -e GATE_URL=http://localhost:8000 gateway python -m app"

FAILED=0
for SET in $SETS; do
  echo "=== $SET ==="
  if $RUN.evalrun "$SET" "$ROUTE" "$PROMPT"; then
    $RUN.evalcheck latest || FAILED=1
  else
    FAILED=1
  fi
done
exit $FAILED
