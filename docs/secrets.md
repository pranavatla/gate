# gate: production secrets (names only, never values)

All stored in AWS SSM Parameter Store, region ap-south-1, type SecureString
(encrypted with the AWS-managed aws/ssm KMS key). Created with the AWS CLI,
never by Terraform, so values never enter Terraform state.

| Parameter                          | Used by              | How created          |
|------------------------------------|----------------------|----------------------|
| /gate/prod/ANTHROPIC_API_KEY       | gateway              | pasted via read -s   |
| /gate/prod/OPENAI_API_KEY          | gateway              | pasted via read -s   |
| /gate/prod/GEMINI_API_KEY          | gateway              | pasted via read -s   |
| /gate/prod/BEDROCK_API_KEY         | gateway              | pasted via read -s   |
| /gate/prod/POSTGRES_PASSWORD       | postgres, gateway    | openssl rand -hex 24 |
| /gate/prod/GATE_READONLY_PW        | postgres, grafana    | openssl rand -hex 24 |
| /gate/prod/GRAFANA_ADMIN_PW        | grafana              | openssl rand -hex 24 |

## Rotate a secret
aws ssm put-parameter --name /gate/prod/<NAME> --type SecureString --value "<new>" --overwrite
Then, on the host (through SSM), re-render the secrets file and recreate the containers that use it.
A plain restart is not enough: containers read `/opt/gate/app/.env`, which only `render-env.sh` rewrites.

    sudo bash /opt/gate/app/render-env.sh
    cd /opt/gate/app && sudo docker compose up -d

## Read the Grafana admin password when needed
aws ssm get-parameter --name /gate/prod/GRAFANA_ADMIN_PW --with-decryption --query Parameter.Value --output text
