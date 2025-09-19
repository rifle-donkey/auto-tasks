# ipam_sdk/utils/validation.py
"""Input validation utilities for IPAM operations."""

from .network import is_ip


def validate_fqdn(fqdn):
    """
    Validate if input is a properly formatted FQDN.
    
    Args:
        fqdn (str): Fully Qualified Domain Name to validate
        
    Returns:
        bool: True if valid FQDN format, False otherwise
    """
    if not fqdn or not isinstance(fqdn, str):
        return False
    
    # Basic FQDN validation
    parts = fqdn.strip().split('.')
    if len(parts) < 2:
        return False
    
    # Check each part is valid
    for part in parts:
        if not part or len(part) > 63:
            return False
        if not part.replace('-', '').isalnum():
            return False
        if part.startswith('-') or part.endswith('-'):
            return False
    
    return True


def validate_ip_or_fqdn(input_value):
    """
    Validate if input is either a valid IP address or FQDN.
    
    Args:
        input_value (str): Value to validate
        
    Returns:
        str: 'ip', 'fqdn', or 'invalid'
    """
    if not input_value or not isinstance(input_value, str):
        return 'invalid'
    
    if is_ip(input_value):
        return 'ip'
    elif validate_fqdn(input_value):
        return 'fqdn'
    else:
        return 'invalid'


def validate_ttl(ttl):
    """
    Validate TTL (Time To Live) value for DNS records.
    
    Args:
        ttl (str|int): TTL value to validate
        
    Returns:
        bool: True if valid TTL (0-2147483647), False otherwise
    """
    try:
        ttl_int = int(ttl)
        return 0 <= ttl_int <= 2147483647
    except (ValueError, TypeError):
        return False