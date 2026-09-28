data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "gate" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "gate-vpc" }
}

resource "aws_internet_gateway" "gate" {
  vpc_id = aws_vpc.gate.id

  tags = { Name = "gate-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.gate.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false

  tags = { Name = "gate-public-a" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.gate.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gate.id
  }

  tags = { Name = "gate-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_default_security_group" "locked" {
  vpc_id = aws_vpc.gate.id

  tags = { Name = "gate-default-sg-locked" }
}
