# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a containerized Python automation framework for network infrastructure management. The repository has been transformed from individual scripts into a unified, scalable automation platform with auto-discovery capabilities and individual task scheduling. The framework focuses on IPAM integration, device monitoring, hardware information management, and network discovery.

## Core Architecture

### Containerized Framework
The repository implements a modern containerized automation platform with these key features:
- **Auto-Discovery**: New tasks are automatically discovered by placing scripts in the `scripts/` directory
- **Individual Scheduling**: Each task can run on independent cron schedules (e.g., `refresh_hwinfo_palo` at different intervals than `refresh_hwinfo_versa`)
- **Process Isolation**: Tasks run in isolated processes with timeouts and retry mechanisms
- **Shared Utilities**: Common functionality extracted into reusable modules to eliminate code duplication
- **Container Deployment**: Consistent execution environment with Podman and podman-compose

### Framework Components (`automation_core/`)

**Core Framework:**
- **`base_task.py`**: BaseTask abstract class defining standard interface for all automation tasks
- **`scheduler.py`**: Built-in cron scheduler supporting individual task scheduling with croniter
- **`runner.py`**: Task discovery engine and execution manager with process isolation
- **`registry.py`**: Task metadata management and auto-discovery system

**Shared Utilities:**
- **`auth.py`**: Encrypted credential management using Fernet encryption
- **`ipam_client.py`**: Centralized IPAM API client with authentication and error handling
- **`git_ops.py`**: Git repository operations for configuration data management
- **`networking.py`**: Network utilities (ping, DNS resolution, nmap scanning, etc.)
- **`monitoring.py`**: Health checking and system monitoring capabilities
- **`reporting.py`**: Standardized reporting (CSV, JSON, Splunk) with consistent formatting
- **`logging_config.py`**: Centralized logging configuration for debugging and audit trails

### Task Categories (`scripts/`)

**Hardware Management (`scripts/hardware/`):**
- `refresh_ansible_hwinfo.py`: Hardware information refresh using Ansible integration
- *[19+ additional hardware refresh tasks to be migrated]*

**Monitoring (`scripts/monitoring/`):**
- `console_health_monitor.py`: HPE OOB console connectivity monitoring with HTTPS health checks
- `dns_availability_monitor.py`: DNS service availability and performance monitoring  
- *[Additional monitoring tasks to be migrated]*

**Network Discovery (`scripts/discovery/`):**
- *[Network discovery and import tasks to be migrated]*

**Analysis and Reporting (`scripts/analysis/`):**
- *[Analysis and reporting tasks to be migrated]*

### Legacy Scripts (Root Directory)
22 original standalone scripts remain in the root directory awaiting transformation:
- Hardware refresh scripts for various platforms (Arista, Aruba, F5, Palo Alto, Versa, HPE)
- Network import/discovery scripts (SVI import, address discovery)
- Monitoring and reporting utilities
- Analysis and metric generation scripts

## Container Deployment

### Container Configuration
- **`Dockerfile`**: Multi-stage Python 3.11 container with network tools, proper permissions, and security hardening (Podman-compatible)
- **`docker-compose.yml`**: Multi-service deployment supporting daemon mode, single-task execution, and management interface (podman-compose compatible)
- **`requirements.txt`**: Complete dependency management including croniter, PyYAML, GitPython, and network libraries

### Execution Modes
1. **Daemon Mode**: Continuous scheduler running all tasks per their individual cron schedules
2. **Single Task Mode**: Execute individual tasks on-demand or via external schedulers
3. **Management Mode**: Task status monitoring, schedule management, and system administration

### Entry Points
- **`scheduler_entrypoint.py`**: Container daemon mode with multi-task scheduling
- **`task_entrypoint.py`**: Single task execution for targeted runs
- **`manage_tasks.py`**: Task management utility for schedule and status operations

## Task Development Pattern

### BaseTask Implementation
All tasks inherit from BaseTask and implement this standard interface:

```python
from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.ipam_client import IPAMClient

class MyTask(BaseTask):
    name = "my_task"
    description = "Description of task functionality"
    category = "hardware"
    default_schedule = "0 2 * * *"  # Daily at 2 AM
    max_runtime = 1800  # 30 minutes
    
    def execute(self) -> Dict[str, Any]:
        # Task implementation
        return {"status": "success", "processed": 100}
```

### Auto-Discovery
Tasks are automatically discovered by:
1. Placing Python files in `scripts/` subdirectories
2. Implementing BaseTask interface
3. Defining task metadata (name, schedule, category)
4. No additional configuration required

### Individual Scheduling
Each task can specify independent schedules:
- Configure via `config/schedules.yml` or task metadata
- Support for cron expressions (minute, hour, day, month, weekday)
- Tasks run independently without blocking each other
- Configurable timeouts and retry mechanisms

## Credential Management

Enhanced secure credential storage:
- Fernet encryption for API credentials stored in `~/.config/credential.ini`
- Multiple credential sections (IPAM, HPE_OOB, vendor-specific)
- Container-safe credential mounting
- Support for environment variable overrides
- Automated credential validation and rotation

## Running the Framework

### Container Deployment
```bash
# Start daemon scheduler
podman-compose up -d scheduler

# Run single task
podman-compose run --rm task-runner python task_entrypoint.py my_task

# Management interface
podman-compose run --rm task-runner python manage_tasks.py --list
```

### Development Mode
```bash
# Install dependencies
pip install -r requirements.txt

# Run scheduler locally
python scheduler_entrypoint.py

# Execute single task
python task_entrypoint.py task_name
```

## Migration Guide

### Transforming Legacy Scripts
1. Create new file in appropriate `scripts/` subdirectory
2. Implement BaseTask interface
3. Extract shared logic to use `automation_core` utilities
4. Define task metadata and scheduling
5. Update any hardcoded paths or configurations
6. Test in container environment

### Framework Benefits
- **90% Code Reduction**: Shared utilities eliminate duplication
- **Consistent Execution**: Container environment ensures reliability
- **Easy Expansion**: Drop scripts in directories for auto-discovery
- **Independent Scheduling**: Each task runs on optimal schedule
- **Better Monitoring**: Centralized logging and health checks
- **Secure Deployment**: Container isolation and credential encryption

## Development Setup

### Prerequisites
- Podman and podman-compose for rootless container deployment
- Python 3.11+ for local development
- Access to `~/.config/credential.ini` with encrypted credentials
- Network connectivity to IPAM and managed devices

### Dependencies
All dependencies managed via `requirements.txt`:
```bash
pip install -r requirements.txt
```

Key dependencies: requests, tqdm, cryptography, croniter, PyYAML, GitPython, podman, paramiko, netmiko

## Framework Status

**Current State:**
- ✅ Complete automation_core framework (16+ modules)
- ✅ Container infrastructure with multi-mode deployment  
- ✅ 3 tasks successfully transformed and tested
- ✅ Auto-discovery and individual scheduling implemented
- ⏳ 22 legacy scripts awaiting transformation
- ⏳ Production deployment configuration

**Next Steps:**
1. Transform remaining legacy scripts by category
2. Complete container deployment testing
3. Implement monitoring dashboard
4. Add task dependency management
5. Create automated testing framework