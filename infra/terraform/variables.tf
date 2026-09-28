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
