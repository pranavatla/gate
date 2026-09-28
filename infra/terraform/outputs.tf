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

output "ecr_repository_url" {
  value = aws_ecr_repository.gate.repository_url
}

output "backup_bucket" {
  value = aws_s3_bucket.backups.bucket
}

output "host_role_arn" {
  value = aws_iam_role.host.arn
}

output "host_instance_profile" {
  value = aws_iam_instance_profile.host.name
}

output "instance_id" {
  value = aws_instance.host.id
}

output "public_ip" {
  value = aws_eip.host.public_ip
}