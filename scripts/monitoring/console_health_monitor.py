"""
Console Health Monitor

Monitors HPE OOB device connectivity and generates health reports.
Tests HTTPS connections to console management interfaces.
"""
from automation_core import BaseTask, get_credential, MonitoringUtilities, ReportingUtilities
import csv
import os
from typing import Dict, List, Any


class ConsoleHealthMonitor(BaseTask):
    """Monitor HPE out-of-band console device health."""
    
    name = "console_health_monitor"
    description = "Monitor HPE OOB device connectivity with HTTPS testing and health reporting"
    category = "monitoring"
    dependencies = ["HPE_OOB"]
    default_schedule = "*/30 * * * *"  # Every 30 minutes
    max_runtime = 600  # 10 minutes
    retry_count = 2
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.monitoring = MonitoringUtilities(debug=self.config.get('debug', False))
        self.reporting = ReportingUtilities(debug=self.config.get('debug', False))
        
        # Configuration
        self.device_list_file = self.config.get(
            'device_list_file', 
            '/var/www/html/info-hub/Console_Inventory/console_total.csv'
        )
    
    def load_console_devices(self) -> List[Dict[str, str]]:
        """Load console device list from CSV file."""
        devices = []
        
        try:
            if not os.path.exists(self.device_list_file):
                self.log(f"Device list file not found: {self.device_list_file}", "warning")
                return devices
            
            with open(self.device_list_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Extract required fields with fallbacks
                    device = {
                        'address': row.get('Address', row.get('IP_Address', '')),
                        'name': row.get('Hostname', row.get('Name', '')),
                        'location': row.get('Location', 'Unknown'),
                        'type': row.get('Device_Type', 'Console')
                    }
                    
                    # Add standby address if available
                    if 'Standby_Address' in row and row['Standby_Address']:
                        device['standby_address'] = row['Standby_Address']
                    
                    # Skip devices without address
                    if device['address']:
                        devices.append(device)
                    else:
                        self.log(f"Skipping device without address: {row}", "warning")
            
            self.log(f"Loaded {len(devices)} console devices from {self.device_list_file}")
            
        except Exception as e:
            self.log(f"Error loading device list: {e}", "error")
            raise
        
        return devices
    
    def generate_reports(self, health_results: Dict[str, Any]) -> Dict[str, str]:
        """Generate various output reports from health check results."""
        reports = {}
        timestamp = self.monitoring.network_utils.set_timestamp()
        
        # CSV reports for reachable and unreachable devices
        if health_results['reachable']:
            csv_file = f"console_reachable_{timestamp}.csv"
            self.reporting.write_to_csv(
                health_results['reachable'], 
                csv_file, 
                category="monitoring"
            )
            reports['reachable_csv'] = csv_file
        
        if health_results['unreachable']:
            csv_file = f"console_unreachable_{timestamp}.csv"
            self.reporting.write_to_csv(
                health_results['unreachable'], 
                csv_file, 
                category="monitoring"
            )
            reports['unreachable_csv'] = csv_file
        
        # Splunk format logs
        all_results = health_results['reachable'] + health_results['unreachable']
        if all_results:
            splunk_file = f"console_monitoring_{timestamp}.log"
            self.reporting.write_to_splunk(
                all_results, 
                splunk_file, 
                category="monitoring",
                script_name="console_health_monitor.py"
            )
            reports['splunk_log'] = splunk_file
        
        # JSON report for dashboards
        json_file = f"console_health_{timestamp}.json"
        self.reporting.write_to_json(
            health_results,
            json_file,
            category="monitoring"
        )
        reports['json_report'] = json_file
        
        # Create monitoring dashboard data
        dashboard_file = self.reporting.create_monitoring_dashboard_data(
            health_results, 
            category="monitoring"
        )
        reports['dashboard'] = dashboard_file
        
        return reports
    
    def run(self) -> Dict[str, Any]:
        """Execute console health monitoring."""
        self.log("Starting console health monitoring")
        
        # Get credentials
        username, password = self.get_credential("HPE_OOB")
        self.log("Retrieved HPE console credentials")
        
        # Load device list
        devices = self.load_console_devices()
        
        if not devices:
            raise RuntimeError("No console devices found to monitor")
        
        self.log(f"Monitoring {len(devices)} console devices")
        
        # Perform health checks
        health_results = self.monitoring.console_health_check(
            devices, username, password
        )
        
        # Log summary
        summary = health_results['summary']
        self.log(
            f"Health check complete: {summary['reachable_count']}/{summary['total_checked']} "
            f"devices reachable ({summary['health_percentage']:.1f}%)"
        )
        
        # Generate reports
        reports = self.generate_reports(health_results)
        
        # Log report locations
        for report_type, report_path in reports.items():
            self.log(f"Generated {report_type}: {report_path}")
        
        # Return results
        return {
            'devices_monitored': len(devices),
            'health_summary': summary,
            'reports_generated': reports,
            'raw_results': health_results
        }


# For backwards compatibility and direct execution
def main():
    """Main function for direct script execution."""
    task = ConsoleHealthMonitor()
    try:
        result = task.execute()
        print(f"Console monitoring completed successfully")
        print(f"Monitored {result['task_result']['devices_monitored']} devices")
        print(f"Health: {result['task_result']['health_summary']['health_percentage']:.1f}%")
    except Exception as e:
        print(f"Console monitoring failed: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())