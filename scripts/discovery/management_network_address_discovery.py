from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.utils import set_timestamp
from automation_core.networking import ping_host, nmap_scan, make_api_request
from automation_core.reporting import write_list_to_csv
import os
import csv
import json
import ipaddress
from datetime import datetime
import concurrent.futures


class ManagementNetworkAddressDiscovery(BaseTask):
    name = "management_network_address_discovery"
    description = "Discover IP addresses in management networks and update IPAM"
    category = "discovery"
    dependencies = ["IPAM"]
    default_schedule = "0 6 * * 0"  # Weekly on Sunday at 6 AM
    max_runtime = 3600
    
    def __init__(self):
        super().__init__()
        self.output_dir = "/var/automation_file/discovery"
        self.max_workers = 100
        
    def execute(self):
        try:
            self.log("Starting management network address discovery")
            
            # Get management networks from IPAM
            mgmt_networks = self._get_management_networks()
            if not mgmt_networks:
                self.log("No management networks found", level="WARNING")
                return {"status": "skipped", "reason": "no_networks"}
            
            discovered_addresses = []
            total_addresses = 0
            
            # Process each management network
            for network in mgmt_networks:
                try:
                    self.log(f"Scanning management network: {network['network']}")
                    
                    # Discover active addresses in network
                    active_addresses = self._discover_network_addresses(network)
                    
                    for addr_info in active_addresses:
                        # Enrich with additional information
                        enriched_info = self._enrich_address_info(addr_info, network)
                        if enriched_info:
                            discovered_addresses.append(enriched_info)
                    
                    total_addresses += len(active_addresses)
                    self.log(f"Found {len(active_addresses)} active addresses in {network['network']}")
                    
                except Exception as e:
                    self.log(f"Error scanning network {network['network']}: {e}", level="ERROR")
            
            # Update IPAM with discovered addresses
            imported_addresses = self._import_addresses_to_ipam(discovered_addresses)
            
            # Generate discovery report
            report_file = self._generate_discovery_report(discovered_addresses)
            
            self.log(f"Discovery complete. Found: {total_addresses}, Imported: {imported_addresses}")
            
            return {
                "status": "success",
                "networks_scanned": len(mgmt_networks),
                "addresses_discovered": total_addresses,
                "addresses_imported": imported_addresses,
                "report_file": report_file,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"Management network address discovery failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_management_networks(self):
        """Get list of management networks from IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            response = make_api_request(
                method="GET",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/networks/",
                params={"network_type": "management"},
                auth=(ipam_user, ipam_pass),
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                networks = response.get("data", [])
                self.log(f"Retrieved {len(networks)} management networks")
                return networks
            
            return []
            
        except Exception as e:
            self.log(f"Error getting management networks: {e}", level="ERROR")
            return []
    
    def _discover_network_addresses(self, network_info):
        """Discover active IP addresses in a network using parallel scanning"""
        network = network_info['network']
        discovered_addresses = []
        
        try:
            # Create network object
            net = ipaddress.IPv4Network(network, strict=False)
            
            # Skip networks that are too large (> /22)
            if net.prefixlen < 22:
                self.log(f"Network {network} too large, skipping detailed scan")
                return []
            
            # Get all host IPs in network
            host_ips = [str(ip) for ip in net.hosts()]
            
            # Parallel ping scan
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit ping tasks
                future_to_ip = {
                    executor.submit(self._ping_and_gather_info, ip): ip
                    for ip in host_ips
                }
                
                # Collect results
                for future in concurrent.futures.as_completed(future_to_ip):
                    ip = future_to_ip[future]
                    try:
                        result = future.result()
                        if result:
                            discovered_addresses.append(result)
                    except Exception as e:
                        self.log(f"Error scanning {ip}: {e}", level="DEBUG")
            
            return discovered_addresses
            
        except Exception as e:
            self.log(f"Error discovering addresses in {network}: {e}", level="ERROR")
            return []
    
    def _ping_and_gather_info(self, ip_address):
        """Ping an IP and gather basic information if reachable"""
        try:
            # Ping test
            is_reachable, response_time = ping_host(ip_address, timeout=2)
            
            if is_reachable:
                # Try to get hostname via reverse DNS
                try:
                    import socket
                    hostname = socket.gethostbyaddr(ip_address)[0]
                except:
                    hostname = None
                
                return {
                    'ip_address': ip_address,
                    'hostname': hostname,
                    'response_time_ms': response_time,
                    'status': 'active',
                    'discovered_timestamp': set_timestamp()
                }
            
            return None
            
        except Exception as e:
            return None
    
    def _enrich_address_info(self, addr_info, network_info):
        """Enrich discovered address with network context"""
        try:
            enriched = {
                **addr_info,
                'network': network_info['network'],
                'network_description': network_info.get('description'),
                'site': network_info.get('site'),
                'vlan_id': network_info.get('vlan_id'),
                'discovery_source': 'mgmt_network_scan'
            }
            
            return enriched
            
        except Exception as e:
            self.log(f"Error enriching address info: {e}", level="ERROR")
            return addr_info
    
    def _import_addresses_to_ipam(self, discovered_addresses):
        """Import discovered addresses to IPAM"""
        imported_count = 0
        
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            for addr_info in discovered_addresses:
                try:
                    # Check if address already exists
                    existing_response = make_api_request(
                        method="GET",
                        url=f"{os.getenv('IPAM_BASE_URL')}/api/addresses/",
                        params={"ip_address": addr_info['ip_address']},
                        auth=(ipam_user, ipam_pass),
                        timeout=10
                    )
                    
                    if existing_response and existing_response.get("data"):
                        # Update existing address
                        address_id = existing_response["data"][0]["id"]
                        update_payload = {
                            "hostname": addr_info.get('hostname'),
                            "status": "discovered",
                            "last_seen": addr_info['discovered_timestamp'],
                            "response_time": addr_info.get('response_time_ms')
                        }
                        
                        response = make_api_request(
                            method="PUT",
                            url=f"{os.getenv('IPAM_BASE_URL')}/api/addresses/{address_id}/",
                            auth=(ipam_user, ipam_pass),
                            json=update_payload,
                            timeout=10
                        )
                        
                        if response and response.get("status_code") == 200:
                            imported_count += 1
                    else:
                        # Create new address record
                        create_payload = {
                            "ip_address": addr_info['ip_address'],
                            "hostname": addr_info.get('hostname'),
                            "network": addr_info.get('network'),
                            "status": "discovered",
                            "discovery_source": addr_info['discovery_source'],
                            "discovered_date": addr_info['discovered_timestamp']
                        }
                        
                        response = make_api_request(
                            method="POST",
                            url=f"{os.getenv('IPAM_BASE_URL')}/api/addresses/",
                            auth=(ipam_user, ipam_pass),
                            json=create_payload,
                            timeout=10
                        )
                        
                        if response and response.get("status_code") == 201:
                            imported_count += 1
                    
                except Exception as e:
                    self.log(f"Error importing {addr_info['ip_address']}: {e}", level="ERROR")
            
            return imported_count
            
        except Exception as e:
            self.log(f"Error importing addresses to IPAM: {e}", level="ERROR")
            return 0
    
    def _generate_discovery_report(self, discovered_addresses):
        """Generate CSV report of discovered addresses"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"{self.output_dir}/mgmt_network_discovery_{timestamp}.csv"
            
            if discovered_addresses:
                write_list_to_csv(discovered_addresses, report_file)
                self.log(f"Discovery report generated: {report_file}")
                return report_file
            
            return None
            
        except Exception as e:
            self.log(f"Error generating discovery report: {e}", level="ERROR")
            return None


# Task registration for auto-discovery
task_class = ManagementNetworkAddressDiscovery