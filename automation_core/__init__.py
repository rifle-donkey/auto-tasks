# automation_core/__init__.py
"""
Automation Core Framework

A comprehensive automation framework providing:
- Task management and scheduling
- IPAM integration
- Network utilities
- Monitoring capabilities
- Standardized reporting
- Git operations
- Credential management
"""

from .base_task import BaseTask
from .base import IPAMClient
from .auth import get_credential
from .logging_config import setup_logging
from .git_ops import GitOperations
from .networking import NetworkUtilities
from .monitoring import MonitoringUtilities
from .reporting import ReportingUtilities
from .runner import TaskRegistry, TaskDiscovery, TaskRunner
from .scheduler import TaskScheduler
from .utils import *

__version__ = "1.0.0"
__author__ = "Automation Framework Team"

# Main exports
__all__ = [
    # Core classes
    'BaseTask',
    'IPAMClient',
    'TaskRegistry',
    'TaskDiscovery', 
    'TaskRunner',
    'TaskScheduler',
    
    # Utility classes
    'GitOperations',
    'NetworkUtilities',
    'MonitoringUtilities',
    'ReportingUtilities',
    
    # Functions
    'get_credential',
    'setup_logging',
    'set_timestamp',
    'exec_timestamp',
    'ipm_timestamp',
    'size_to_prefix',
    'hex_to_ip',
    'write_list_to_csv',
    'write_to_splunk',
    'archive_file'
]