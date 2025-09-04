from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.git_ops import pull_git_repository
from automation_core.utils import set_timestamp, get_file_hash, write_list_to_csv
from automation_core.networking import make_api_request
import os
import csv
import json
import hashlib
from datetime import datetime


class PaloAltoPanoramaHardwareRefresh(BaseTask):
    name = "palo_alto_panorama_hardware_refresh"
    description = "Update Palo Alto device hardware info from Panorama data via Git seed files"
    category = "hardware"
    dependencies = ["IPAM"]
    default_schedule = "0 3 * * 2"  # Weekly on Tuesday at 3 AM
    max_runtime = 1800
    
    def __init__(self):
        super().__init__()
        self.git_dir = "/app/git-repos/panorama-data"
        self.seed_dir = f"{self.git_dir}/seed-files"
        self.hash_file = "/var/automation_file/hardware/palo_alto_hash.txt"
        
    def execute(self):
        try:
            self.log("Starting Palo Alto Panorama hardware refresh")
            
            # Pull latest seed files from Git
            pull_result = pull_git_repository(self.git_dir)
            self.log(f"Git pull result: {pull_result}")
            
            # Get seed files
            seed_files = self._get_seed_files()
            if not seed_files:
                self.log("No seed files found", level="WARNING")
                return {"status": "skipped", "reason": "no_seed_files"}
            
            processed_devices = 0
            updated_devices = 0
            
            for seed_file in seed_files:
                seed_path = os.path.join(self.seed_dir, seed_file)
                
                # Check if seed file has changed
                if not self._seed_file_updated(seed_path):
                    self.log(f"Seed file {seed_file} unchanged, skipping")
                    continue
                    
                # Process Palo Alto device data
                devices = self._read_device_data(seed_path)
                
                for device in devices:
                    try:
                        if self._update_device_hardware(device):
                            updated_devices += 1
                        processed_devices += 1
                    except Exception as e:
                        self.log(f"Error updating device {device.get('hostname', 'unknown')}: {e}", level="ERROR")
            
            self.log(f"Processing complete. Processed: {processed_devices}, Updated: {updated_devices}")
            
            return {
                "status": "success",
                "processed_devices": processed_devices,
                "updated_devices": updated_devices,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"Palo Alto hardware refresh failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_seed_files(self):
        """Get list of Panorama seed files"""
        if not os.path.exists(self.seed_dir):
            return []
            
        return [
            entry.name
            for entry in os.scandir(self.seed_dir)
            if entry.is_file() and entry.name.endswith("panorama_devices.csv")
        ]
    
    def _seed_file_updated(self, seed_file_path):
        """Check if seed file has changed since last run"""
        current_hash = get_file_hash(seed_file_path)
        
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
    
    def _read_device_data(self, seed_file_path):
        """Read Palo Alto device data from seed file"""
        devices = []
        try:
            with open(seed_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                devices = list(reader)
        except Exception as e:
            self.log(f"Error reading seed file {seed_file_path}: {e}", level="ERROR")
        
        return devices
    
    def _update_device_hardware(self, device_data):
        """Update hardware info for a single Palo Alto device in IPAM"""
        try:
            # Get IPAM credentials
            ipam_user, ipam_pass = get_credential("IPAM")
            
            # Prepare hardware update payload
            update_payload = {
                "hostname": device_data.get("hostname"),
                "serial_number": device_data.get("serial_number"), 
                "hardware_model": device_data.get("model"),
                "software_version": device_data.get("sw_version"),
                "management_ip": device_data.get("ip_address"),
                "ha_state": device_data.get("ha_state"),
                "last_updated": set_timestamp()
            }
            
            # Update device in IPAM
            response = make_api_request(
                method="PUT",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/hardware-update/",
                auth=(ipam_user, ipam_pass),
                json=update_payload,
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                self.log(f"Updated hardware info for {device_data.get('hostname')}")
                return True
            else:
                self.log(f"Failed to update {device_data.get('hostname')}: {response}", level="ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error updating device hardware: {e}", level="ERROR")
            return False


# Task registration for auto-discovery
task_class = PaloAltoPanoramaHardwareRefresh