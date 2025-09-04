from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.git_ops import pull_git_repository
from automation_core.utils import set_timestamp, get_file_hash
from automation_core.networking import make_api_request
from automation_core.reporting import write_list_to_csv
import os
import csv
import json
import ipaddress
from datetime import datetime


class PaloAltoPanoramaSviDiscovery(BaseTask):
    name = "palo_alto_panorama_svi_discovery"
    description = "Import discovered subnets and VLAN interface addresses from Palo Alto Panorama"
    category = "discovery"
    dependencies = ["IPAM"]
    default_schedule = "0 4 * * 3"  # Weekly on Wednesday at 4 AM
    max_runtime = 2400
    
    def __init__(self):
        super().__init__()
        self.git_dir = "/app/git-repos/palo-panorama-discovery"
        self.seed_dir = f"{self.git_dir}/seed-files"
        self.hash_file = "/var/automation_file/discovery/palo_panorama_hash.txt"
        self.output_dir = "/var/automation_file/discovery"
        
    def execute(self):
        try:
            self.log("Starting Palo Alto Panorama SVI discovery")
            
            # Pull latest discovery data from Git
            pull_result = pull_git_repository(self.git_dir)
            self.log(f"Git pull result: {pull_result}")
            
            # Get discovery files
            discovery_files = self._get_discovery_files()
            if not discovery_files:
                self.log("No discovery files found", level="WARNING")
                return {"status": "skipped", "reason": "no_discovery_files"}
            
            processed_networks = 0
            imported_networks = 0
            discovered_subnets = []
            
            for discovery_file in discovery_files:
                file_path = os.path.join(self.seed_dir, discovery_file)
                
                # Check if file has changed
                if not self._file_updated(file_path):
                    self.log(f"Discovery file {discovery_file} unchanged, skipping")
                    continue
                
                # Process discovery data
                networks = self._read_discovery_data(file_path)
                
                for network in networks:
                    try:
                        # Validate and process network data
                        processed_network = self._process_network_data(network)
                        if processed_network:
                            discovered_subnets.append(processed_network)
                            
                            # Import to IPAM if not excluded
                            if self._should_import_network(processed_network):
                                if self._import_network_to_ipam(processed_network):
                                    imported_networks += 1
                            
                        processed_networks += 1
                        
                    except Exception as e:
                        self.log(f"Error processing network {network}: {e}", level="ERROR")
            
            # Generate discovery report
            report_file = self._generate_discovery_report(discovered_subnets)
            
            self.log(f"Discovery complete. Processed: {processed_networks}, Imported: {imported_networks}")
            
            return {
                "status": "success",
                "processed_networks": processed_networks,
                "imported_networks": imported_networks,
                "discovered_count": len(discovered_subnets),
                "report_file": report_file,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"Palo Alto Panorama SVI discovery failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_discovery_files(self):
        """Get list of Palo Alto Panorama discovery files"""
        if not os.path.exists(self.seed_dir):
            return []
            
        return [
            entry.name
            for entry in os.scandir(self.seed_dir)
            if entry.is_file() and ("panorama" in entry.name.lower() or "vlan" in entry.name.lower()) and entry.name.endswith(".csv")
        ]
    
    def _file_updated(self, file_path):
        """Check if discovery file has changed since last run"""
        current_hash = get_file_hash(file_path)
        
        # Create hash file if it doesn't exist
        os.makedirs(os.path.dirname(self.hash_file), exist_ok=True)
        
        if os.path.exists(self.hash_file):
            with open(self.hash_file, 'r') as f:
                previous_hashes = set(line.strip() for line in f)
                if current_hash in previous_hashes:
                    return False
        
        # Update hash file
        with open(self.hash_file, 'a') as f:
            f.write(f"{current_hash}\n")
        
        return True
    
    def _read_discovery_data(self, file_path):
        """Read discovery data from CSV file"""
        networks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                networks = list(reader)
        except Exception as e:
            self.log(f"Error reading discovery file {file_path}: {e}", level="ERROR")
        
        return networks
    
    def _process_network_data(self, network_data):
        """Process and validate network discovery data"""
        try:
            # Extract network information (Panorama format)
            zone_name = network_data.get('zone')
            network_address = network_data.get('network')
            subnet_info = network_data.get('subnet')
            device_name = network_data.get('device_name')
            vsys = network_data.get('vsys')
            
            if not network_address:
                return None
            
            # Parse network address (could be in CIDR format)
            if '/' in network_address:
                network = ipaddress.IPv4Network(network_address, strict=False)
            elif subnet_info:
                network = ipaddress.IPv4Network(f"{network_address}/{subnet_info}", strict=False)
            else:
                return None
            
            processed_data = {
                'network': str(network.network_address),
                'prefix_length': network.prefixlen,
                'subnet_mask': str(network.netmask),
                'broadcast_address': str(network.broadcast_address),
                'zone_name': zone_name,
                'vsys': vsys,
                'source_device': device_name,
                'discovered_timestamp': set_timestamp(),
                'discovery_source': 'palo_panorama'
            }
            
            return processed_data
            
        except Exception as e:
            self.log(f"Error processing network data: {e}", level="ERROR")
            return None
    
    def _should_import_network(self, network_data):
        """Check if network should be imported based on exclusion rules"""
        try:
            network = network_data.get('network')
            
            # Define exclusion rules
            exclusions = [
                '127.0.0.0/8',    # Loopback
                '169.254.0.0/16', # Link-local
                '224.0.0.0/4',    # Multicast
            ]
            
            for exclusion in exclusions:
                if ipaddress.IPv4Network(network).subnet_of(ipaddress.IPv4Network(exclusion)):
                    self.log(f"Network {network} excluded by rule {exclusion}")
                    return False
            
            return True
            
        except Exception as e:
            self.log(f"Error checking exclusion rules: {e}", level="ERROR")
            return False
    
    def _import_network_to_ipam(self, network_data):
        """Import discovered network to IPAM"""
        try:
            # Get IPAM credentials
            ipam_user, ipam_pass = get_credential("IPAM")
            
            # Prepare import payload
            import_payload = {
                "network_address": network_data['network'],
                "prefix_length": network_data['prefix_length'],
                "subnet_mask": network_data['subnet_mask'],
                "zone_name": network_data.get('zone_name'),
                "vsys": network_data.get('vsys'),
                "description": f"Auto-discovered from {network_data['source_device']} Panorama",
                "discovery_source": network_data['discovery_source'],
                "discovered_date": network_data['discovered_timestamp']
            }
            
            # Import to IPAM
            response = make_api_request(
                method="POST",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/networks/",
                auth=(ipam_user, ipam_pass),
                json=import_payload,
                timeout=30
            )
            
            if response and response.get("status_code") == 201:
                self.log(f"Imported network {network_data['network']}")
                return True
            else:
                self.log(f"Failed to import {network_data['network']}: {response}", level="ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error importing network to IPAM: {e}", level="ERROR")
            return False
    
    def _generate_discovery_report(self, discovered_subnets):
        """Generate CSV report of discovered networks"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"{self.output_dir}/palo_panorama_discovery_{timestamp}.csv"
            
            if discovered_subnets:
                write_list_to_csv(discovered_subnets, report_file)
                self.log(f"Discovery report generated: {report_file}")
                return report_file
            
            return None
            
        except Exception as e:
            self.log(f"Error generating discovery report: {e}", level="ERROR")
            return None


# Task registration for auto-discovery
task_class = PaloAltoPanoramaSviDiscovery