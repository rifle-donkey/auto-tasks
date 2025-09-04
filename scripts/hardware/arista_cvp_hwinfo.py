#!/usr/bin/env python3
"""
Arista CVP Hardware Information Sync Task

This task reads Arista device information from Git (CVP export data),
compares it with IPAM data, and updates hardware information including
model, software version, serial numbers, and End-of-Life data.

Version: 2.0 (Containerized Framework)
- Converted from refresh_hwinfo_arista_cvp.py to framework BaseTask
- Utilizes shared automation_core utilities
- Implements individual scheduling and process isolation
"""

import csv
import hashlib
import ipaddress
import os
from typing import Dict, Any, List
from tqdm import tqdm

from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.ipam_client import IPAMClient
from automation_core.git_ops import GitRepository
from automation_core.reporting import generate_report, log_to_file
from automation_core.monitoring import set_timestamp, ipm_timestamp


class AristaCVPHWInfoTask(BaseTask):
    """Arista CVP hardware information synchronization task"""
    
    name = "arista_cvp_hwinfo"
    description = "Sync Arista device hardware info from CVP via Git to IPAM"
    category = "hardware"
    default_schedule = "0 2 * * 1"  # Weekly on Monday at 2 AM
    max_runtime = 3600  # 1 hour
    dependencies = []
    
    def __init__(self):
        super().__init__()
        self.home_path = os.getenv("HOME")
        self.seed_path = f"{self.home_path}/GitHub/IPAM_Data/Arista-CVP_report"
        self.mgmtip_seed_ipm = "/var/www/html/info-hub/Network_Inventory/mgmtip_total.csv"
        self.hash_file = f"{self.seed_path}/seed_hash"
        
        # Exception networks for IP creation
        self.exception_nets = [
            "10.58.0.0/16", "10.228.0.0/16", "10.229.0.0/16", "10.246.0.0/16",
            "10.247.0.0/16", "10.248.0.0/16", "10.249.0.0/16", "10.101.0.0/16",
            "10.102.0.0/16", "10.103.0.0/16", "172.16.0.0/16", "172.20.0.0/16",
            "172.21.0.0/16", "172.22.0.0/16", "172.25.0.0/16", "172.27.0.0/16",
            "172.28.0.0/16", "172.29.0.0/16", "172.31.0.0/16", "172.17.0.0/16",
            "172.19.0.0/16", "172.18.0.0/16", "157.130.0.0/16", "116.214.0.0/16",
            "1.0.0.0/8", "11.0.0.0/8", "3.0.0.0/8", "4.0.0.0/8", "5.0.0.0/8",
            "6.0.0.0/8", "7.0.0.0/8", "8.0.0.0/8", "111.0.0.0/8", "169.254.0.0/16",
            "33.0.0.0/8", "14.0.0.0/8", "101.0.0.0/8", "172.1.0.0/16"
        ]
    
    def execute(self) -> Dict[str, Any]:
        """Execute Arista CVP hardware info synchronization"""
        result = {
            "status": "success",
            "messages": [],
            "devices_processed": 0,
            "devices_updated": 0,
            "devices_created": 0,
            "eox_items_added": 0,
            "seed_file_list": [],
            "hwinfo_cvp": {},
            "hwinfo_infohub": {},
            "ip_hwinfo_update": {},
            "undocumented_ip": {},
            "arista_lcm_eox": [],
            "lcm_eox_stock": []
        }
        
        try:
            # Initialize IPAM client
            usr, pwd = get_credential("IPAM")
            self.ipam = IPAMClient(usr, pwd)
            
            # Initialize Git repository
            git_repo = GitRepository(self.seed_path)
            
            # Ensure hash file exists
            self._ensure_hash_file()
            
            # Pull latest seed files from Git
            self._pull_git_data(git_repo, result)
            
            # List seed files
            self._list_seed_files(result)
            
            # Process seed files
            if result['seed_file_list']:
                self._process_seed_files(result)
            
            # Read hardware info from Info Hub
            self._read_hwinfo_infohub(result)
            
            # Compare hardware information
            if result['hwinfo_cvp'] and result['hwinfo_infohub']:
                self._compare_hwinfo(result)
            
            # Update hardware info
            if result['ip_hwinfo_update']:
                self._update_hwinfo(result)
            
            # Create missing management IPs
            if result['undocumented_ip']:
                self._add_missing_ips(result)
            
            # Update EoX database
            self._read_eox_stock(result)
            if result['arista_lcm_eox'] and result['lcm_eox_stock']:
                self._update_eox_db(result)
            
            # Generate reports
            self._generate_reports(result)
            
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["messages"].append(f"Task failed with error: {str(e)}")
            
        return result
    
    def _ensure_hash_file(self):
        """Ensure hash file exists"""
        if not os.path.exists(self.hash_file):
            open(self.hash_file, 'w', encoding='UTF-8').close()
            os.chmod(self.hash_file, 0o644)
    
    def _pull_git_data(self, git_repo: GitRepository, result: Dict[str, Any]):
        """Pull latest seed files from Git"""
        try:
            result['messages'].append("Pulling seed file from Git......")
            git_repo.pull()
            result['messages'].append("Git pull completed successfully")
        except Exception as e:
            result['messages'].append(f"Git pull failed: {str(e)}")
    
    def _list_seed_files(self, result: Dict[str, Any]):
        """List available seed files"""
        result['messages'].append("List seed files......")
        result['seed_file_list'] = []
        
        try:
            with os.scandir(self.seed_path) as entries:
                for entry in entries:
                    if entry.is_file() and "inventory.csv" in entry.name:
                        result['seed_file_list'].append(entry.name)
        except Exception as e:
            result['messages'].append(f"Failed to list seed files: {str(e)}")
    
    def _verify_seed_change(self, seed_file: str) -> bool:
        """Verify if seed file has changed"""
        try:
            # Generate new hash
            with open(seed_file, 'rb') as f:
                content = f.read()
            new_hash = hashlib.md5(content).hexdigest()
            
            # Read previous hashes
            previous_hashes = []
            if os.path.exists(self.hash_file):
                with open(self.hash_file, 'r') as f:
                    previous_hashes = [line.strip() for line in f]
            
            # Compare hashes
            if new_hash in previous_hashes:
                return False
            else:
                # Update hash file
                with open(self.hash_file, 'a') as f:
                    f.write(f"{new_hash}\n")
                return True
                
        except Exception:
            return True  # Assume changed if error occurs
    
    def _process_seed_files(self, result: Dict[str, Any]):
        """Process seed files for hardware info"""
        for file_name in result['seed_file_list']:
            seed_file = f"{self.seed_path}/{file_name}"
            
            if not self._verify_seed_change(seed_file):
                result['messages'].append(f"No change found in {seed_file}")
                continue
                
            result['messages'].append(f"Found change in {seed_file}")
            self._read_hwinfo_cvp(seed_file, result)
    
    def _read_hwinfo_cvp(self, seed_file: str, result: Dict[str, Any]):
        """Read hardware info from CVP seed file"""
        result['messages'].append("Read HW info from device list......")
        
        hwsw_bundle = []
        class_name = "IKEA/Network_Device_NOC"
        
        # Preset values for Arista devices
        defaults = {
            "Operation_Status": "Operation",
            "Response_PING": "1",
            "Scanned": "1",
            "Brand_and_Model": "Arista",
            "OS_Type": "Arista-EOS",
            "Vendor": "Arista",
            "In_Tool": "1",
            "Device_Type": "HW Appliance"
        }
        
        try:
            with open(seed_file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                devices = list(reader)
            
            for device in devices:
                dev_name = device.get('Device', '')
                dev_ip = device.get('IP Address', '')
                hw_model = device.get('Model', '')
                sw_version = device.get('Software', '')
                serial_number = device.get('Device ID', '')
                
                if not dev_ip or not dev_name:
                    continue
                
                # Extract device information
                short_name = dev_name.split(".", 1)[0]
                type_param = dev_name[3].lower() if len(dev_name) > 3 else 'x'
                
                # Determine function and type
                if type_param in ["x", "s"]:
                    function = "Switch"
                    device_type = type_param
                else:
                    function = "Unknown"
                    device_type = "x"
                
                # Store device info
                result['hwinfo_cvp'][dev_ip] = {
                    "Device_Name": short_name,
                    "Function": function,
                    "Type": device_type,
                    "Device_Type": defaults["Device_Type"],
                    "Brand_and_Model": defaults["Brand_and_Model"],
                    "Operation_Status": defaults["Operation_Status"],
                    "Scanned": defaults["Scanned"],
                    "Response_PING": defaults["Response_PING"],
                    "Vendor": defaults["Vendor"],
                    "Model": hw_model,
                    "OS_Type": defaults["OS_Type"],
                    "OS_Version": sw_version,
                    "Serial_Number": serial_number,
                    "Class_Name": class_name,
                    "In_Tool": defaults["In_Tool"],
                    "Name_in_Tool": short_name,
                    "Name_on_Device": short_name,
                    "PCI_DSS": "0"
                }
                
                # Prepare EoX table entry
                if hw_model and sw_version:
                    hwsw_list = [hw_model, sw_version]
                    not_in_bundle = True
                    
                    for item in hwsw_bundle:
                        if set(hwsw_list).issubset(set(item)):
                            not_in_bundle = False
                            break
                    
                    if not_in_bundle:
                        hwsw_list.extend(["2099-12-31", "2099-12-31"])  # Default EoX dates
                        hwsw_bundle.append(hwsw_list)
            
            # Process EoX bundle
            for bundle in hwsw_bundle:
                eox_item = {
                    "HW_Model": bundle[0],
                    "SW_Version": bundle[1],
                    "HW_EoX": bundle[2],
                    "SW_EoX": bundle[3],
                    "Sys_OID": "Unknown",
                    "Hosting_HW_ID": "Unknown",
                    "Hosting_HW_EoX": "Unknown",
                    "Hosting_OS": "Unknown",
                    "Hosting_OS_EoX": "Unknown",
                    "Vendor": "Arista"
                }
                result['arista_lcm_eox'].append(eox_item)
            
            result['devices_processed'] = len(result['hwinfo_cvp'])
            
        except Exception as e:
            result['messages'].append(f"Failed to read CVP hardware info: {str(e)}")
    
    def _read_hwinfo_infohub(self, result: Dict[str, Any]):
        """Read hardware info from Info Hub"""
        result['messages'].append("Read HW info from INFO Hub......")
        
        try:
            with open(self.mgmtip_seed_ipm, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                mgmt_ips = list(reader)
            
            for mgmt_ip in mgmt_ips:
                dev_ip = mgmt_ip.get('Address', '')
                if dev_ip:
                    result['hwinfo_infohub'][dev_ip] = {
                        "Device_Name": mgmt_ip.get('Hostname', ''),
                        "Function": mgmt_ip.get('Device_Function', ''),
                        "Type": mgmt_ip.get('Device_Type', ''),
                        "Device_Type": mgmt_ip.get('HW_or_Virtual', ''),
                        "Brand_and_Model": mgmt_ip.get('Brand_Model', ''),
                        "Operation_Status": mgmt_ip.get('Operation_Status', ''),
                        "Scanned": mgmt_ip.get('Device_scanned', ''),
                        "Response_PING": mgmt_ip.get('Device_Ping_Flag', ''),
                        "Vendor": mgmt_ip.get('Vendor', ''),
                        "Model": mgmt_ip.get('Model', ''),
                        "OS_Type": mgmt_ip.get('OS_Type', ''),
                        "OS_Version": mgmt_ip.get('OS_Version', ''),
                        "Serial_Number": mgmt_ip.get('Serial_Number', ''),
                        "Class_Name": mgmt_ip.get('IP_Class_Name', ''),
                        "In_Tool": mgmt_ip.get('In_Tool', ''),
                        "Name_in_Tool": mgmt_ip.get('Name_in_Tool', ''),
                        "Name_on_Device": mgmt_ip.get('Name_on_Device', ''),
                        "PCI_DSS": mgmt_ip.get('PCI_DSS', '')
                    }
            
            result['messages'].append("Reading management IP from INFO Hub completed")
            
        except Exception as e:
            result['messages'].append(f"Failed to read Info Hub data: {str(e)}")
    
    def _compare_hwinfo(self, result: Dict[str, Any]):
        """Compare hardware information between CVP and IPAM"""
        result['messages'].append("Comparing Arista HW Info......")
        
        cvp_data = result['hwinfo_cvp']
        ipam_data = result['hwinfo_infohub']
        
        with tqdm(total=len(cvp_data), desc="Comparing devices") as pbar:
            for dev_ip, dev_hwinfo in cvp_data.items():
                if dev_ip not in ipam_data:
                    result['undocumented_ip'][dev_ip] = dev_hwinfo
                    result['messages'].append(
                        f"Found undocumented Arista {dev_ip}: {dev_hwinfo['Device_Name']}, "
                        f"SN: {dev_hwinfo['Serial_Number']}"
                    )
                else:
                    ipam_hwinfo = ipam_data[dev_ip]
                    needs_update = False
                    
                    for key in dev_hwinfo.keys():
                        cvp_value = str(dev_hwinfo[key]).upper()
                        ipam_value = str(ipam_hwinfo[key]).upper()
                        
                        if hash(cvp_value) != hash(ipam_value):
                            needs_update = True
                            break
                    
                    if needs_update:
                        result['ip_hwinfo_update'][dev_ip] = dev_hwinfo
                        result['messages'].append(f"Device {dev_ip} needs update")
                
                pbar.update(1)
        
        result['messages'].append("Comparing HW Info completed.")
    
    def _update_hwinfo(self, result: Dict[str, Any]):
        """Update hardware info for existing IPs"""
        result['messages'].append("Updating HW Info for Network Device IP addresses......")
        
        ipm_timestamp = ipm_timestamp()
        last_scan = set_timestamp()
        
        with tqdm(total=len(result['ip_hwinfo_update']), desc="Updating devices") as pbar:
            for addr, hwinfo in result['ip_hwinfo_update'].items():
                try:
                    # Prepare IP class parameters
                    ip_params = {
                        "time_stamp_create": ipm_timestamp,
                        "ikea_network_device_lastscanned": last_scan,
                        "ikea_network_device_hostname_dev": hwinfo['Name_on_Device'],
                        "ikea_network_device_hostname_mgntool": hwinfo['Name_in_Tool'],
                        "ikea_network_device_mgntool": hwinfo['In_Tool'],
                        "ikea_network_component_function": hwinfo['Function'],
                        "ikea_network_component_type": hwinfo['Type'],
                        "ikea_network_device_type": hwinfo['Device_Type'],
                        "ikea_network_equipment_brand": hwinfo['Brand_and_Model'],
                        "ikea_network_device_opera": hwinfo['Operation_Status'],
                        "ikea_network_device_bmc": hwinfo['Scanned'],
                        "ikea_network_device_ping": hwinfo['Response_PING'],
                        "ikea_network_device_vendor": hwinfo['Vendor'],
                        "ikea_network_device_module": hwinfo['Model'],
                        "ikea_network_device_ostype": hwinfo['OS_Type'],
                        "ikea_network_device_osversion": hwinfo['OS_Version'],
                        "ikea_network_device_sn": hwinfo['Serial_Number'],
                        "ikea_network_ip_logs": f"Last updated by task: {self.name}"
                    }
                    
                    # Update IP via IPAM client
                    success = self.ipam.update_ip_device_info(
                        ip_address=addr,
                        class_name=hwinfo['Class_Name'],
                        parameters=ip_params
                    )
                    
                    if success:
                        result['devices_updated'] += 1
                        result['messages'].append(f"Update {addr} succeed.")
                    else:
                        result['messages'].append(f"Update {addr} failed.")
                        
                except Exception as e:
                    result['messages'].append(f"Update {addr} failed with error: {str(e)}")
                
                pbar.update(1)
    
    def _add_missing_ips(self, result: Dict[str, Any]):
        """Add missing/undocumented IP addresses"""
        result['messages'].append("Create undocumented IP addresses......")
        
        with tqdm(total=len(result['undocumented_ip']), desc="Creating IPs") as pbar:
            for addr, hwinfo in result['undocumented_ip'].items():
                if not addr:
                    result['messages'].append(f"Undocumented device missing IP: {hwinfo}")
                    pbar.update(1)
                    continue
                
                # Check if IP is in exception list
                is_exception = False
                try:
                    ip_obj = ipaddress.ip_address(addr)
                    for exc_net in self.exception_nets:
                        if ip_obj in ipaddress.ip_network(exc_net):
                            is_exception = True
                            break
                except ValueError:
                    is_exception = True
                
                if is_exception:
                    result['messages'].append(f"Address {addr} is in exception list, ignore.")
                    pbar.update(1)
                    continue
                
                try:
                    # Create IP via IPAM client
                    success = self.ipam.create_device_ip(
                        ip_address=addr,
                        hostname=hwinfo['Device_Name'],
                        class_name=hwinfo['Class_Name'],
                        device_info=hwinfo
                    )
                    
                    if success:
                        result['devices_created'] += 1
                        result['messages'].append(f"Create {addr} succeed.")
                    else:
                        result['messages'].append(f"Create {addr} failed.")
                        
                except Exception as e:
                    result['messages'].append(f"Create {addr} failed with error: {str(e)}")
                
                pbar.update(1)
    
    def _read_eox_stock(self, result: Dict[str, Any]):
        """Read existing EoX stock from IPAM"""
        try:
            eox_data = self.ipam.read_custom_db("ikea_device_lcm_eox")
            
            for item in eox_data:
                eox_item = {
                    "data_id": item.get('custom_db_data_id'),
                    "db_id": item.get('custom_db_name_id'),
                    "Sys_OID": item.get('value1'),
                    "HW_Model": item.get('value2'),
                    "HW_EoX": item.get('value3'),
                    "SW_Version": item.get('value4'),
                    "SW_EoX": item.get('value5'),
                    "Hosting_HW_ID": item.get('value6'),
                    "Hosting_HW_EoX": item.get('value7'),
                    "Hosting_OS": item.get('value8'),
                    "Hosting_OS_EoX": item.get('value9'),
                    "Vendor": item.get('value10')
                }
                result['lcm_eox_stock'].append(eox_item)
                
        except Exception as e:
            result['messages'].append(f"Failed to read EoX stock: {str(e)}")
    
    def _update_eox_db(self, result: Dict[str, Any]):
        """Update EoX database with new entries"""
        new_eox = result['arista_lcm_eox']
        stock_eox = result['lcm_eox_stock']
        
        if not stock_eox:
            result['messages'].append("No EoX stock data available, skipping update")
            return
        
        db_id = stock_eox[0]['db_id']
        
        # Prepare comparison dictionaries
        new_compare = {}
        stock_compare = {}
        eox_create = []
        
        for item in new_eox:
            key = f"{item['Sys_OID']}:{item['HW_Model']}:{item['SW_Version']}"
            new_compare[key] = item
        
        for item in stock_eox:
            key = f"{item['Sys_OID']}:{item['HW_Model']}:{item['SW_Version']}"
            stock_compare[key] = item
        
        # Find new items to create
        for key, item in new_compare.items():
            if key not in stock_compare:
                eox_create.append(item)
        
        # Create new EoX items
        if eox_create:
            with tqdm(total=len(eox_create), desc="Creating EoX items") as pbar:
                for new_eox_item in eox_create:
                    try:
                        success = self.ipam.create_custom_db_entry(
                            db_id=db_id,
                            values={
                                "value1": new_eox_item['Sys_OID'],
                                "value2": new_eox_item['HW_Model'],
                                "value3": new_eox_item['HW_EoX'],
                                "value4": new_eox_item['SW_Version'],
                                "value5": new_eox_item['SW_EoX'],
                                "value6": new_eox_item['Hosting_HW_ID'],
                                "value7": new_eox_item['Hosting_HW_EoX'],
                                "value8": new_eox_item['Hosting_OS'],
                                "value9": new_eox_item['Hosting_OS_EoX'],
                                "value10": new_eox_item['Vendor']
                            }
                        )
                        
                        if success:
                            result['eox_items_added'] += 1
                            result['messages'].append(
                                f"New EoX item created - {new_eox_item['HW_Model']}_{new_eox_item['SW_Version']}"
                            )
                        else:
                            result['messages'].append(
                                f"Failed to create EoX item - {new_eox_item['HW_Model']}_{new_eox_item['SW_Version']}"
                            )
                            
                    except Exception as e:
                        result['messages'].append(f"Create EoX item failed: {str(e)}")
                    
                    pbar.update(1)
        else:
            result['messages'].append("No new EoX items found, skip custom DB update.")
    
    def _generate_reports(self, result: Dict[str, Any]):
        """Generate summary reports and logs"""
        try:
            # Generate summary report
            summary = {
                "task": self.name,
                "timestamp": set_timestamp(),
                "devices_processed": result['devices_processed'],
                "devices_updated": result['devices_updated'],
                "devices_created": result['devices_created'],
                "eox_items_added": result['eox_items_added'],
                "status": result['status']
            }
            
            # Log detailed messages
            if result['messages']:
                log_file = f"/var/automation_log/hardware/{self.name}.log"
                log_to_file(result['messages'], log_file)
            
            # Generate CSV reports for updated/created devices
            if result['ip_hwinfo_update']:
                report_file = f"/var/automation_file/hardware/{self.name}_updates.csv"
                generate_report(result['ip_hwinfo_update'], report_file, format='csv')
            
            if result['undocumented_ip']:
                report_file = f"/var/automation_file/hardware/{self.name}_created.csv"
                generate_report(result['undocumented_ip'], report_file, format='csv')
            
        except Exception as e:
            result['messages'].append(f"Report generation failed: {str(e)}")


# Task instance for auto-discovery
task = AristaCVPHWInfoTask()