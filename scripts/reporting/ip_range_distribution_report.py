from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.utils import set_timestamp
from automation_core.networking import make_api_request
from automation_core.reporting import write_list_to_csv, write_to_json
import os
import csv
import json
import ipaddress
from datetime import datetime


class IpRangeDistributionReport(BaseTask):
    name = "ip_range_distribution_report"
    description = "Generate IP range distribution reports by site and analyze network utilization"
    category = "reporting"
    dependencies = ["IPAM"]
    default_schedule = "0 9 * * 1"  # Weekly on Monday at 9 AM
    max_runtime = 1200
    
    def __init__(self):
        super().__init__()
        self.output_dir = "/var/automation_file/reporting"
        
    def execute(self):
        try:
            self.log("Starting IP range distribution report generation")
            
            # Get network data from IPAM
            networks_data = self._get_networks_data()
            if not networks_data:
                self.log("No network data found", level="WARNING")
                return {"status": "skipped", "reason": "no_data"}
            
            # Analyze IP range distributions
            site_distribution = self._analyze_site_distribution(networks_data)
            utilization_analysis = self._analyze_utilization(networks_data)
            
            # Generate reports
            report_files = []
            
            # Site distribution CSV report
            site_csv = self._generate_site_distribution_csv(site_distribution)
            if site_csv:
                report_files.append(site_csv)
            
            # Utilization analysis report
            util_json = self._generate_utilization_report(utilization_analysis)
            if util_json:
                report_files.append(util_json)
            
            # Summary statistics
            summary_stats = self._generate_summary_statistics(networks_data, site_distribution)
            
            self.log(f"Report generation complete. Analyzed {len(networks_data)} networks across {len(site_distribution)} sites")
            
            return {
                "status": "success",
                "networks_analyzed": len(networks_data),
                "sites_processed": len(site_distribution),
                "reports_generated": len(report_files),
                "report_files": report_files,
                "summary_stats": summary_stats,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"IP range distribution report failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_networks_data(self):
        """Get network data from IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            # Get all networks with utilization data
            response = make_api_request(
                method="GET",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/networks/",
                params={"include_utilization": "true"},
                auth=(ipam_user, ipam_pass),
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                networks = response.get("data", [])
                
                # Process and enrich network data
                processed_networks = []
                for network in networks:
                    processed_network = self._process_network_data(network)
                    if processed_network:
                        processed_networks.append(processed_network)
                
                self.log(f"Retrieved {len(processed_networks)} networks")
                return processed_networks
            
            return []
            
        except Exception as e:
            self.log(f"Error getting networks data: {e}", level="ERROR")
            return []
    
    def _process_network_data(self, network):
        """Process and enrich network data"""
        try:
            network_addr = network.get('network_address')
            prefix_len = network.get('prefix_length')
            
            if not network_addr or not prefix_len:
                return None
            
            # Create network object for calculations
            net = ipaddress.IPv4Network(f"{network_addr}/{prefix_len}", strict=False)
            
            processed = {
                'network': str(net),
                'network_address': str(net.network_address),
                'broadcast_address': str(net.broadcast_address),
                'prefix_length': net.prefixlen,
                'total_hosts': net.num_addresses - 2,  # Exclude network and broadcast
                'site': network.get('site', 'Unknown'),
                'vlan_id': network.get('vlan_id'),
                'description': network.get('description', ''),
                'network_type': network.get('network_type', 'Unknown'),
                'allocated_ips': network.get('allocated_ip_count', 0),
                'available_ips': network.get('available_ip_count', 0),
                'utilization_percent': network.get('utilization_percent', 0),
                'last_updated': network.get('last_updated'),
                'report_timestamp': set_timestamp()
            }
            
            return processed
            
        except Exception as e:
            self.log(f"Error processing network data: {e}", level="ERROR")
            return None
    
    def _analyze_site_distribution(self, networks_data):
        """Analyze IP range distribution by site"""
        try:
            site_distribution = {}
            
            for network in networks_data:
                site = network.get('site', 'Unknown')
                
                if site not in site_distribution:
                    site_distribution[site] = {
                        'total_networks': 0,
                        'total_ip_addresses': 0,
                        'allocated_addresses': 0,
                        'available_addresses': 0,
                        'network_types': {},
                        'utilization_stats': {
                            'high_utilization': 0,    # >80%
                            'medium_utilization': 0,  # 50-80%
                            'low_utilization': 0      # <50%
                        },
                        'networks': []
                    }
                
                site_data = site_distribution[site]
                
                # Update counters
                site_data['total_networks'] += 1
                site_data['total_ip_addresses'] += network.get('total_hosts', 0)
                site_data['allocated_addresses'] += network.get('allocated_ips', 0)
                site_data['available_addresses'] += network.get('available_ips', 0)
                
                # Network type distribution
                net_type = network.get('network_type', 'Unknown')
                site_data['network_types'][net_type] = \
                    site_data['network_types'].get(net_type, 0) + 1
                
                # Utilization categorization
                utilization = network.get('utilization_percent', 0)
                if utilization > 80:
                    site_data['utilization_stats']['high_utilization'] += 1
                elif utilization > 50:
                    site_data['utilization_stats']['medium_utilization'] += 1
                else:
                    site_data['utilization_stats']['low_utilization'] += 1
                
                # Store network details
                site_data['networks'].append(network)
            
            # Calculate site-level utilization percentages
            for site, data in site_distribution.items():
                if data['total_ip_addresses'] > 0:
                    data['overall_utilization'] = \
                        (data['allocated_addresses'] / data['total_ip_addresses']) * 100
                else:
                    data['overall_utilization'] = 0
            
            return site_distribution
            
        except Exception as e:
            self.log(f"Error analyzing site distribution: {e}", level="ERROR")
            return {}
    
    def _analyze_utilization(self, networks_data):
        """Analyze network utilization patterns"""
        try:
            utilization_analysis = {
                'high_utilization_networks': [],
                'underutilized_networks': [],
                'prefix_length_distribution': {},
                'utilization_by_type': {}
            }
            
            for network in networks_data:
                utilization = network.get('utilization_percent', 0)
                prefix_len = network.get('prefix_length', 0)
                net_type = network.get('network_type', 'Unknown')
                
                # High utilization networks (>85%)
                if utilization > 85:
                    utilization_analysis['high_utilization_networks'].append({
                        'network': network.get('network'),
                        'site': network.get('site'),
                        'utilization': utilization,
                        'total_hosts': network.get('total_hosts'),
                        'allocated_ips': network.get('allocated_ips')
                    })
                
                # Underutilized networks (<20% and >100 hosts)
                if utilization < 20 and network.get('total_hosts', 0) > 100:
                    utilization_analysis['underutilized_networks'].append({
                        'network': network.get('network'),
                        'site': network.get('site'),
                        'utilization': utilization,
                        'total_hosts': network.get('total_hosts'),
                        'wasted_ips': network.get('available_ips')
                    })
                
                # Prefix length distribution
                utilization_analysis['prefix_length_distribution'][prefix_len] = \
                    utilization_analysis['prefix_length_distribution'].get(prefix_len, 0) + 1
                
                # Utilization by network type
                if net_type not in utilization_analysis['utilization_by_type']:
                    utilization_analysis['utilization_by_type'][net_type] = {
                        'count': 0,
                        'total_utilization': 0,
                        'average_utilization': 0
                    }
                
                type_data = utilization_analysis['utilization_by_type'][net_type]
                type_data['count'] += 1
                type_data['total_utilization'] += utilization
                type_data['average_utilization'] = type_data['total_utilization'] / type_data['count']
            
            return utilization_analysis
            
        except Exception as e:
            self.log(f"Error analyzing utilization: {e}", level="ERROR")
            return {}
    
    def _generate_site_distribution_csv(self, site_distribution):
        """Generate CSV report for site distribution"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_file = f"{self.output_dir}/site_ip_distribution_{timestamp}.csv"
            
            # Flatten site distribution data for CSV
            csv_data = []
            for site, data in site_distribution.items():
                csv_data.append({
                    'site': site,
                    'total_networks': data['total_networks'],
                    'total_ip_addresses': data['total_ip_addresses'],
                    'allocated_addresses': data['allocated_addresses'],
                    'available_addresses': data['available_addresses'],
                    'overall_utilization_percent': round(data['overall_utilization'], 2),
                    'high_util_networks': data['utilization_stats']['high_utilization'],
                    'medium_util_networks': data['utilization_stats']['medium_utilization'],
                    'low_util_networks': data['utilization_stats']['low_utilization'],
                    'report_timestamp': set_timestamp()
                })
            
            write_list_to_csv(csv_data, csv_file)
            self.log(f"Site distribution CSV report generated: {csv_file}")
            return csv_file
            
        except Exception as e:
            self.log(f"Error generating site distribution CSV: {e}", level="ERROR")
            return None
    
    def _generate_utilization_report(self, utilization_analysis):
        """Generate JSON utilization analysis report"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_file = f"{self.output_dir}/utilization_analysis_{timestamp}.json"
            
            report_data = {
                "report_metadata": {
                    "generation_timestamp": set_timestamp(),
                    "report_type": "network_utilization_analysis"
                },
                "analysis": utilization_analysis
            }
            
            write_to_json(report_data, json_file)
            self.log(f"Utilization analysis report generated: {json_file}")
            return json_file
            
        except Exception as e:
            self.log(f"Error generating utilization report: {e}", level="ERROR")
            return None
    
    def _generate_summary_statistics(self, networks_data, site_distribution):
        """Generate summary statistics"""
        try:
            total_networks = len(networks_data)
            total_sites = len(site_distribution)
            total_ip_addresses = sum(net.get('total_hosts', 0) for net in networks_data)
            total_allocated = sum(net.get('allocated_ips', 0) for net in networks_data)
            
            summary = {
                'total_networks': total_networks,
                'total_sites': total_sites,
                'total_ip_addresses': total_ip_addresses,
                'total_allocated_ips': total_allocated,
                'overall_utilization_percent': (total_allocated / total_ip_addresses * 100) if total_ip_addresses > 0 else 0,
                'average_networks_per_site': round(total_networks / total_sites, 2) if total_sites > 0 else 0
            }
            
            return summary
            
        except Exception as e:
            self.log(f"Error generating summary statistics: {e}", level="ERROR")
            return {}


# Task registration for auto-discovery
task_class = IpRangeDistributionReport