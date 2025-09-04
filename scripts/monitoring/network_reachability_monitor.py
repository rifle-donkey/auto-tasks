from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.utils import set_timestamp
from automation_core.networking import ping_host, make_api_request
from automation_core.reporting import write_list_to_csv
import os
import csv
import json
from datetime import datetime
import concurrent.futures
from typing import Dict, List, Any


class NetworkReachabilityMonitor(BaseTask):
    name = "network_reachability_monitor"
    description = "Monitor network IP reachability and connectivity health across infrastructure"
    category = "monitoring"
    dependencies = ["IPAM"]
    default_schedule = "*/10 * * * *"  # Every 10 minutes
    max_runtime = 900
    
    def __init__(self):
        super().__init__()
        self.output_dir = "/var/automation_file/monitoring"
        self.max_workers = 50
        
    def execute(self):
        try:
            self.log("Starting network reachability monitoring")
            
            # Get device list from IPAM
            devices = self._get_monitored_devices()
            if not devices:
                self.log("No devices found for monitoring", level="WARNING")
                return {"status": "skipped", "reason": "no_devices"}
            
            # Perform parallel reachability tests
            reachable_devices = []
            unreachable_devices = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all ping tests
                future_to_device = {
                    executor.submit(self._test_device_reachability, device): device
                    for device in devices
                }
                
                # Collect results
                for future in concurrent.futures.as_completed(future_to_device):
                    device = future_to_device[future]
                    try:
                        is_reachable, response_time = future.result()
                        device_result = {
                            **device,
                            "response_time_ms": response_time,
                            "timestamp": set_timestamp(),
                            "status": "reachable" if is_reachable else "unreachable"
                        }
                        
                        if is_reachable:
                            reachable_devices.append(device_result)
                        else:
                            unreachable_devices.append(device_result)
                            
                    except Exception as e:
                        self.log(f"Error testing {device.get('ip', 'unknown')}: {e}", level="ERROR")
                        unreachable_devices.append({
                            **device,
                            "status": "error",
                            "error": str(e),
                            "timestamp": set_timestamp()
                        })
            
            # Generate reports
            report_files = self._generate_reachability_reports(reachable_devices, unreachable_devices)
            
            # Update IPAM with status changes if configured
            self._update_device_status_in_ipam(reachable_devices, unreachable_devices)
            
            self.log(f"Monitoring complete. Reachable: {len(reachable_devices)}, Unreachable: {len(unreachable_devices)}")
            
            return {
                "status": "success",
                "total_devices": len(devices),
                "reachable_devices": len(reachable_devices),
                "unreachable_devices": len(unreachable_devices),
                "report_files": report_files,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"Network reachability monitoring failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_monitored_devices(self):
        """Get list of devices to monitor from IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            response = make_api_request(
                method="GET",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/",
                params={
                    "status": "active",
                    "monitor_enabled": "true"
                },
                auth=(ipam_user, ipam_pass),
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                devices = response.get("data", [])
                self.log(f"Retrieved {len(devices)} devices for monitoring")
                return devices
            
            return []
            
        except Exception as e:
            self.log(f"Error getting monitored devices: {e}", level="ERROR")
            return []
    
    def _test_device_reachability(self, device):
        """Test reachability of a single device"""
        ip_address = device.get("ip_address", device.get("address"))
        
        try:
            # Perform ICMP ping test
            is_reachable, response_time = ping_host(ip_address, timeout=5)
            return is_reachable, response_time
            
        except Exception as e:
            self.log(f"Error pinging {ip_address}: {e}", level="ERROR")
            return False, None
    
    def _generate_reachability_reports(self, reachable_devices, unreachable_devices):
        """Generate CSV reports for reachable and unreachable devices"""
        report_files = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Reachable devices report
            if reachable_devices:
                reachable_file = f"{self.output_dir}/reachable_devices_{timestamp}.csv"
                write_list_to_csv(reachable_devices, reachable_file)
                report_files["reachable_report"] = reachable_file
                self.log(f"Reachable devices report: {reachable_file}")
            
            # Unreachable devices report
            if unreachable_devices:
                unreachable_file = f"{self.output_dir}/unreachable_devices_{timestamp}.csv"
                write_list_to_csv(unreachable_devices, unreachable_file)
                report_files["unreachable_report"] = unreachable_file
                self.log(f"Unreachable devices report: {unreachable_file}")
                
                # Send alerts for critical unreachable devices
                self._send_unreachable_alerts(unreachable_devices)
            
            # Summary report
            summary = {
                "monitoring_timestamp": set_timestamp(),
                "total_devices": len(reachable_devices) + len(unreachable_devices),
                "reachable_count": len(reachable_devices),
                "unreachable_count": len(unreachable_devices),
                "success_rate": (len(reachable_devices) / (len(reachable_devices) + len(unreachable_devices))) * 100
            }
            
            summary_file = f"{self.output_dir}/reachability_summary_{timestamp}.json"
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
            report_files["summary_report"] = summary_file
            
            return report_files
            
        except Exception as e:
            self.log(f"Error generating reports: {e}", level="ERROR")
            return {}
    
    def _update_device_status_in_ipam(self, reachable_devices, unreachable_devices):
        """Update device status in IPAM based on reachability results"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            # Update unreachable devices
            for device in unreachable_devices:
                device_id = device.get("id")
                if device_id:
                    update_payload = {
                        "last_ping_status": "unreachable",
                        "last_ping_timestamp": set_timestamp(),
                        "consecutive_failures": device.get("consecutive_failures", 0) + 1
                    }
                    
                    make_api_request(
                        method="PUT",
                        url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/{device_id}/",
                        auth=(ipam_user, ipam_pass),
                        json=update_payload,
                        timeout=10
                    )
            
            # Update reachable devices  
            for device in reachable_devices:
                device_id = device.get("id")
                if device_id:
                    update_payload = {
                        "last_ping_status": "reachable",
                        "last_ping_timestamp": set_timestamp(),
                        "last_response_time": device.get("response_time_ms"),
                        "consecutive_failures": 0
                    }
                    
                    make_api_request(
                        method="PUT", 
                        url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/{device_id}/",
                        auth=(ipam_user, ipam_pass),
                        json=update_payload,
                        timeout=10
                    )
                    
        except Exception as e:
            self.log(f"Error updating device status in IPAM: {e}", level="ERROR")
    
    def _send_unreachable_alerts(self, unreachable_devices):
        """Send alerts for critical unreachable devices"""
        try:
            critical_devices = [
                device for device in unreachable_devices
                if device.get("priority", "normal") in ["critical", "high"]
            ]
            
            if critical_devices:
                alert_message = f"ALERT: {len(critical_devices)} critical devices are unreachable"
                self.log(alert_message, level="WARNING")
                
                # Here you could integrate with alerting systems like:
                # - Send to Splunk
                # - Send email notifications  
                # - Post to Slack/Teams
                # - Create service tickets
                
        except Exception as e:
            self.log(f"Error sending alerts: {e}", level="ERROR")


# Task registration for auto-discovery
task_class = NetworkReachabilityMonitor