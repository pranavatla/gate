#!/bin/bash
set -uo pipefail

ROUTE="bedrock/global.amazon.nova-2-lite-v1:0"
# set|prompt pairs. gate-chatbot@live = the page chatbot's exact production instructions and facts.
JOBS="atla-chatbot/facts-core|atla-chatbot@6
atla-chatbot/facts-guard-v2|atla-chatbot@6
gate-chatbot/gate-page-v1|gate-chatbot@live"

cd /opt/gate/app

EVAL_GATE_KEY=$(aws ssm get-parameter --region ap-south-1 \
  --name /gate/prod/EVAL_GATE_KEY --with-decryption \
  --query Parameter.Value --output text) || { echo "could not read EVAL_GATE_KEY"; exit 1; }
export EVAL_GATE_KEY

RUN="docker compose exec -T -e EVAL_GATE_KEY -e GATE_URL=http://localhost:8000 gateway python -m app"

# Cases are immutable and the import skips existing ones, so this is safe every night.
$RUN.evalimport gate-chatbot/gate-page-v1 evals/gate-page-v1.jsonl || echo "warning: could not import gate-page-v1"

FAILED=0
while IFS='|' read -r SET PROMPT; do
  echo "=== $SET ($PROMPT) ==="
  # evalrun compares its own run ID and propagates alert exit codes.
  $RUN.evalrun "$SET" "$ROUTE" "$PROMPT" || FAILED=1
done <<< "$JOBS"
exit $FAILED
