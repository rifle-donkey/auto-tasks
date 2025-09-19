# ipam_sdk/utils/time_utils.py
"""Time and timestamp utilities for IPAM operations."""

import time
from datetime import datetime


def set_timestamp():
    """
    Generate current timestamp in standard format.
    
    Returns:
        str: Timestamp in 'YYYY-MM-DD HH:MM:SS' format
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


def exec_timestamp():
    """
    Generate execution timestamp in Unix epoch format.
    
    Returns:
        float: Current time as Unix timestamp
    """
    return time.time()


def ipm_timestamp():
    """
    Generate IPAM-specific timestamp format for logging and operations.
    
    Returns:
        str: Timestamp in 'Month DD, YYYY, H:MM AM/PM' format
    """
    now = datetime.now()
    return now.strftime("%B %d, %Y, %-I:%M %p")