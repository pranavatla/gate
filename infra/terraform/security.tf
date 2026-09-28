resource "aws_security_group" "host" {
  name        = "gate-host"
  description = "gate.atla.in host: HTTPS in, web out only"
  vpc_id      = aws_vpc.gate.id

  tags = { Name = "gate-host-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "https_in" {
  security_group_id = aws_security_group.host.id
  description       = "HTTPS to Caddy from anywhere"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "http_in" {
  security_group_id = aws_security_group.host.id
  description       = "HTTP for TLS certificate issuance and redirect to HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "https_out" {
  security_group_id = aws_security_group.host.id
  description       = "HTTPS out: LLM providers, ECR, SSM, S3, Lets Encrypt"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "http_out" {
  security_group_id = aws_security_group.host.id
  description       = "HTTP out: OS package repositories"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}
