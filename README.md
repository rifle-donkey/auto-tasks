# Automation Framework

A containerized, self-discovering automation framework with built-in task scheduling for network infrastructure management.

## Features

- **Auto-Discovery**: Automatically discovers new automation tasks by scanning the scripts directory
- **Individual Scheduling**: Each task can be scheduled independently with cron expressions
- **Containerized Deployment**: Single container handles all automation needs
- **Shared Framework**: Common modules eliminate code duplication (90%+ reduction)
- **Monitoring & Reporting**: Built-in health checks, logging, and report generation
- **Easy Expansion**: Add new tasks by dropping Python files in the appropriate directory

## Quick Start

### 1. Build the Container

```bash
docker build -t automation-framework .
```

### 2. Run with Scheduler (Default)

```bash
docker run -d \
  --name automation-scheduler \
  -v /var/automation_file:/var/automation_file \
  -v ~/.config:/root/.config:ro \
  -v ./git-repos:/app/git-repos \
  automation-framework
```

### 3. Run Single Task

```bash
docker run --rm \
  -v /var/automation_file:/var/automation_file \
  -v ~/.config:/root/.config:ro \
  automation-framework python3 task_entrypoint.py --task monitoring/dns_availability_monitor
```

## Container Modes

### Scheduler Daemon (Default)
Runs continuously, executing tasks based on their schedules:

```bash
# Start scheduler
docker run -d automation-framework

# Check status
docker exec automation-scheduler python3 manage_tasks.py schedules

# View logs
docker logs automation-scheduler
```

### Single Task Execution
Execute specific tasks on demand:

```bash
# Run specific task
docker run --rm automation-framework python3 task_entrypoint.py --task hardware/refresh_ansible_hwinfo

# Run all tasks in category
docker run --rm automation-framework python3 task_entrypoint.py --category monitoring

# List available tasks
docker run --rm automation-framework python3 task_entrypoint.py --list
```

### Task Management
Manage schedules and task execution:

```bash
# List all tasks
docker exec automation-scheduler python3 manage_tasks.py list

# Show current schedules
docker exec automation-scheduler python3 manage_tasks.py schedules

# Enable/disable tasks
docker exec automation-scheduler python3 manage_tasks.py enable monitoring/dns_monitor
docker exec automation-scheduler python3 manage_tasks.py disable hardware/refresh_palo

# Update task schedule
docker exec automation-scheduler python3 manage_tasks.py schedule myTask "0 */6 * * *"

# Run task immediately
docker exec automation-scheduler python3 manage_tasks.py run monitoring/console_health_monitor

# Check system health
docker exec automation-scheduler python3 manage_tasks.py health
```

## Project Structure

```
auto-tasks/
├── automation_core/           # Shared framework
│   ├── base_task.py          # Base class for all tasks
│   ├── scheduler.py          # Built-in task scheduler
│   ├── runner.py             # Task discovery and execution
│   ├── auth.py               # Credential management
│   ├── ipam_client.py        # IPAM integration
│   ├── git_ops.py            # Git operations
│   ├── networking.py         # Network utilities
│   ├── monitoring.py         # Health check utilities
│   └── reporting.py          # Reporting and logging
├── scripts/                  # Auto-discovered tasks
│   ├── hardware/             # Hardware management tasks
│   ├── monitoring/           # Health monitoring tasks
│   ├── discovery/            # Network discovery tasks
│   └── integration/          # System integration tasks
├── config/
│   ├── schedules.yml         # Task scheduling configuration
│   └── logging.conf          # Logging configuration
├── docker-compose.yml        # Multi-service deployment
├── Dockerfile               # Container definition
└── requirements.txt         # Python dependencies
```

## Adding New Automation Tasks

### 1. Create Task Script

Create a new Python file in the appropriate category directory:

```python
# scripts/monitoring/new_monitor.py
from automation_core import BaseTask, MonitoringUtilities

class NewMonitor(BaseTask):
    name = "new_monitor"
    description = "Monitor something new"
    category = "monitoring"
    dependencies = ["IPAM"]
    default_schedule = "*/10 * * * *"  # Every 10 minutes
    max_runtime = 300
    
    def run(self):
        self.log("Starting new monitoring task")
        
        # Use shared utilities
        monitoring = MonitoringUtilities()
        results = monitoring.some_check()
        
        self.log("Monitoring complete")
        return results
```

### 2. Container Auto-Discovers

The container automatically discovers new tasks on startup:

```bash
# Restart container to discover new tasks
docker restart automation-scheduler

# Or manually trigger discovery
docker exec automation-scheduler python3 manage_tasks.py list
```

### 3. Configure Schedule (Optional)

Add to `config/schedules.yml` or use management commands:

```bash
docker exec automation-scheduler python3 manage_tasks.py schedule monitoring/new_monitor "*/10 * * * *"
docker exec automation-scheduler python3 manage_tasks.py enable monitoring/new_monitor
```

## Configuration

### Credentials
Store encrypted credentials in `~/.config/credential.ini`:

```ini
[KEY]
crypto_key = your-fernet-key

[IPAM]
hash_usr = encrypted-username
hash_pwd = encrypted-password

[HPE_OOB]
hash_usr = encrypted-username
hash_pwd = encrypted-password
```

### Task Schedules
Configure in `config/schedules.yml`:

```yaml
schedules:
  monitoring/dns_monitor:
    cron: "*/15 * * * *"       # Every 15 minutes
    enabled: true
    max_runtime: 300           # 5 minutes
    retry_count: 1
    config:
      debug: false
      test_domains:
        - "www.example.com"
```

## Docker Compose Deployment

For production deployment with persistence:

```bash
# Start all services
docker-compose up -d

# Start with specific profiles
docker-compose --profile dashboard up -d

# Scale for high availability
docker-compose up -d --scale automation-scheduler=2
```

### Environment Variables

- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `SCHEDULER_CHECK_INTERVAL`: Seconds between schedule checks (default: 60)
- `MAX_CONCURRENT_TASKS`: Maximum concurrent task executions (default: 5)
- `TASK_TIMEOUT_DEFAULT`: Default task timeout in seconds (default: 3600)

## Monitoring & Logging

### Container Logs
```bash
# View scheduler logs
docker logs -f automation-scheduler

# View specific time range
docker logs --since="2h" automation-scheduler

# Export logs
docker logs automation-scheduler > automation.log
```

### Task Execution History
```bash
# View task history
docker exec automation-scheduler python3 manage_tasks.py history monitoring/dns_monitor

# System health check
docker exec automation-scheduler python3 manage_tasks.py health --json
```

### Output Files
Task outputs are stored in `/var/automation_file/` organized by category:
- `/var/automation_file/monitoring/` - Health check reports
- `/var/automation_file/hardware/` - Hardware update logs
- `/var/automation_file/discovery/` - Network discovery results

## Development

### Adding Shared Utilities
Extend the framework by adding modules to `automation_core/`:

```python
# automation_core/new_utility.py
class NewUtility:
    def helper_function(self):
        # Shared functionality
        pass
```

### Testing
```bash
# Run tests
docker run --rm -v $(pwd):/app automation-framework python3 -m pytest tests/

# Test specific task
docker run --rm automation-framework python3 task_entrypoint.py --task monitoring/dns_monitor --dry-run
```

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run task discovery
python3 -m automation_core.runner --discover

# Run scheduler locally
python3 scheduler_entrypoint.py --daemon
```

## Migration from Existing Scripts

The framework is designed for easy migration:

1. **Copy existing script** to appropriate `scripts/` directory
2. **Refactor to inherit from BaseTask** and use shared modules
3. **Container auto-discovers** the new task
4. **Configure schedule** and enable task

Example migration:
- Before: 22 individual scripts with duplicated code
- After: Unified framework with 90%+ code reduction and consistent patterns

## Troubleshooting

### Task Not Discovered
```bash
# Check script syntax
python3 -c "import scripts.category.task_name"

# View discovery logs
docker logs automation-scheduler | grep -i discover
```

### Task Not Running
```bash
# Check if enabled
docker exec automation-scheduler python3 manage_tasks.py schedules | grep task_name

# Check dependencies
docker exec automation-scheduler python3 manage_tasks.py run task_name --verbose
```

### Permission Issues
```bash
# Check volume mounts
docker exec automation-scheduler ls -la /var/automation_file/

# Check credential access
docker exec automation-scheduler ls -la /root/.config/
```

## Support

For issues and questions:
- Check container logs: `docker logs automation-scheduler`
- Review task execution: `python3 manage_tasks.py history task_name`
- System health: `python3 manage_tasks.py health`