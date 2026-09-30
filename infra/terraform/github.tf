# GitHub Actions deploys on every push to main (.github/workflows/deploy.yml).
# It signs in with a short-lived OIDC token: no AWS keys are stored in GitHub.
# The OIDC provider already exists in this account (shared with other projects), so it is read, not managed.

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only workflows running on main of this repository can deploy.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:pranavatla@40049243/gate@1395108469:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "gate-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "EcrPushGateImageOnly"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:DescribeImages", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload",
      "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.gate.arn]
  }
  statement {
    sid       = "ListDeployBundle"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.backups.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["deploy/", "deploy/*"]
    }
  }
  # Publishing only touches deploy/; database backups under postgres/ stay out of reach.
  statement {
    sid       = "WriteDeployBundle"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.backups.arn}/deploy/*"]
  }
  statement {
    sid     = "RunDeployCommandOnHost"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.host.arn,
      "arn:aws:ssm:${var.region}::document/AWS-RunShellScript",
    ]
  }
  statement {
    sid       = "ReadDeployCommandResult"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "gate-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
