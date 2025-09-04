"""
DNS Availability Monitor

Monitors DNS server availability and performance.
Tests DNS resolution against multiple nameservers with various target domains.
"""
from automation_core import BaseTask, IPAMClient, get_credential, MonitoringUtilities, ReportingUtilities
import csv
import os
from typing import Dict, List, Any


class DNSAvailabilityMonitor(BaseTask):
    """Monitor DNS server availability and resolution performance."""
    
    name = "dns_availability_monitor"
    description = "Monitor DNS usability by testing nameserver responses to common domains"
    category = "monitoring"
    dependencies = ["IPAM"]
    default_schedule = "*/15 * * * *"  # Every 15 minutes
    max_runtime = 300  # 5 minutes
    retry_count = 1
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.monitoring = MonitoringUtilities(debug=self.config.get('debug', False))
        self.reporting = ReportingUtilities(debug=self.config.get('debug', False))
        
        # Configuration
        self.test_domains = self.config.get('test_domains', [
            "short-ttl.ikea.com",
            "www.ikea.com",
            "www.google.com"
        ])
        
        self.nameserver_filter = self.config.get('nameserver_filter', {
            'exclude_staging': True,
            'allow_monitor': True
        })
    
    def get_nameservers_from_ipam(self) -> List[Dict[str, str]]:
        """Retrieve nameserver list from IPAM."""
        username, password = self.get_credential("IPAM")
        client = IPAMClient("https://ipam.ikea.com", username, password)
        
        self.log("Retrieving nameserver list from IPAM")
        
        # Query parameters for nameservers
        query_params = {
            "WHERE": "class_name LIKE '%DNS%' AND class_name NOT LIKE '%staging%'",
            "SELECT": "hostaddr,hostname,class_name,ikea_network_device_monitor",
            "ORDERBY": "hostaddr"
        }
        
        try:
            status_code, response = client.get("ip_address_list", query_params)
            
            if status_code != 200:
                raise RuntimeError(f"IPAM query failed: {status_code} - {response}")
            
            nameservers = []
            
            for server_info in response:
                # Apply filters
                class_name = server_info.get('class_name', '').upper()
                monitor_flag = server_info.get('ikea_network_device_monitor', '0')
                
                # Skip staging servers if filter enabled
                if self.nameserver_filter.get('exclude_staging') and 'STAGING' in class_name:
                    continue
                
                # Skip servers not allowed to be monitored
                if self.nameserver_filter.get('allow_monitor') and monitor_flag == '0':
                    self.log(f"Nameserver {server_info.get('hostname')} not allowed to be monitored")
                    continue
                
                nameserver = {
                    'address': server_info.get('hostaddr', ''),
                    'name': server_info.get('hostname', ''),
                    'class_name': class_name,
                    'location': self._extract_location_from_class(class_name),
                    'scope': 'Central' if 'NOC' in class_name else 'Local'
                }
                
                if nameserver['address']:
                    nameservers.append(nameserver)
            
            self.log(f"Retrieved {len(nameservers)} nameservers from IPAM")
            return nameservers
            
        except Exception as e:
            self.log(f"Error retrieving nameservers from IPAM: {e}", "error")
            raise
    
    def _extract_location_from_class(self, class_name: str) -> str:
        """Extract location information from IP class name."""
        # This would contain logic to parse location from class naming convention
        # For example, extract site codes or region information
        if 'NOC' in class_name:
            return 'Central'
        
        # Try to extract site code or location identifier
        parts = class_name.split('/')
        for part in parts:
            if len(part) == 3 and part.isalpha():  # Assume 3-letter site codes
                return part.upper()
        
        return 'Unknown'
    
    def calculate_health_metrics(self, dns_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate additional DNS health metrics."""
        metrics = {
            'total_servers': dns_results['total_tested'],
            'healthy_servers': dns_results['healthy_count'],
            'unhealthy_servers': dns_results['total_tested'] - dns_results['healthy_count'],
            'health_percentage': dns_results['health_percentage']
        }
        
        # Location-based health statistics
        location_stats = {}
        scope_stats = {'Central': {'total': 0, 'healthy': 0}, 'Local': {'total': 0, 'healthy': 0}}
        
        all_servers = dns_results['healthy_servers'] + dns_results['unhealthy_servers']
        
        for server in all_servers:
            location = server.get('location', 'Unknown')
            scope = server.get('scope', 'Local')
            is_healthy = server['healthy']
            
            # Location statistics
            if location not in location_stats:
                location_stats[location] = {'total': 0, 'healthy': 0}
            
            location_stats[location]['total'] += 1
            if is_healthy:
                location_stats[location]['healthy'] += 1
            
            # Scope statistics
            scope_stats[scope]['total'] += 1
            if is_healthy:
                scope_stats[scope]['healthy'] += 1
        
        # Calculate percentages
        for location, stats in location_stats.items():
            stats['health_percentage'] = round(
                (stats['healthy'] / stats['total']) * 100, 2
            ) if stats['total'] > 0 else 0
        
        for scope, stats in scope_stats.items():
            stats['health_percentage'] = round(
                (stats['healthy'] / stats['total']) * 100, 2
            ) if stats['total'] > 0 else 0
        
        metrics['location_health'] = location_stats
        metrics['scope_health'] = scope_stats
        
        return metrics
    
    def generate_reports(self, dns_results: Dict[str, Any], 
                        health_metrics: Dict[str, Any]) -> Dict[str, str]:
        """Generate comprehensive DNS monitoring reports."""
        reports = {}
        timestamp = self.monitoring.network_utils.set_timestamp()
        
        # Detailed results CSV
        all_servers = dns_results['healthy_servers'] + dns_results['unhealthy_servers']
        if all_servers:
            # Flatten server results for CSV
            csv_data = []
            for server in all_servers:
                base_row = {
                    'server_address': server['address'],
                    'server_name': server['name'],
                    'location': server.get('location', 'Unknown'),
                    'scope': server.get('scope', 'Local'),
                    'overall_healthy': server['healthy']
                }
                
                # Add test results for each domain
                for domain, test_result in server['test_results'].items():
                    row = base_row.copy()
                    row.update({
                        'test_domain': domain,
                        'test_success': test_result['success'],
                        'response_time_ms': test_result.get('response_time_ms', 0),
                        'error': test_result.get('error', '')
                    })
                    csv_data.append(row)
            
            csv_file = f"dns_detailed_results_{timestamp}.csv"
            self.reporting.write_to_csv(csv_data, csv_file, category="monitoring")
            reports['detailed_csv'] = csv_file
        
        # Summary CSV
        summary_data = []
        for server in all_servers:
            summary_data.append({
                'server_address': server['address'],
                'server_name': server['name'],
                'location': server.get('location', 'Unknown'),
                'scope': server.get('scope', 'Local'),
                'healthy': server['healthy'],
                'successful_tests': sum(1 for t in server['test_results'].values() if t['success']),
                'total_tests': len(server['test_results']),
                'avg_response_time': round(
                    sum(t.get('response_time_ms', 0) for t in server['test_results'].values() 
                        if t['success']) / max(1, sum(1 for t in server['test_results'].values() if t['success'])), 2
                )
            })
        
        summary_csv = f"dns_summary_{timestamp}.csv"
        self.reporting.write_to_csv(summary_data, summary_csv, category="monitoring")
        reports['summary_csv'] = summary_csv
        
        # Splunk logs
        splunk_data = []
        for server in all_servers:
            for domain, test_result in server['test_results'].items():
                splunk_entry = {
                    'server_address': server['address'],
                    'server_name': server['name'],
                    'test_domain': domain,
                    'success': test_result['success'],
                    'response_time_ms': test_result.get('response_time_ms', 0),
                    'location': server.get('location', 'Unknown'),
                    'scope': server.get('scope', 'Local')
                }
                splunk_data.append(splunk_entry)
        
        splunk_file = f"dns_monitoring_{timestamp}.log"
        self.reporting.write_to_splunk(
            splunk_data, 
            splunk_file, 
            category="monitoring",
            script_name="dns_availability_monitor.py"
        )
        reports['splunk_log'] = splunk_file
        
        # JSON report with metrics
        complete_results = {
            'dns_results': dns_results,
            'health_metrics': health_metrics,
            'test_domains': self.test_domains,
            'timestamp': dns_results['timestamp']
        }
        
        json_file = f"dns_health_{timestamp}.json"
        self.reporting.write_to_json(complete_results, json_file, category="monitoring")
        reports['json_report'] = json_file
        
        return reports
    
    def run(self) -> Dict[str, Any]:
        """Execute DNS availability monitoring."""
        self.log("Starting DNS availability monitoring")
        
        # Get nameserver list
        nameservers = self.get_nameservers_from_ipam()
        
        if not nameservers:
            raise RuntimeError("No nameservers found for monitoring")
        
        self.log(f"Testing {len(nameservers)} nameservers against {len(self.test_domains)} domains")
        
        # Perform DNS monitoring
        dns_results = self.monitoring.dns_availability_monitor(
            nameservers, 
            self.test_domains
        )
        
        # Calculate additional health metrics
        health_metrics = self.calculate_health_metrics(dns_results)
        
        # Log summary
        self.log(
            f"DNS monitoring complete: {health_metrics['health_percentage']:.1f}% "
            f"({health_metrics['healthy_servers']}/{health_metrics['total_servers']}) servers healthy"
        )
        
        # Log scope breakdown
        for scope, stats in health_metrics['scope_health'].items():
            if stats['total'] > 0:
                self.log(
                    f"{scope} DNS servers: {stats['health_percentage']:.1f}% "
                    f"({stats['healthy']}/{stats['total']}) healthy"
                )
        
        # Generate reports
        reports = self.generate_reports(dns_results, health_metrics)
        
        # Log report locations
        for report_type, report_path in reports.items():
            self.log(f"Generated {report_type}: {report_path}")
        
        return {
            'servers_tested': len(nameservers),
            'domains_tested': len(self.test_domains),
            'health_metrics': health_metrics,
            'reports_generated': reports,
            'raw_results': dns_results
        }


# For backwards compatibility and direct execution
def main():
    """Main function for direct script execution."""
    task = DNSAvailabilityMonitor()
    try:
        result = task.execute()
        print(f"DNS monitoring completed successfully")
        print(f"Tested {result['task_result']['servers_tested']} servers")
        print(f"Health: {result['task_result']['health_metrics']['health_percentage']:.1f}%")
    except Exception as e:
        print(f"DNS monitoring failed: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())