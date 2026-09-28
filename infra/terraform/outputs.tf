output "vpc_id" {
  value = aws_vpc.gate.id
}

output "public_subnet_id" {
  value = aws_subnet.public.id
}

output "host_security_group_id" {
  value = aws_security_group.host.id
}

output "availability_zone" {
  value = aws_subnet.public.availability_zone
}
