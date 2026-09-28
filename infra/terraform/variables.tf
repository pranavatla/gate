variable "region" {
  description = "AWS region for all gate resources"
  type        = string
  default     = "ap-south-1"
}

variable "alert_email" {
  description = "Email address that receives budget alerts"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly AWS spend limit for the gate project"
  type        = number
  default     = 20
}

variable "vpc_cidr" {
  description = "Address range for the gate VPC"
  type        = string
  default     = "10.40.0.0/16"
}

variable "public_subnet_cidr" {
  description = "Address range for the single public subnet"
  type        = string
  default     = "10.40.1.0/24"
}
