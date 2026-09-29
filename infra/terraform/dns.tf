data "aws_route53_zone" "atla" {
  name         = "atla.in"
  private_zone = false
}

resource "aws_route53_record" "gate" {
  zone_id = data.aws_route53_zone.atla.zone_id
  name    = "gate.atla.in"
  type    = "A"
  ttl     = 300
  records = [aws_eip.host.public_ip]
}
