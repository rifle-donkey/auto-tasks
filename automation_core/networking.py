"""
Network utilities module.
Provides network-related functionality for automation tasks.
"""
import ipaddress
import nmap
import ping3
import dns.resolver
import dns.reversename
import requests
import socket
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed


class NetworkUtilities:
    """Network utility functions for automation tasks."""
    
    def __init__(self, debug: bool = False):
        """
        Initialize network utilities.
        
        Args:
            debug: Enable debug logging
        """
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
    
    def is_ip_in_network(self, ip: str, network: str) -> bool:
        """
        Check if IP address is in network range.
        
        Args:
            ip: IP address to check
            network: Network in CIDR notation (e.g., "192.168.1.0/24")
            
        Returns:
            True if IP is in network, False otherwise
        """
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(network)
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
            return False
    
    def is_ip_in_exception_list(self, ip: str, exception_networks: List[str]) -> bool:
        """
        Check if IP address is in any of the exception networks.
        
        Args:
            ip: IP address to check  
            exception_networks: List of networks in CIDR notation
            
        Returns:
            True if IP is in any exception network
        """
        for network in exception_networks:
            try:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(network):
                    return True
            except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
                continue
        return False
    
    def ping_host(self, host: str, timeout: int = 2) -> bool:
        """
        Ping a host to check reachability.
        
        Args:
            host: Hostname or IP address
            timeout: Timeout in seconds
            
        Returns:
            True if host is reachable, False otherwise
        """
        try:
            result = ping3.ping(host, timeout=timeout)
            return result is not None
        except Exception as e:
            self.logger.debug(f"Ping failed for {host}: {e}")
            return False
    
    def icmp_check(self, server: str, timeout: int = 2) -> int:
        """
        Check ICMP reachability and return status code.
        
        Args:
            server: Server hostname or IP
            timeout: Timeout in seconds
            
        Returns:
            200 if reachable, 404 if not reachable
        """
        if self.ping_host(server, timeout):
            return 200
        return 404
    
    def nmap_scan(self, network: str, arguments: str = "-sn") -> Dict[str, Any]:
        """
        Perform nmap scan on network.
        
        Args:
            network: Network to scan in CIDR notation
            arguments: Nmap arguments
            
        Returns:
            Dictionary containing scan results
        """
        try:
            nm = nmap.PortScanner()
            scan_result = nm.scan(network, arguments=arguments)
            
            hosts_found = []
            for host in nm.all_hosts():
                hosts_found.append({
                    'host': host,
                    'hostname': nm[host].hostname(),
                    'state': nm[host].state()
                })
            
            return {
                'success': True,
                'hosts_found': hosts_found,
                'scan_info': scan_result.get('nmap', {}),
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'hosts_found': [],
                'scan_info': {},
                'error': str(e)
            }
    
    def dns_lookup(self, hostname: str, record_type: str = 'A') -> List[str]:
        """
        Perform DNS lookup for hostname.
        
        Args:
            hostname: Hostname to resolve
            record_type: DNS record type (A, AAAA, MX, etc.)
            
        Returns:
            List of resolved addresses/records
        """
        try:
            answers = dns.resolver.resolve(hostname, record_type)
            return [str(answer) for answer in answers]
        except Exception as e:
            self.logger.debug(f"DNS lookup failed for {hostname}: {e}")
            return []
    
    def reverse_dns_lookup(self, ip: str) -> Optional[str]:
        """
        Perform reverse DNS lookup for IP address.
        
        Args:
            ip: IP address to lookup
            
        Returns:
            Hostname if found, None otherwise
        """
        try:
            reverse_name = dns.reversename.from_address(ip)
            answers = dns.resolver.resolve(reverse_name, 'PTR')
            return str(answers[0]).rstrip('.')
        except Exception as e:
            self.logger.debug(f"Reverse DNS lookup failed for {ip}: {e}")
            return None
    
    def test_tcp_connection(self, host: str, port: int, timeout: int = 5) -> bool:
        """
        Test TCP connection to host:port.
        
        Args:
            host: Hostname or IP address
            port: TCP port number
            timeout: Connection timeout in seconds
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            sock = socket.create_connection((host, port), timeout)
            sock.close()
            return True
        except Exception as e:
            self.logger.debug(f"TCP connection failed to {host}:{port}: {e}")
            return False
    
    def test_https_connection(self, host: str, port: int = 443, timeout: int = 5, 
                             verify_ssl: bool = False) -> Tuple[int, str]:
        """
        Test HTTPS connection and return status.
        
        Args:
            host: Hostname or IP address
            port: HTTPS port (default 443)
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            Tuple of (status_code, status_message)
        """
        try:
            url = f"https://{host}:{port}"
            response = requests.get(
                url, 
                timeout=timeout, 
                verify=verify_ssl,
                headers={'User-Agent': 'AutomationFramework/1.0'}
            )
            
            if response.status_code == 200:
                return 200, "Healthy"
            else:
                return response.status_code, "Unhealthy"
                
        except requests.exceptions.SSLError as e:
            return 500, f"SSL Error: {str(e)}"
        except requests.exceptions.Timeout:
            return 500, "Connection timeout"
        except requests.exceptions.ConnectionError:
            return 500, "Connection refused"
        except Exception as e:
            return 500, f"Connection failed: {str(e)}"
    
    def probe_console_api(self, host: str, username: str, password: str, 
                         port: int = 48048) -> Tuple[int, str]:
        """
        Probe console API endpoint (HPE OOB style).
        
        Args:
            host: Console hostname or IP
            username: Username for authentication
            password: Password for authentication
            port: API port
            
        Returns:
            Tuple of (status_code, status_message)
        """
        requests.packages.urllib3.disable_warnings()
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        body = {
            "username": username,
            "password": password
        }
        
        try:
            url = f"https://{host}:{port}/api/v1/sessions/login"
            response = requests.post(
                url=url,
                headers=headers,
                json=body,
                verify=False,
                timeout=5
            )
            
            status_code = response.status_code
            
            if status_code == 200:
                return status_code, "Healthy"
            else:
                return status_code, "Unhealthy"
                
        except Exception as e:
            return 500, f"Unhealthy: {str(e)}"
    
    def dns_probe_threaded(self, nameservers: List[Dict[str, str]], 
                          test_domains: List[str], max_workers: int = 10) -> Dict[str, Any]:
        """
        Probe multiple DNS servers using threading.
        
        Args:
            nameservers: List of nameserver dicts with 'address' and 'name' keys
            test_domains: List of domains to test
            max_workers: Maximum number of worker threads
            
        Returns:
            Dictionary containing probe results
        """
        results = {
            'healthy_servers': [],
            'unhealthy_servers': [],
            'total_tested': len(nameservers),
            'healthy_count': 0,
            'health_percentage': 0
        }
        
        def probe_nameserver(ns_info: Dict[str, str]) -> Dict[str, Any]:
            """Probe a single nameserver."""
            ns_addr = ns_info['address']
            ns_name = ns_info.get('name', ns_addr)
            
            probe_result = {
                'address': ns_addr,
                'name': ns_name,
                'healthy': True,
                'test_results': {}
            }
            
            # Create custom resolver for this nameserver
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [ns_addr]
            resolver.timeout = 2
            resolver.lifetime = 5
            
            for domain in test_domains:
                try:
                    start_time = time.time()
                    answers = resolver.resolve(domain, 'A')
                    query_time = (time.time() - start_time) * 1000
                    
                    probe_result['test_results'][domain] = {
                        'success': True,
                        'response_time_ms': round(query_time, 2),
                        'answers': [str(answer) for answer in answers]
                    }
                    
                except Exception as e:
                    probe_result['healthy'] = False
                    probe_result['test_results'][domain] = {
                        'success': False,
                        'error': str(e)
                    }
            
            return probe_result
        
        import time
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ns = {executor.submit(probe_nameserver, ns): ns for ns in nameservers}
            
            for future in as_completed(future_to_ns):
                ns_result = future.result()
                
                if ns_result['healthy']:
                    results['healthy_servers'].append(ns_result)
                else:
                    results['unhealthy_servers'].append(ns_result)
        
        results['healthy_count'] = len(results['healthy_servers'])
        if results['total_tested'] > 0:
            results['health_percentage'] = round(
                (results['healthy_count'] / results['total_tested']) * 100, 2
            )
        
        return results
    
    def get_network_from_ip_and_prefix(self, ip: str, prefix: int) -> str:
        """
        Get network address from IP and prefix length.
        
        Args:
            ip: IP address
            prefix: Prefix length (e.g., 24 for /24)
            
        Returns:
            Network address in CIDR notation
        """
        try:
            network = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
            return str(network)
        except Exception as e:
            self.logger.error(f"Error calculating network for {ip}/{prefix}: {e}")
            return ""
    
    def calculate_network_size(self, prefix: int) -> int:
        """
        Calculate network size from prefix length.
        
        Args:
            prefix: Prefix length
            
        Returns:
            Number of host addresses in network
        """
        try:
            return 2 ** (32 - prefix) if 0 <= prefix <= 32 else 0
        except Exception:
            return 0
    
    def prefix_to_size(self, prefix: int) -> int:
        """Calculate size from prefix (alias for calculate_network_size)."""
        return self.calculate_network_size(prefix)
    
    def size_to_prefix(self, size: int) -> int:
        """
        Calculate prefix length from network size.
        
        Args:
            size: Network size (number of addresses)
            
        Returns:
            Prefix length
        """
        try:
            from math import log2
            if 0 < size <= 16777216:  # Max /8 network
                return int(32 - log2(size))
            else:
                self.logger.error(f"Invalid network size: {size}")
                return 0
        except (ValueError, OverflowError):
            self.logger.error(f"Invalid network size: {size}")
            return 0