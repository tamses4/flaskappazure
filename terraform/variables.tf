variable "resource_group_name" {
  description = "Nom du resource group"
  default     = "rg-monapp-prod"
}

variable "location" {
  description = "Région Azure"
  default     = "francecentral"
}

variable "admin_username" {
  description = "Nom d'utilisateur admin SSH"
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Chemin vers la clé SSH publique"
  default     = "~/.ssh/id_rsa.pub"
}

variable "vm_size" {
  description = "Taille des VMs"
  default     = "Standard_B2s"
}
