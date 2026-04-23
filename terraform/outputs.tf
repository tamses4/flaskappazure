output "bastion_public_ip" {
  description = "IP publique du Bastion (point d'entrée SSH)"
  value       = azurerm_public_ip.bastion_ip.ip_address
}

output "lb_public_ip" {
  description = "IP publique du Load Balancer Frontend (accès utilisateurs)"
  value       = azurerm_public_ip.lb_public_ip.ip_address
}

output "lb_internal_ip" {
  description = "IP privée du Load Balancer Backend"
  value       = "10.0.2.10"
}

output "vm_frontend_private_ip" {
  description = "IP privée de la VM Frontend"
  value       = azurerm_network_interface.nic_frontend.private_ip_address
}

output "vm_backend_private_ips" {
  description = "IPs privées des VMs Backend"
  value       = azurerm_network_interface.nic_backend[*].private_ip_address
}
