#!/bin/bash
set -euo pipefail

SET="atla-chatbot/facts-core"
ROUTE="bedrock/global.amazon.nova-2-lite-v1:0"
PROMPT="atla-chatbot@1"

cd /opt/gate/app

EVAL_GATE_KEY=$(aws ssm get-parameter --region ap-south-1 \
  --name /gate/prod/EVAL_GATE_KEY --with-decryption \
  --query Parameter.Value --output text)
export EVAL_GATE_KEY

RUN="docker compose exec -T -e EVAL_GATE_KEY -e GATE_URL=http://localhost:8000 gateway python -m app"

$RUN.evalrun "$SET" "$ROUTE" "$PROMPT"
$RUN.evalcheck latest
