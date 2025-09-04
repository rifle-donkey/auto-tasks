from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.utils import set_timestamp
from automation_core.networking import make_api_request
from automation_core.reporting import write_list_to_csv, write_to_json, send_to_splunk
import os
import csv
import json
from datetime import datetime


class NetworkDeviceInventoryReport(BaseTask):
    name = "network_device_inventory_report"
    description = "Generate comprehensive network device inventory reports from IPAM"
    category = "reporting"
    dependencies = ["IPAM"]
    default_schedule = "0 8 * * 1"  # Weekly on Monday at 8 AM
    max_runtime = 1200
    
    def __init__(self):
        super().__init__()
        self.output_dir = "/var/automation_file/reporting"
        
    def execute(self):
        try:
            self.log("Starting network device inventory report generation")
            
            # Get network device data from IPAM
            device_data = self._get_network_devices()
            if not device_data:
                self.log("No network device data found", level="WARNING")
                return {"status": "skipped", "reason": "no_data"}
            
            # Generate different report formats
            report_files = []
            
            # CSV report
            csv_file = self._generate_csv_report(device_data)
            if csv_file:
                report_files.append(csv_file)
            
            # JSON report for API consumption
            json_file = self._generate_json_report(device_data)
            if json_file:
                report_files.append(json_file)
            
            # Site-based analysis
            site_analysis = self._generate_site_analysis(device_data)
            
            # Send to Splunk for monitoring
            self._send_to_splunk(device_data, site_analysis)
            
            self.log(f"Report generation complete. Generated {len(report_files)} reports for {len(device_data)} devices")
            
            return {
                "status": "success",
                "devices_processed": len(device_data),
                "reports_generated": len(report_files),
                "report_files": report_files,
                "site_count": len(site_analysis),
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"Network device inventory report failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_network_devices(self):
        """Get network device inventory from IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            # Get all network devices
            response = make_api_request(
                method="GET",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/",
                params={"device_type": "network_equipment"},
                auth=(ipam_user, ipam_pass),
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                devices = response.get("data", [])
                
                # Enrich device data
                enriched_devices = []
                for device in devices:
                    enriched_device = self._enrich_device_data(device)
                    if enriched_device:
                        enriched_devices.append(enriched_device)
                
                self.log(f"Retrieved and enriched {len(enriched_devices)} network devices")
                return enriched_devices
            
            return []
            
        except Exception as e:
            self.log(f"Error getting network devices: {e}", level="ERROR")
            return []
    
    def _enrich_device_data(self, device):
        """Enrich device data with additional information"""
        try:
            enriched = {
                'hostname': device.get('hostname'),
                'ip_address': device.get('ip_address'),
                'device_type': device.get('device_type'),
                'vendor': device.get('vendor'),
                'model': device.get('model'),
                'serial_number': device.get('serial_number'),
                'software_version': device.get('software_version'),
                'site': device.get('site'),
                'location': device.get('location'),
                'status': device.get('status'),
                'last_updated': device.get('last_updated'),
                'management_status': device.get('management_status'),
                'monitoring_enabled': device.get('monitoring_enabled'),
                'backup_status': device.get('backup_status'),
                'compliance_status': device.get('compliance_status'),
                'report_timestamp': set_timestamp()
            }
            
            return enriched
            
        except Exception as e:
            self.log(f"Error enriching device data: {e}", level="ERROR")
            return device
    
    def _generate_csv_report(self, device_data):
        """Generate CSV inventory report"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_file = f"{self.output_dir}/network_device_inventory_{timestamp}.csv"
            
            write_list_to_csv(device_data, csv_file)
            self.log(f"CSV report generated: {csv_file}")
            return csv_file
            
        except Exception as e:
            self.log(f"Error generating CSV report: {e}", level="ERROR")
            return None
    
    def _generate_json_report(self, device_data):
        """Generate JSON inventory report for API consumption"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_file = f"{self.output_dir}/network_device_inventory_{timestamp}.json"
            
            report_data = {
                "report_metadata": {
                    "generation_timestamp": set_timestamp(),
                    "total_devices": len(device_data),
                    "report_type": "network_device_inventory"
                },
                "devices": device_data
            }
            
            write_to_json(report_data, json_file)
            self.log(f"JSON report generated: {json_file}")
            return json_file
            
        except Exception as e:
            self.log(f"Error generating JSON report: {e}", level="ERROR")
            return None
    
    def _generate_site_analysis(self, device_data):
        """Generate site-based analysis of device distribution"""
        try:
            site_analysis = {}
            
            for device in device_data:
                site = device.get('site', 'Unknown')
                
                if site not in site_analysis:
                    site_analysis[site] = {
                        'total_devices': 0,
                        'device_types': {},
                        'vendors': {},
                        'status_summary': {
                            'active': 0,
                            'inactive': 0,
                            'maintenance': 0
                        }
                    }
                
                # Update counters
                site_analysis[site]['total_devices'] += 1
                
                # Device type distribution
                device_type = device.get('device_type', 'Unknown')
                site_analysis[site]['device_types'][device_type] = \
                    site_analysis[site]['device_types'].get(device_type, 0) + 1
                
                # Vendor distribution
                vendor = device.get('vendor', 'Unknown')
                site_analysis[site]['vendors'][vendor] = \
                    site_analysis[site]['vendors'].get(vendor, 0) + 1
                
                # Status summary
                status = device.get('status', 'unknown').lower()
                if status in site_analysis[site]['status_summary']:
                    site_analysis[site]['status_summary'][status] += 1
            
            # Save site analysis report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            analysis_file = f"{self.output_dir}/site_analysis_{timestamp}.json"
            write_to_json(site_analysis, analysis_file)
            
            self.log(f"Site analysis generated for {len(site_analysis)} sites")
            return site_analysis
            
        except Exception as e:
            self.log(f"Error generating site analysis: {e}", level="ERROR")
            return {}
    
    def _send_to_splunk(self, device_data, site_analysis):
        """Send inventory data to Splunk for monitoring"""
        try:
            # Summary metrics for Splunk
            summary_data = {
                "timestamp": set_timestamp(),
                "event_type": "network_device_inventory",
                "total_devices": len(device_data),
                "site_count": len(site_analysis),
                "vendor_distribution": self._get_vendor_distribution(device_data),
                "status_distribution": self._get_status_distribution(device_data)
            }
            
            # Send to Splunk
            send_to_splunk(summary_data, source="network_inventory_report")
            
            self.log("Inventory data sent to Splunk")
            
        except Exception as e:
            self.log(f"Error sending data to Splunk: {e}", level="ERROR")
    
    def _get_vendor_distribution(self, device_data):
        """Get vendor distribution summary"""
        vendor_counts = {}
        for device in device_data:
            vendor = device.get('vendor', 'Unknown')
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
        return vendor_counts
    
    def _get_status_distribution(self, device_data):
        """Get status distribution summary"""
        status_counts = {}
        for device in device_data:
            status = device.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        return status_counts


# Task registration for auto-discovery
task_class = NetworkDeviceInventoryReport