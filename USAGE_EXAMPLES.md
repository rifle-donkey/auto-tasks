# Usage Examples

This guide provides practical examples for using the Automation Framework in various scenarios.

## Container Deployment Examples

### 1. Basic Scheduler Deployment

```bash
# Build the container
docker build -t automation-framework .

# Run with persistent storage
docker run -d \
  --name automation-scheduler \
  --restart unless-stopped \
  -v /var/automation_file:/var/automation_file \
  -v ~/.config:/root/.config:ro \
  -v ./git-repos:/app/git-repos \
  automation-framework

# Check status
docker exec automation-scheduler python3 manage_tasks.py health
```

### 2. Production Deployment with Docker Compose

```bash
# Create data directories
sudo mkdir -p /var/automation_file /var/log/automation

# Deploy with compose
docker-compose up -d

# Scale for high availability
docker-compose up -d --scale automation-scheduler=2
```

### 3. Development Environment

```bash
# Run with debug logging
docker run -d \
  --name automation-dev \
  -e LOG_LEVEL=DEBUG \
  -v $(pwd):/app \
  -v /var/automation_file:/var/automation_file \
  automation-framework

# Mount local scripts for development
docker run -d \
  --name automation-dev \
  -v $(pwd)/scripts:/app/scripts \
  -v $(pwd)/config:/app/config \
  automation-framework
```

## Task Management Examples

### 1. Viewing Available Tasks

```bash
# List all tasks with descriptions
docker exec automation-scheduler python3 manage_tasks.py list

# Get JSON output for scripting
docker exec automation-scheduler python3 manage_tasks.py list --json

# View specific task metadata
docker exec automation-scheduler python3 task_entrypoint.py --list | grep -A 5 "dns_monitor"
```

### 2. Managing Task Schedules

```bash
# View current schedules
docker exec automation-scheduler python3 manage_tasks.py schedules

# Enable/disable tasks
docker exec automation-scheduler python3 manage_tasks.py enable monitoring/dns_availability_monitor
docker exec automation-scheduler python3 manage_tasks.py disable hardware/refresh_palo_hwinfo

# Update task schedule
docker exec automation-scheduler python3 manage_tasks.py schedule \
  monitoring/console_health_monitor "*/15 * * * *"

# Add new task with custom timeout
docker exec automation-scheduler python3 manage_tasks.py schedule \
  custom/my_task "0 6 * * *" --timeout 7200 --retries 3
```

### 3. Manual Task Execution

```bash
# Run single task
docker exec automation-scheduler python3 manage_tasks.py run monitoring/dns_availability_monitor

# Run with verbose output
docker exec automation-scheduler python3 manage_tasks.py run monitoring/console_health_monitor --verbose

# Run all monitoring tasks
docker run --rm \
  -v /var/automation_file:/var/automation_file \
  -v ~/.config:/root/.config:ro \
  automation-framework python3 task_entrypoint.py --category monitoring
```

## Adding Custom Tasks

### 1. Simple Monitoring Task

Create `scripts/monitoring/custom_health_check.py`:

```python
from automation_core import BaseTask, NetworkUtilities, ReportingUtilities

class CustomHealthCheck(BaseTask):
    name = "custom_health_check"
    description = "Check health of custom services"
    category = "monitoring"
    dependencies = []
    default_schedule = "*/30 * * * *"  # Every 30 minutes
    max_runtime = 300
    
    def __init__(self, config=None):
        super().__init__(config)
        self.network_utils = NetworkUtilities()
        self.reporting = ReportingUtilities()
        
        # Configuration
        self.services = self.config.get('services', [
            {'name': 'web-server', 'host': '192.168.1.10', 'port': 80},
            {'name': 'database', 'host': '192.168.1.20', 'port': 5432}
        ])
    
    def run(self):
        self.log("Starting custom health check")
        
        results = {
            'healthy_services': [],
            'unhealthy_services': [],
            'timestamp': datetime.now().isoformat()
        }
        
        for service in self.services:
            self.log(f"Checking {service['name']} at {service['host']}:{service['port']}")
            
            is_healthy = self.network_utils.test_tcp_connection(
                service['host'], 
                service['port'], 
                timeout=5
            )
            
            service_result = {
                'name': service['name'],
                'host': service['host'],
                'port': service['port'],
                'healthy': is_healthy
            }
            
            if is_healthy:
                results['healthy_services'].append(service_result)
            else:
                results['unhealthy_services'].append(service_result)
        
        # Generate report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = f"custom_health_{timestamp}.json"
        self.reporting.write_to_json(results, report_file, category="monitoring")
        
        summary = {
            'total_services': len(self.services),
            'healthy_count': len(results['healthy_services']),
            'unhealthy_count': len(results['unhealthy_services']),
            'report_file': report_file
        }
        
        self.log(f"Health check complete: {summary['healthy_count']}/{summary['total_services']} services healthy")
        
        return summary
```

Deploy and configure:

```bash
# Restart container to discover new task
docker restart automation-scheduler

# Verify discovery
docker exec automation-scheduler python3 manage_tasks.py list | grep custom_health_check

# Configure and enable
docker exec automation-scheduler python3 manage_tasks.py schedule \
  monitoring/custom_health_check "*/30 * * * *"
docker exec automation-scheduler python3 manage_tasks.py enable monitoring/custom_health_check

# Test run
docker exec automation-scheduler python3 manage_tasks.py run monitoring/custom_health_check
```

### 2. Hardware Discovery Task

Create `scripts/hardware/custom_device_discovery.py`:

```python
from automation_core import BaseTask, IPAMClient, NetworkUtilities, ReportingUtilities
import ipaddress

class CustomDeviceDiscovery(BaseTask):
    name = "custom_device_discovery"
    description = "Discover devices in specified network ranges"
    category = "hardware"
    dependencies = ["IPAM"]
    default_schedule = "0 3 * * 0"  # Weekly on Sunday at 3 AM
    max_runtime = 7200  # 2 hours
    
    def __init__(self, config=None):
        super().__init__(config)
        self.network_utils = NetworkUtilities()
        self.reporting = ReportingUtilities()
        
        # Networks to scan
        self.scan_networks = self.config.get('scan_networks', [
            "192.168.1.0/24",
            "10.0.1.0/24"
        ])
    
    def run(self):
        self.log("Starting custom device discovery")
        
        discovered_devices = []
        
        for network in self.scan_networks:
            self.log(f"Scanning network: {network}")
            
            # Use nmap for network discovery
            scan_result = self.network_utils.nmap_scan(network, "-sn")
            
            if scan_result['success']:
                for host in scan_result['hosts_found']:
                    if host['state'] == 'up':
                        # Perform reverse DNS lookup
                        hostname = self.network_utils.reverse_dns_lookup(host['host'])
                        
                        device_info = {
                            'ip_address': host['host'],
                            'hostname': hostname or 'unknown',
                            'network': network,
                            'discovery_method': 'nmap_scan'
                        }
                        
                        discovered_devices.append(device_info)
                        self.log(f"Discovered device: {host['host']} ({hostname})")
        
        # Generate reports
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        
        # CSV report
        if discovered_devices:
            csv_file = f"discovered_devices_{timestamp}.csv"
            self.reporting.write_to_csv(discovered_devices, csv_file, category="hardware")
        
        # JSON report
        results = {
            'discovery_timestamp': datetime.now().isoformat(),
            'networks_scanned': self.scan_networks,
            'devices_discovered': discovered_devices,
            'total_count': len(discovered_devices)
        }
        
        json_file = f"device_discovery_{timestamp}.json"
        self.reporting.write_to_json(results, json_file, category="hardware")
        
        self.log(f"Discovery complete: found {len(discovered_devices)} devices")
        
        return {
            'networks_scanned': len(self.scan_networks),
            'devices_found': len(discovered_devices),
            'reports': [csv_file if discovered_devices else None, json_file]
        }
```

## Configuration Examples

### 1. Custom Schedule Configuration

Create `config/custom_schedules.yml`:

```yaml
schedules:
  # High-frequency monitoring
  monitoring/critical_service_check:
    cron: "* * * * *"           # Every minute
    enabled: true
    max_runtime: 30             # 30 seconds
    retry_count: 1
    config:
      services:
        - name: "critical-api"
          host: "api.example.com"
          port: 443
  
  # Business hours only
  monitoring/business_hours_check:
    cron: "*/15 8-18 * * 1-5"   # Every 15 min, 8 AM-6 PM, Mon-Fri
    enabled: true
    max_runtime: 300
    retry_count: 2
  
  # Maintenance window tasks
  hardware/monthly_cleanup:
    cron: "0 2 1 * *"           # First day of month at 2 AM
    enabled: true
    max_runtime: 14400          # 4 hours
    retry_count: 1
  
  # Custom configuration per task
  integration/data_sync:
    cron: "0 */6 * * *"         # Every 6 hours
    enabled: true
    max_runtime: 3600
    retry_count: 3
    config:
      batch_size: 1000
      timeout: 60
      endpoints:
        - "https://api1.example.com"
        - "https://api2.example.com"
```

Deploy custom configuration:

```bash
# Mount custom config
docker run -d \
  --name automation-custom \
  -v $(pwd)/config/custom_schedules.yml:/app/config/schedules.yml \
  automation-framework
```

### 2. Environment-Specific Configurations

Development environment:

```yaml
# config/dev_schedules.yml
schedules:
  monitoring/dns_availability_monitor:
    cron: "*/5 * * * *"         # More frequent in dev
    enabled: true
    max_runtime: 60
    config:
      debug: true
      test_domains:
        - "dev.example.com"
```

Production environment:

```yaml
# config/prod_schedules.yml
schedules:
  monitoring/dns_availability_monitor:
    cron: "*/15 * * * *"        # Standard frequency
    enabled: true
    max_runtime: 300
    config:
      debug: false
      test_domains:
        - "www.example.com"
        - "api.example.com"
```

## Monitoring and Troubleshooting

### 1. Health Monitoring

```bash
# System health check
docker exec automation-scheduler python3 manage_tasks.py health

# JSON output for monitoring systems
docker exec automation-scheduler python3 manage_tasks.py health --json | \
  jq '.overall_status'

# Check specific task history
docker exec automation-scheduler python3 manage_tasks.py history monitoring/dns_availability_monitor

# View recent logs
docker logs --tail 100 automation-scheduler
```

### 2. Performance Monitoring

```bash
# Check container resource usage
docker stats automation-scheduler

# View task execution times
docker exec automation-scheduler python3 manage_tasks.py schedules --json | \
  jq '.tasks[] | select(.recent_executions | length > 0) | {name: .name, recent: .recent_executions[-1].runtime}'

# Monitor file system usage
docker exec automation-scheduler df -h /var/automation_file/
```

### 3. Debugging Failed Tasks

```bash
# Run task with debug logging
docker exec automation-scheduler \
  python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from automation_core import TaskDiscovery, TaskRunner
discovery = TaskDiscovery('scripts')
registry = discovery.discover_tasks()
runner = TaskRunner(registry)
result = runner.run_task('monitoring/failing_task', {'debug': True})
print(result)
"

# Check task dependencies
docker exec automation-scheduler python3 manage_tasks.py list --json | \
  jq '.[] | select(.name == "monitoring/dns_monitor") | .dependencies'

# Verify credentials
docker exec automation-scheduler ls -la /root/.config/credential.ini
```

## Integration Examples

### 1. Monitoring System Integration

Export metrics to external monitoring:

```bash
# Export scheduler status
docker exec automation-scheduler python3 manage_tasks.py schedules --json > scheduler_status.json

# Create monitoring script
cat > monitor_automation.sh << 'EOF'
#!/bin/bash
STATUS=$(docker exec automation-scheduler python3 manage_tasks.py health --json)
HEALTHY=$(echo "$STATUS" | jq -r '.overall_status')

if [ "$HEALTHY" != "healthy" ]; then
    echo "CRITICAL: Automation framework unhealthy"
    echo "$STATUS" | jq '.issues[]'
    exit 2
else
    echo "OK: Automation framework healthy"
    exit 0
fi
EOF
chmod +x monitor_automation.sh
```

### 2. CI/CD Pipeline Integration

```yaml
# .github/workflows/automation-deploy.yml
name: Deploy Automation Framework
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Build automation framework
      run: docker build -t automation-framework:latest .
    
    - name: Test task discovery
      run: |
        docker run --rm automation-framework:latest \
          python3 task_entrypoint.py --discover
    
    - name: Deploy to production
      run: |
        docker-compose down
        docker-compose up -d
        
    - name: Health check
      run: |
        sleep 30
        docker exec automation-scheduler python3 manage_tasks.py health
```

### 3. Log Aggregation

```bash
# Configure log forwarding
docker run -d \
  --name automation-scheduler \
  --log-driver=syslog \
  --log-opt syslog-address=tcp://log-server:514 \
  --log-opt syslog-tag="automation-framework" \
  automation-framework

# Export logs to external system
docker logs automation-scheduler --since="24h" | \
  curl -X POST -H "Content-Type: application/json" \
  -d @- https://log-collector.example.com/api/logs
```

These examples demonstrate the flexibility and power of the automation framework for various deployment scenarios and operational needs.