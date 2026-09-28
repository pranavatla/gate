provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "gate"
      ManagedBy = "terraform"
    }
  }
}
