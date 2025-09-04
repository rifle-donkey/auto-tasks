"""
Monitoring utilities module.
Provides monitoring and health check functionality for automation tasks.
"""
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from .networking import NetworkUtilities


class MonitoringUtilities:
    """Monitoring and health check utilities."""
    
    def __init__(self, debug: bool = False):
        """
        Initialize monitoring utilities.
        
        Args:
            debug: Enable debug logging
        """
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        self.network_utils = NetworkUtilities(debug)
        
        if debug:
            self.logger.setLevel(logging.DEBUG)
    
    def console_health_check(self, consoles: List[Dict[str, str]], 
                           username: str, password: str) -> Dict[str, Any]:
        """
        Perform health checks on console servers.
        
        Args:
            consoles: List of console dicts with 'address' and 'name' keys
            username: Username for authentication
            password: Password for authentication
            
        Returns:
            Dictionary containing health check results
        """
        results = {
            'reachable': [],
            'unreachable': [],
            'total_checked': len(consoles),
            'timestamp': datetime.now().isoformat(),
            'summary': {}
        }
        
        def check_console(console_info: Dict[str, str]) -> Dict[str, Any]:
            """Check a single console server."""
            console_addr = console_info.get('address', console_info.get('host', ''))
            console_name = console_info.get('name', console_addr)
            
            check_result = {
                'address': console_addr,
                'name': console_name,
                'timestamp': datetime.now().isoformat()
            }
            
            try:
                # First try primary address
                status_code, status_msg = self.network_utils.probe_console_api(
                    console_addr, username, password
                )
                
                check_result.update({
                    'status_code': status_code,
                    'status_message': status_msg,
                    'healthy': status_code == 200,
                    'connection_method': 'primary'
                })
                
                # If primary fails and standby address available, try standby
                if status_code != 200 and 'standby_address' in console_info:
                    standby_addr = console_info['standby_address']
                    standby_status, standby_msg = self.network_utils.probe_console_api(
                        standby_addr, username, password
                    )
                    
                    if standby_status == 200:
                        check_result.update({
                            'status_code': standby_status,
                            'status_message': standby_msg,
                            'healthy': True,
                            'connection_method': 'standby',
                            'standby_address': standby_addr,
                            'note': 'Primary failed, connected via standby'
                        })
                
            except Exception as e:
                check_result.update({
                    'status_code': 500,
                    'status_message': f"Exception: {str(e)}",
                    'healthy': False,
                    'connection_method': 'failed'
                })
            
            return check_result
        
        # Use threading for concurrent checks
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_console = {executor.submit(check_console, console): console 
                               for console in consoles}
            
            for future in as_completed(future_to_console):
                result = future.result()
                
                if result['healthy']:
                    results['reachable'].append(result)
                else:
                    results['unreachable'].append(result)
        
        # Generate summary
        results['summary'] = {
            'reachable_count': len(results['reachable']),
            'unreachable_count': len(results['unreachable']),
            'health_percentage': round(
                (len(results['reachable']) / len(consoles)) * 100, 2
            ) if consoles else 0
        }
        
        return results
    
    def dns_availability_monitor(self, nameservers: List[Dict[str, str]], 
                                test_domains: List[str] = None) -> Dict[str, Any]:
        """
        Monitor DNS server availability and performance.
        
        Args:
            nameservers: List of nameserver info dicts
            test_domains: Domains to test (defaults to common test domains)
            
        Returns:
            Dictionary containing DNS monitoring results
        """
        if test_domains is None:
            test_domains = [
                "short-ttl.ikea.com",
                "www.ikea.com", 
                "www.google.com"
            ]
        
        results = self.network_utils.dns_probe_threaded(
            nameservers, test_domains, max_workers=10
        )
        
        # Add monitoring-specific metadata
        results.update({
            'timestamp': datetime.now().isoformat(),
            'test_domains': test_domains,
            'monitoring_type': 'dns_availability'
        })
        
        # Calculate additional metrics
        if results['healthy_servers']:
            response_times = []
            for server in results['healthy_servers']:
                for domain, test_result in server['test_results'].items():
                    if test_result.get('success') and 'response_time_ms' in test_result:
                        response_times.append(test_result['response_time_ms'])
            
            if response_times:
                results['performance_metrics'] = {
                    'avg_response_time_ms': round(sum(response_times) / len(response_times), 2),
                    'min_response_time_ms': min(response_times),
                    'max_response_time_ms': max(response_times)
                }
        
        return results
    
    def network_reachability_test(self, targets: List[Dict[str, str]], 
                                 test_types: List[str] = None) -> Dict[str, Any]:
        """
        Test network reachability for multiple targets.
        
        Args:
            targets: List of target dicts with 'address', 'name', and optional 'type'
            test_types: Types of tests to perform ['icmp', 'tcp', 'https']
            
        Returns:
            Dictionary containing reachability test results
        """
        if test_types is None:
            test_types = ['icmp']
        
        results = {
            'reachable': [],
            'unreachable': [],
            'partial': [],  # Some tests passed, some failed
            'total_tested': len(targets),
            'timestamp': datetime.now().isoformat(),
            'test_types': test_types
        }
        
        def test_target(target_info: Dict[str, str]) -> Dict[str, Any]:
            """Test reachability for a single target."""
            target_addr = target_info.get('address', target_info.get('host', ''))
            target_name = target_info.get('name', target_addr)
            target_type = target_info.get('type', 'unknown')
            
            test_result = {
                'address': target_addr,
                'name': target_name,
                'type': target_type,
                'tests': {},
                'overall_status': 'unknown'
            }
            
            passed_tests = 0
            total_tests = 0
            
            # ICMP test
            if 'icmp' in test_types:
                total_tests += 1
                icmp_result = self.network_utils.icmp_check(target_addr)
                test_result['tests']['icmp'] = {
                    'status_code': icmp_result,
                    'success': icmp_result == 200,
                    'message': 'Reachable' if icmp_result == 200 else 'Unreachable'
                }
                if icmp_result == 200:
                    passed_tests += 1
            
            # TCP test (if port specified)
            if 'tcp' in test_types and 'port' in target_info:
                total_tests += 1
                port = int(target_info['port'])
                tcp_success = self.network_utils.test_tcp_connection(target_addr, port)
                test_result['tests']['tcp'] = {
                    'port': port,
                    'success': tcp_success,
                    'message': f'Port {port} {"open" if tcp_success else "closed/filtered"}'
                }
                if tcp_success:
                    passed_tests += 1
            
            # HTTPS test
            if 'https' in test_types:
                total_tests += 1
                https_port = int(target_info.get('https_port', 443))
                status_code, status_msg = self.network_utils.test_https_connection(
                    target_addr, https_port
                )
                test_result['tests']['https'] = {
                    'port': https_port,
                    'status_code': status_code,
                    'success': status_code == 200,
                    'message': status_msg
                }
                if status_code == 200:
                    passed_tests += 1
            
            # Determine overall status
            if passed_tests == total_tests:
                test_result['overall_status'] = 'reachable'
            elif passed_tests == 0:
                test_result['overall_status'] = 'unreachable'
            else:
                test_result['overall_status'] = 'partial'
            
            test_result['passed_tests'] = passed_tests
            test_result['total_tests'] = total_tests
            
            return test_result
        
        # Run tests concurrently
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_target = {executor.submit(test_target, target): target 
                              for target in targets}
            
            for future in as_completed(future_to_target):
                result = future.result()
                
                status = result['overall_status']
                if status == 'reachable':
                    results['reachable'].append(result)
                elif status == 'unreachable':
                    results['unreachable'].append(result)
                else:
                    results['partial'].append(result)
        
        # Generate summary
        results['summary'] = {
            'reachable_count': len(results['reachable']),
            'unreachable_count': len(results['unreachable']),
            'partial_count': len(results['partial']),
            'success_rate': round(
                (len(results['reachable']) / len(targets)) * 100, 2
            ) if targets else 0
        }
        
        return results
    
    def service_performance_metrics(self, services: List[Dict[str, str]], 
                                  samples: int = 5, interval: float = 1.0) -> Dict[str, Any]:
        """
        Collect performance metrics for services over time.
        
        Args:
            services: List of service info dicts with 'address', 'name', 'type'
            samples: Number of samples to collect
            interval: Interval between samples in seconds
            
        Returns:
            Dictionary containing performance metrics
        """
        results = {
            'services': {},
            'timestamp': datetime.now().isoformat(),
            'samples': samples,
            'interval': interval
        }
        
        for service in services:
            service_addr = service.get('address', service.get('host', ''))
            service_name = service.get('name', service_addr)
            service_type = service.get('type', 'generic')
            
            service_metrics = {
                'name': service_name,
                'address': service_addr,
                'type': service_type,
                'measurements': [],
                'statistics': {}
            }
            
            # Collect samples
            for sample_num in range(samples):
                if sample_num > 0:
                    time.sleep(interval)
                
                measurement = {
                    'sample': sample_num + 1,
                    'timestamp': datetime.now().isoformat()
                }
                
                if service_type == 'dns':
                    # DNS performance test
                    start_time = time.time()
                    dns_results = self.network_utils.dns_lookup(service_addr, 'A')
                    response_time = (time.time() - start_time) * 1000
                    
                    measurement.update({
                        'response_time_ms': round(response_time, 2),
                        'success': len(dns_results) > 0,
                        'result_count': len(dns_results)
                    })
                
                elif service_type == 'https':
                    # HTTPS performance test
                    start_time = time.time()
                    status_code, status_msg = self.network_utils.test_https_connection(service_addr)
                    response_time = (time.time() - start_time) * 1000
                    
                    measurement.update({
                        'response_time_ms': round(response_time, 2),
                        'status_code': status_code,
                        'success': status_code == 200,
                        'message': status_msg
                    })
                
                else:
                    # Generic ICMP test
                    start_time = time.time()
                    ping_result = self.network_utils.ping_host(service_addr)
                    response_time = (time.time() - start_time) * 1000
                    
                    measurement.update({
                        'response_time_ms': round(response_time, 2),
                        'success': ping_result
                    })
                
                service_metrics['measurements'].append(measurement)
            
            # Calculate statistics
            response_times = [m['response_time_ms'] for m in service_metrics['measurements'] 
                            if 'response_time_ms' in m]
            successful_samples = [m for m in service_metrics['measurements'] if m.get('success')]
            
            if response_times:
                service_metrics['statistics'] = {
                    'avg_response_time_ms': round(sum(response_times) / len(response_times), 2),
                    'min_response_time_ms': min(response_times),
                    'max_response_time_ms': max(response_times),
                    'success_rate': round((len(successful_samples) / samples) * 100, 2),
                    'total_samples': samples,
                    'successful_samples': len(successful_samples)
                }
            
            results['services'][service_name] = service_metrics
        
        return results