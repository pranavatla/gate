terraform {
  required_version = ">= 1.15"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region = "ap-south-1"
  default_tags {
    tags = {
      Project   = "atla-chatbot"
      ManagedBy = "terraform"
    }
  }
}

variable "reserved_concurrency" {
  description = "Maximum simultaneous runs; -1 means no reservation"
  type        = number
  default     = -1
}

variable "extra_origins" {
  description = "Extra browser origins allowed temporarily, e.g. localhost for testing"
  type        = list(string)
  default     = []
}

data "aws_caller_identity" "me" {}

locals {
  name      = "atla-chatbot"
  key_param = "/atla-chatbot/prod/GATE_API_KEY"
}

data "archive_file" "bundle" {
  type        = "zip"
  output_path = "${path.module}/build/bundle.zip"

  source {
    content  = file("${path.module}/../lambda/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../facts.md")
    filename = "facts.md"
  }
}

resource "aws_cloudwatch_log_group" "fn" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_iam_role" "fn" {
  name = "${local.name}-fn"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "fn" {
  name = "read-own-key-write-own-logs"
  role = aws_iam_role.fn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadOwnGatewayKey"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:ap-south-1:${data.aws_caller_identity.me.account_id}:parameter${local.key_param}"
      },
      {
        Sid      = "WriteOwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.fn.arn}:*"
      }
    ]
  })
}

resource "aws_lambda_function" "fn" {
  function_name                  = local.name
  role                           = aws_iam_role.fn.arn
  runtime                        = "python3.13"
  architectures                  = ["arm64"]
  handler                        = "handler.handler"
  filename                       = data.archive_file.bundle.output_path
  source_code_hash               = data.archive_file.bundle.output_base64sha256
  memory_size                    = 256
  timeout                        = 30
  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      GATE_URL   = "https://gate.atla.in"
      GATE_MODEL = "bedrock/global.amazon.nova-2-lite-v1:0"
      KEY_PARAM  = local.key_param
    }
  }

  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy.fn]
}

resource "aws_lambda_function_url" "fn" {
  function_name      = aws_lambda_function.fn.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = concat(["https://atla.in", "https://www.atla.in"], var.extra_origins)
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
    max_age       = 86400
  }
}

resource "aws_lambda_permission" "public_url" {
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.fn.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "terraform_data" "invoke_via_url_only" {
  triggers_replace = [aws_lambda_function.fn.arn]

  provisioner "local-exec" {
    command = "aws lambda add-permission --function-name ${aws_lambda_function.fn.function_name} --statement-id InvokeViaFunctionUrlOnly --action lambda:InvokeFunction --principal '*' --invoked-via-function-url --region ap-south-1"
  }
}

output "chat_url" {
  value = aws_lambda_function_url.fn.function_url
}
