# ipam_sdk/utils/network.py
"""Network and IP address utilities for IPAM operations."""

import ipaddress
import logging
from socket import inet_ntoa
from struct import pack
from math import log2
import ping3
import dns.resolver as resolver


def is_ip(f_input):
    """
    Verify if the input is a valid IP address.
    
    Args:
        f_input (str): String to validate as IP address
        
    Returns:
        bool: True if valid IP address, False otherwise
    """
    try:
        ipaddress.ip_address(f_input)
        return True
    except ValueError:
        return False


# This function verify if the input hostname is a cname
def is_cname(f_hostname):
    f_resolver = resolver.Resolver()
    f_resolver.nameservers = ["10.59.253.2"]
    try:
        f_answers = f_resolver.resolve(f_hostname, 'CNAME')
        for f_rdata in f_answers:
            f_cname = f_rdata.target.to_text()
            if f_cname.endswith("."):
                f_cname = f_cname[:-1]
        f_is_cname = True
    except Exception as f_err:
        f_cname = f_err
        f_is_cname = False
    return f_is_cname, f_cname


def hex_to_ip(f_hex_addr):
    """
    Convert hexadecimal address to IP address format.
    
    Args:
        f_hex_addr (str): Hexadecimal address string
        
    Returns:
        str: IP address in dotted decimal notation
    """
    f_addr_long = int(f_hex_addr, 16)
    return inet_ntoa(pack(">L", f_addr_long))


def size_to_prefix(f_size):
    """
    Convert subnet size to CIDR prefix length.
    
    Args:
        f_size (str|int): Subnet size (number of addresses)
        
    Returns:
        int: CIDR prefix length, or 0 if invalid input
    """
    if not isinstance(f_size, int):
        try:
            f_size = int(f_size)
        except (ValueError, TypeError):
            logging.error(f"Value error, cannot convert to int: {f_size}")
            return None
    # Validate the integer value
    if f_size < 0 or f_size > 16777216:  # Max /8 subnet (2^24)
        logging.error(f"Size error, verify input: {f_size}")
        return None
    # Check if f_size is a power of 2
    if f_size & (f_size - 1) != 0:
        logging.error(f"Size must be a power of 2: {f_size}")
        return None
    
    return int(32 - log2(f_size))


# Function to convert prefix to subnet size
def prefix_to_size(f_prefix):
    """
    Convert CIDR prefix length to subnet size.
    
    Args:
        f_prefix (str|int): CIDR prefix length (0-32)
        
    Returns:
        int: Number of addresses in subnet, or None if invalid input
    """
    if not isinstance(f_prefix, int):
        try:
            f_prefix = int(f_prefix)
        except (ValueError, TypeError):
            logging.error(f"Value error, cannot convert to int: {f_prefix}")
            return None
    # Valid the integer value
    if f_prefix < 0 or f_prefix > 32:
        logging.error(f"Prefix error, verify input: {f_prefix}")
        return None

    return 2**(32 - f_prefix)


# Function convert prefix to netmask
def prefix_to_mask(f_prefix):
    if isinstance(f_prefix, int):
        if 0 <= f_prefix <= 32:
            return ('.'.join([str((0xffffffff << (32 - f_prefix) >> i) & 0xff)for i in (24, 16, 8, 0)]))
        else:
            logging.error(f"Prefix error, verify input: {f_prefix}")
            return None
    else:
        logging.error(f"Prefix error, verify input: {f_prefix}")
        return None


def icmp_check(f_addr):
    """
    Verify ICMP reachability of an IP address using ping.
    
    Args:
        f_addr (str): IP address to ping
        
    Returns:
        int: 200 if reachable, 404 if unreachable
    """
    f_icmp = ping3.ping(f_addr, timeout=2)
    if f_icmp:
        return 200
    else:
        return 404


def get_domain_suffix(f_fqdn):
    """
    Extract domain suffix from FQDN (last two domain components).
    
    Args:
        f_fqdn (str): Fully Qualified Domain Name
        
    Returns:
        str: Domain suffix (e.g., 'ikea.com' from 'server.ikea.com')
    """
    f_parts = f_fqdn.strip().split(".")
    if len(f_parts) >= 2:
        return ".".join(f_parts[-2:])
    return f_fqdn