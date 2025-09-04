"""
Ansible Hardware Info Refresh

Updates network device hardware information in IPAM using data from Ansible playbook reports.
Processes device inventory and updates IPAM with current hardware details.
"""
from automation_core import (
    BaseTask, IPAMClient, get_credential, GitOperations, 
    ReportingUtilities, NetworkUtilities
)
import csv
import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from tqdm import tqdm


class AnsibleHardwareRefresh(BaseTask):
    """Refresh hardware information using Ansible playbook reports."""
    
    name = "ansible_hardware_refresh"
    description = "Update network device hardware information in IPAM from Ansible discovery reports"
    category = "hardware"
    dependencies = ["IPAM"]
    default_schedule = "0 2 * * *"  # Daily at 2 AM
    max_runtime = 3600  # 1 hour
    retry_count = 2
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.reporting = ReportingUtilities(debug=self.config.get('debug', False))
        self.network_utils = NetworkUtilities(debug=self.config.get('debug', False))
        
        # Configuration
        home_path = os.getenv("HOME")
        self.git_repo_path = self.config.get(
            'git_repo_path', 
            f"{home_path}/GitHub/IPAM_Data/playbook_report"
        )
        self.ipam_seed_file = self.config.get(
            'ipam_seed_file',
            "/var/www/html/info-hub/Network_Inventory/mgmtip_total.csv"
        )
        
        # Initialize Git operations
        self.git_ops = GitOperations(self.git_repo_path)
        
        # Function mapping for device types
        self.function_mapping = {
            "s": "Switch", "x": "Switch", "d": "Switch",
            "r": "Router", "y": "Router_SDWAN", "o": "OOB",
            "p": "FW", "i": "IPS", "v": "VPN",
            "c": "LB", "w": "WLC", "a": "WirelessAP"
        }
        
        # Results storage
        self.results = {
            'messages': [],
            'hwinfo_ansible': {},
            'hwinfo_ipam': {},
            'updates_needed': {},
            'undocumented_devices': {},
            'lcm_eox_data': []
        }
    
    def pull_latest_reports(self) -> List[str]:
        """Pull latest Ansible reports from Git repository."""
        self.log("Pulling latest Ansible reports from Git")
        
        # Pull latest changes
        self.git_ops.pull_latest(self.results)
        
        # Find hardware info CSV files
        hardware_files = self.git_ops.list_files_in_directory(
            ".", "*hardware_info.csv", self.results
        )
        
        if not hardware_files:
            self.log("No hardware info CSV files found in repository", "warning")
            return []
        
        self.log(f"Found {len(hardware_files)} hardware info files")
        return hardware_files
    
    def process_ansible_hardware_data(self, csv_file_path: str) -> None:
        """Process hardware information from Ansible CSV report."""
        self.log(f"Processing Ansible hardware data from {csv_file_path}")
        
        full_path = self.git_ops.get_file_path(csv_file_path)
        
        if not os.path.exists(full_path):
            self.log(f"File not found: {full_path}", "error")
            return
        
        try:
            with open(full_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                devices = list(reader)
            
            self.log(f"Processing {len(devices)} devices from Ansible report")
            
            # Process each device with progress bar
            pbar = tqdm(total=len(devices), desc="Processing devices")
            
            for device_info in devices:
                try:
                    processed_device = self._process_device_info(device_info)
                    if processed_device:
                        device_ip = device_info.get('IP_Address', '').strip()
                        if device_ip:
                            self.results['hwinfo_ansible'][device_ip] = processed_device
                except Exception as e:
                    self.log(f"Error processing device {device_info}: {e}", "error")
                finally:
                    pbar.update(1)
            
            pbar.close()
            
        except Exception as e:
            self.log(f"Error reading Ansible hardware file {csv_file_path}: {e}", "error")
            raise
    
    def _process_device_info(self, device_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Process individual device information from Ansible data."""
        hostname = device_data.get('Hostname', '').strip()
        if not hostname or len(hostname) < 4:
            return None
        
        # Extract device type from hostname (4th character)
        device_type = hostname[3].lower()
        device_function = self.function_mapping.get(device_type, "Unknown")
        
        # Process device model and serial numbers for stacks
        master_model = device_data.get('Device_Model', '').strip()
        stack_models = device_data.get('Stack_Model', '').strip()
        master_sn = device_data.get('Serial_number', '').strip()
        stack_sns = device_data.get('Stack Serial_Number', '').strip()
        
        # Handle stacked devices
        final_model = self._process_stack_info(master_model, stack_models)
        final_sn = self._process_stack_serials(master_sn, stack_sns)
        
        # Determine brand and model category
        vendor = device_data.get('Vendor', '').upper()
        brand_model = self._determine_brand_model(vendor, master_model, device_type)
        
        # Build device info dictionary
        device_info = {
            'Device_Name': hostname,
            'Function': device_function,
            'Type': device_type,
            'Brand_and_Model': brand_model,
            'Operation_Status': 'Operation',
            'Scanned': '1',
            'Vendor': device_data.get('Vendor', ''),
            'Model': final_model,
            'OS_Type': device_data.get('OS', ''),
            'OS_Version': device_data.get('OS_Version', ''),
            'Serial_Number': final_sn,
            'Name_on_Device': hostname
        }
        
        return device_info
    
    def _process_stack_info(self, master_model: str, stack_models: str) -> str:
        """Process stack model information."""
        if not stack_models:
            return master_model or "HW_Model_not_found"
        
        models = [m.strip() for m in stack_models.split() if m.strip()]
        
        if master_model and master_model in models:
            if len(models) > 1:
                models.remove(master_model)
                models.insert(0, f"{master_model}_STACK")
        elif master_model:
            models.insert(0, f"{master_model}_STACK")
        
        return ";".join(models) if models else master_model
    
    def _process_stack_serials(self, master_sn: str, stack_sns: str) -> str:
        """Process stack serial number information."""
        if not stack_sns:
            return master_sn or "SN_not_found"
        
        serials = [s.strip() for s in stack_sns.split() if s.strip()]
        
        if master_sn and master_sn in serials:
            if len(serials) > 1:
                serials.remove(master_sn)
                serials.insert(0, f"{master_sn}_STACK")
        elif master_sn:
            serials.insert(0, f"{master_sn}_STACK")
        
        return ";".join(serials) if serials else master_sn
    
    def _determine_brand_model(self, vendor: str, model: str, device_type: str) -> str:
        """Determine brand and model category from vendor and model info."""
        model_upper = model.upper()
        
        if "CISCO" in vendor:
            if "NEXUS" in model_upper:
                return "Cisco_Nexus"
            elif "ASA" in model_upper:
                return "Cisco_ASA"
            elif "AIR-" in model_upper:
                return "Cisco_WLC"
            else:
                return "Cisco_IOS"
        elif "ARUBA" in vendor:
            return "Aruba_WLC" if device_type == "w" else "Aruba"
        elif "PALO" in vendor:
            return "PaloAlto"
        elif "F5" in vendor:
            return "F5"
        elif "RIVERBED" in vendor:
            return "Riverbed"
        elif "AVOCENT" in vendor:
            return "Avocent"
        elif "HUAWEI" in vendor:
            return "Huawei"
        elif "ARISTA" in vendor:
            return "Arista"
        else:
            return "Unrecognized"
    
    def load_ipam_hardware_info(self) -> None:
        """Load existing hardware information from IPAM."""
        self.log("Loading existing hardware information from IPAM")
        
        if not os.path.exists(self.ipam_seed_file):
            self.log(f"IPAM seed file not found: {self.ipam_seed_file}", "warning")
            return
        
        try:
            with open(self.ipam_seed_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                devices = list(reader)
            
            for device in devices:
                device_ip = device.get('Address', '').strip()
                if device_ip:
                    self.results['hwinfo_ipam'][device_ip] = {
                        'Device_Name': device.get('Hostname', ''),
                        'Function': device.get('Device_Function', ''),
                        'Type': device.get('Device_Type', ''),
                        'Brand_and_Model': device.get('Brand_Model', ''),
                        'Operation_Status': device.get('Operation_Status', ''),
                        'Scanned': device.get('Device_scanned', ''),
                        'Vendor': device.get('Vendor', ''),
                        'Model': device.get('Model', ''),
                        'OS_Type': device.get('OS_Type', ''),
                        'OS_Version': device.get('OS_Version', ''),
                        'Serial_Number': device.get('Serial_Number', ''),
                        'DNS_Domain': device.get('DNS_Domain', ''),
                        'Class_Name': device.get('IP_Class_Name', '')
                    }
            
            self.log(f"Loaded {len(self.results['hwinfo_ipam'])} devices from IPAM")
            
        except Exception as e:
            self.log(f"Error loading IPAM hardware info: {e}", "error")
            raise
    
    def compare_hardware_info(self) -> None:
        """Compare Ansible and IPAM hardware information to identify updates needed."""
        self.log("Comparing hardware information between Ansible and IPAM")
        
        ansible_devices = self.results['hwinfo_ansible']
        ipam_devices = self.results['hwinfo_ipam']
        
        pbar = tqdm(total=len(ansible_devices), desc="Comparing devices")
        
        for device_ip, ansible_info in ansible_devices.items():
            try:
                if device_ip not in ipam_devices:
                    # Device found in Ansible but not in IPAM
                    self.results['undocumented_devices'][device_ip] = ansible_info
                    self.log(
                        f"Found undocumented device: {device_ip} "
                        f"({ansible_info['Device_Name']}, SN: {ansible_info['Serial_Number']})"
                    )
                else:
                    # Compare device information
                    ipam_info = ipam_devices[device_ip]
                    needs_update = False
                    
                    # Compare key fields
                    compare_fields = [
                        'Device_Name', 'Function', 'Type', 'Brand_and_Model',
                        'Vendor', 'Model', 'OS_Type', 'OS_Version', 'Serial_Number'
                    ]
                    
                    for field in compare_fields:
                        ansible_value = str(ansible_info.get(field, '')).upper()
                        ipam_value = str(ipam_info.get(field, '')).upper()
                        
                        if hash(ansible_value) != hash(ipam_value):
                            needs_update = True
                            self.log(
                                f"Field '{field}' differs for {device_ip}: "
                                f"Ansible='{ansible_value}' vs IPAM='{ipam_value}'"
                            )
                            break
                    
                    if needs_update:
                        # Preserve DNS domain from IPAM
                        ansible_info['DNS_Domain'] = ipam_info.get('DNS_Domain', '')
                        self.results['updates_needed'][device_ip] = ansible_info
            
            except Exception as e:
                self.log(f"Error comparing device {device_ip}: {e}", "error")
            finally:
                pbar.update(1)
        
        pbar.close()
        
        self.log(f"Comparison complete: {len(self.results['updates_needed'])} updates needed, "
                f"{len(self.results['undocumented_devices'])} undocumented devices found")
    
    def update_ipam_hardware_info(self) -> None:
        """Update hardware information in IPAM."""
        if not self.results['updates_needed']:
            self.log("No hardware information updates needed")
            return
        
        self.log(f"Updating hardware information for {len(self.results['updates_needed'])} devices")
        
        # Get IPAM credentials and client
        username, password = self.get_credential("IPAM")
        client = IPAMClient("https://ipam.ikea.com", username, password)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        pbar = tqdm(total=len(self.results['updates_needed']), desc="Updating IPAM")
        
        for device_ip, device_info in self.results['updates_needed'].items():
            try:
                hostname = device_info['Device_Name'].strip().split('.')[0]
                dns_domain = device_info.get('DNS_Domain', '')
                
                # Prepare update parameters
                ip_params = {
                    'time_stamp_create': timestamp,
                    'hostname': hostname,
                    'ikea_network_device_lastscanned': timestamp,
                    'ikea_network_device_hostname_dev': device_info['Name_on_Device'],
                    'ikea_network_component_function': device_info['Function'],
                    'ikea_network_component_type': device_info['Type'],
                    'ikea_network_equipment_brand': device_info['Brand_and_Model'],
                    'ikea_network_device_opera': device_info['Operation_Status'],
                    'ikea_network_device_bmc': device_info['Scanned'],
                    'ikea_network_device_vendor': device_info['Vendor'],
                    'ikea_network_device_module': device_info['Model'],
                    'ikea_network_device_ostype': device_info['OS_Type'],
                    'ikea_network_device_osversion': device_info['OS_Version'],
                    'ikea_network_device_sn': device_info['Serial_Number'],
                    'ikea_network_ip_logs': 'Last updated by script: refresh_ansible_hwinfo.py'
                }
                
                # Convert parameters to string
                param_string = "&".join(f"{k}={v}" for k, v in ip_params.items())
                
                # Prepare update request
                update_data = {
                    'add_flag': 'edit_only',
                    'site_id': '2',
                    'hostaddr': device_ip,
                    'name': f"{hostname}.{dns_domain}" if dns_domain else hostname,
                    'ip_class_parameters': param_string
                }
                
                # Execute update
                status_code, response = client.put("ip_add", update_data)
                
                if status_code == 201:
                    self.log(f"Successfully updated {device_ip}")
                else:
                    self.log(f"Failed to update {device_ip}: {status_code} - {response}", "error")
                    
            except Exception as e:
                self.log(f"Error updating device {device_ip}: {e}", "error")
            finally:
                pbar.update(1)
        
        pbar.close()
    
    def generate_reports(self) -> Dict[str, str]:
        """Generate execution reports."""
        reports = {}
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        
        # Messages log
        if self.results['messages']:
            log_file = f"ansible_hwinfo_refresh_{timestamp}.log"
            self.reporting.write_to_log(
                self.results['messages'], 
                log_file, 
                category="hardware"
            )
            reports['log_file'] = log_file
        
        # Updates report
        if self.results['updates_needed']:
            json_file = f"hwinfo_updates_{timestamp}.json"
            self.reporting.write_to_json(
                self.results['updates_needed'],
                json_file,
                category="hardware"
            )
            reports['updates_json'] = json_file
        
        # Undocumented devices report
        if self.results['undocumented_devices']:
            json_file = f"undocumented_devices_{timestamp}.json"
            self.reporting.write_to_json(
                self.results['undocumented_devices'],
                json_file,
                category="hardware"
            )
            reports['undocumented_json'] = json_file
        
        return reports
    
    def run(self) -> Dict[str, Any]:
        """Execute hardware information refresh process."""
        self.log("Starting Ansible hardware info refresh")
        
        # Pull latest reports
        hardware_files = self.pull_latest_reports()
        
        if not hardware_files:
            raise RuntimeError("No hardware info files found to process")
        
        # Process each hardware file
        for hw_file in hardware_files:
            hash_file = os.path.join(self.git_repo_path, "seed_hash")
            
            # Check if file has changed
            file_status = self.git_ops.verify_file_change(hw_file, hash_file, self.results)
            
            if file_status == "Unchanged":
                self.log(f"No changes in {hw_file}, skipping")
                continue
            
            # Process the changed file
            self.process_ansible_hardware_data(hw_file)
        
        # Load current IPAM data
        self.load_ipam_hardware_info()
        
        # Compare and identify changes
        if self.results['hwinfo_ansible'] and self.results['hwinfo_ipam']:
            self.compare_hardware_info()
        
        # Update IPAM with changes
        if self.results['updates_needed']:
            self.update_ipam_hardware_info()
        
        # Generate reports
        reports = self.generate_reports()
        
        # Log summary
        summary = {
            'devices_processed': len(self.results['hwinfo_ansible']),
            'updates_applied': len(self.results['updates_needed']),
            'undocumented_found': len(self.results['undocumented_devices']),
            'reports_generated': list(reports.keys())
        }
        
        self.log(f"Hardware refresh complete: {summary}")
        
        return summary


# Task registration for auto-discovery
task_class = AnsibleHardwareRefresh


# For backwards compatibility and direct execution
def main():
    """Main function for direct script execution."""
    task = AnsibleHardwareRefresh()
    try:
        result = task.execute()
        print(f"Ansible hardware refresh completed successfully")
        print(f"Processed {result['task_result']['devices_processed']} devices")
        print(f"Applied {result['task_result']['updates_applied']} updates")
    except Exception as e:
        print(f"Hardware refresh failed: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())