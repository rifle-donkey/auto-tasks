from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.utils import set_timestamp
from automation_core.networking import make_api_request
import os
import csv
import json
import base64
from datetime import datetime


class HpeConsoleHardwareRefresh(BaseTask):
    name = "hpe_console_hardware_refresh"
    description = "Retrieve and update HPE OOB device hardware info and generate reports"
    category = "hardware"
    dependencies = ["HPE_OOB", "IPAM"]
    default_schedule = "0 4 * * 6"  # Weekly on Saturday at 4 AM
    max_runtime = 2400
    
    def __init__(self):
        super().__init__()
        self.output_file = "/var/automation_file/hardware/hpe_console_hardware.csv"
        
    def execute(self):
        try:
            self.log("Starting HPE console hardware refresh")
            
            # Get HPE OOB credentials
            hpe_user, hpe_pass = get_credential("HPE_OOB")
            
            # Get device list from IPAM
            device_list = self._get_hpe_device_list()
            if not device_list:
                self.log("No HPE devices found", level="WARNING")
                return {"status": "skipped", "reason": "no_devices"}
            
            processed_devices = 0
            updated_devices = 0
            hardware_info = []
            
            for device in device_list:
                try:
                    device_ip = device.get('ip_address')
                    device_name = device.get('hostname', device_ip)
                    
                    self.log(f"Processing HPE device: {device_name}")
                    
                    # Retrieve hardware info from HPE OOB console
                    hw_info = self._get_device_hardware_info(device_ip, hpe_user, hpe_pass)
                    
                    if hw_info:
                        # Update IPAM with hardware info
                        if self._update_device_in_ipam(device, hw_info):
                            updated_devices += 1
                        
                        hardware_info.append({
                            'hostname': device_name,
                            'ip_address': device_ip,
                            'serial_number': hw_info.get('serial_number'),
                            'model': hw_info.get('model'),
                            'firmware': hw_info.get('firmware'),
                            'status': hw_info.get('power_status'),
                            'last_updated': set_timestamp()
                        })
                    
                    processed_devices += 1
                    
                except Exception as e:
                    self.log(f"Error processing device {device_name}: {e}", level="ERROR")
            
            # Generate hardware report
            if hardware_info:
                self._generate_hardware_report(hardware_info)
            
            self.log(f"Processing complete. Processed: {processed_devices}, Updated: {updated_devices}")
            
            return {
                "status": "success",
                "processed_devices": processed_devices,
                "updated_devices": updated_devices,
                "report_file": self.output_file,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"HPE console hardware refresh failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_hpe_device_list(self):
        """Get list of HPE devices from IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            response = make_api_request(
                method="GET",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/",
                params={"device_type": "hpe_oob"},
                auth=(ipam_user, ipam_pass),
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                return response.get("data", [])
            
            return []
            
        except Exception as e:
            self.log(f"Error getting HPE device list: {e}", level="ERROR")
            return []
    
    def _get_device_hardware_info(self, device_ip, username, password):
        """Retrieve hardware info from HPE OOB console"""
        try:
            # Create basic auth header
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            
            headers = {
                'Authorization': f'Basic {auth_string}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Get system information
            response = make_api_request(
                method="GET",
                url=f"https://{device_ip}/redfish/v1/Systems/1/",
                headers=headers,
                verify=False,
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                system_data = response.get("data", {})
                
                return {
                    'serial_number': system_data.get('SerialNumber'),
                    'model': system_data.get('Model'),
                    'firmware': system_data.get('BiosVersion'),
                    'power_status': system_data.get('PowerState'),
                    'manufacturer': system_data.get('Manufacturer')
                }
            
            return None
            
        except Exception as e:
            self.log(f"Error getting hardware info from {device_ip}: {e}", level="ERROR")
            return None
    
    def _update_device_in_ipam(self, device, hardware_info):
        """Update device hardware info in IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            update_payload = {
                "serial_number": hardware_info.get('serial_number'),
                "hardware_model": hardware_info.get('model'),
                "firmware_version": hardware_info.get('firmware'),
                "power_status": hardware_info.get('power_status'),
                "last_updated": set_timestamp()
            }
            
            response = make_api_request(
                method="PUT",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/{device['id']}/",
                auth=(ipam_user, ipam_pass),
                json=update_payload,
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                return True
            
            return False
            
        except Exception as e:
            self.log(f"Error updating device in IPAM: {e}", level="ERROR")
            return False
    
    def _generate_hardware_report(self, hardware_info):
        """Generate CSV report of hardware information"""
        try:
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            
            with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['hostname', 'ip_address', 'serial_number', 'model', 'firmware', 'status', 'last_updated']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(hardware_info)
            
            self.log(f"Hardware report generated: {self.output_file}")
            
        except Exception as e:
            self.log(f"Error generating hardware report: {e}", level="ERROR")


# Task registration for auto-discovery
task_class = HpeConsoleHardwareRefresh