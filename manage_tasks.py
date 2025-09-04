#!/usr/bin/env python3
"""
Task Management Utility

Command-line utility for managing automation tasks and schedules.
Provides easy access to task operations within the container.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Add automation_core to Python path
sys.path.insert(0, str(Path(__file__).parent))

from automation_core import TaskDiscovery, TaskScheduler, TaskRunner


def setup_logging(level: str = "INFO"):
    """Setup basic logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def cmd_list_tasks(args, registry):
    """List all available tasks."""
    runner = TaskRunner(registry)
    runner.list_available_tasks()
    
    if args.json:
        tasks_info = {}
        for task_name in registry.list_tasks():
            metadata = registry.get_metadata(task_name)
            tasks_info[task_name] = metadata
        
        print(json.dumps(tasks_info, indent=2))


def cmd_show_schedules(args, scheduler):
    """Show current task schedules."""
    status = scheduler.get_status()
    
    if args.json:
        print(json.dumps(status, indent=2))
        return
    
    print(f"\n=== Task Schedules ===")
    print(f"Scheduler running: {status['running']}")
    print(f"Total tasks: {status['total_tasks']}")
    print(f"Enabled tasks: {status['enabled_tasks']}")
    print(f"Running tasks: {status['running_tasks']}")
    print()
    
    for task_name, task_info in status['tasks'].items():
        enabled_str = "✓" if task_info['enabled'] else "✗"
        running_str = " [RUNNING]" if task_info['is_running'] else ""
        
        print(f"{enabled_str} {task_name}{running_str}")
        print(f"    Schedule: {task_info['cron']}")
        
        if task_info['last_run']:
            last_run = datetime.fromisoformat(task_info['last_run']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"    Last run: {last_run}")
        
        if task_info['next_run']:
            next_run = datetime.fromisoformat(task_info['next_run']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"    Next run: {next_run}")
        
        # Show recent execution summary
        recent = task_info.get('recent_executions', [])
        if recent:
            success_count = sum(1 for exec in recent if exec['success'])
            print(f"    Recent: {success_count}/{len(recent)} successful")
        
        print()


def cmd_enable_task(args, scheduler):
    """Enable a task."""
    scheduler.enable_task(args.task_name)
    print(f"Enabled task: {args.task_name}")


def cmd_disable_task(args, scheduler):
    """Disable a task."""
    scheduler.disable_task(args.task_name)
    print(f"Disabled task: {args.task_name}")


def cmd_update_schedule(args, scheduler):
    """Update task schedule."""
    scheduler.add_schedule(
        args.task_name, 
        args.cron, 
        enabled=True,
        max_runtime=args.timeout,
        retry_count=args.retries
    )
    print(f"Updated schedule for {args.task_name}: {args.cron}")


def cmd_run_task(args, registry):
    """Run a task immediately."""
    runner = TaskRunner(registry)
    
    # Load config if provided
    config = {}
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1
    
    try:
        print(f"Running task: {args.task_name}")
        result = runner.run_task(args.task_name, config)
        
        if result['success']:
            runtime = result.get('runtime_seconds', 0)
            print(f"✓ Task completed successfully in {runtime:.2f} seconds")
            
            if args.verbose:
                print("\nTask Results:")
                print(json.dumps(result, indent=2, default=str))
        else:
            print(f"✗ Task failed: {result.get('error', 'Unknown error')}")
            return 1
            
    except Exception as e:
        print(f"Error running task: {e}")
        return 1
    
    return 0


def cmd_task_history(args, scheduler):
    """Show task execution history."""
    status = scheduler.get_status()
    task_info = status['tasks'].get(args.task_name)
    
    if not task_info:
        print(f"Task not found: {args.task_name}")
        return 1
    
    executions = task_info.get('recent_executions', [])
    
    if not executions:
        print(f"No execution history for task: {args.task_name}")
        return 0
    
    if args.json:
        print(json.dumps(executions, indent=2))
        return 0
    
    print(f"\n=== Execution History: {args.task_name} ===")
    print(f"Showing last {len(executions)} executions:\n")
    
    for i, exec_info in enumerate(reversed(executions), 1):
        status_icon = "✓" if exec_info['success'] else "✗"
        start_time = "N/A"
        runtime = "N/A"
        
        if exec_info.get('start_time'):
            start_time = datetime.fromisoformat(exec_info['start_time']).strftime('%Y-%m-%d %H:%M:%S')
        
        if exec_info.get('runtime'):
            runtime = f"{exec_info['runtime']:.2f}s"
        
        print(f"{i:2d}. {status_icon} {start_time} - Runtime: {runtime}")
        
        if not exec_info['success'] and exec_info.get('error'):
            print(f"     Error: {exec_info['error']}")
        
        if exec_info.get('pid'):
            print(f"     PID: {exec_info['pid']}")
    
    return 0


def cmd_health_check(args, registry, scheduler):
    """Perform health check on the automation system."""
    health_status = {
        'timestamp': datetime.now().isoformat(),
        'overall_status': 'healthy',
        'issues': []
    }
    
    # Check task discovery
    try:
        task_count = len(registry.list_tasks())
        health_status['discovered_tasks'] = task_count
        
        if task_count == 0:
            health_status['issues'].append("No tasks discovered")
            health_status['overall_status'] = 'warning'
            
    except Exception as e:
        health_status['issues'].append(f"Task discovery failed: {e}")
        health_status['overall_status'] = 'error'
    
    # Check scheduler status
    try:
        sched_status = scheduler.get_status()
        health_status['scheduler_running'] = sched_status['running']
        health_status['enabled_tasks'] = sched_status['enabled_tasks']
        health_status['running_tasks'] = sched_status['running_tasks']
        
        if not sched_status['running']:
            health_status['issues'].append("Scheduler not running")
            health_status['overall_status'] = 'error'
            
    except Exception as e:
        health_status['issues'].append(f"Scheduler check failed: {e}")
        health_status['overall_status'] = 'error'
    
    # Check file system access
    try:
        test_file = Path("/var/automation_file/health_check.tmp")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("health check")
        test_file.unlink()
        health_status['filesystem_writable'] = True
    except Exception as e:
        health_status['issues'].append(f"Filesystem not writable: {e}")
        health_status['overall_status'] = 'error'
    
    if args.json:
        print(json.dumps(health_status, indent=2))
    else:
        status_icon = {"healthy": "✓", "warning": "⚠", "error": "✗"}[health_status['overall_status']]
        print(f"\n=== System Health Check ===")
        print(f"Overall Status: {status_icon} {health_status['overall_status'].upper()}")
        print(f"Discovered Tasks: {health_status.get('discovered_tasks', 'Unknown')}")
        print(f"Scheduler Running: {health_status.get('scheduler_running', 'Unknown')}")
        print(f"Enabled Tasks: {health_status.get('enabled_tasks', 'Unknown')}")
        print(f"Running Tasks: {health_status.get('running_tasks', 'Unknown')}")
        print(f"Filesystem Writable: {health_status.get('filesystem_writable', 'Unknown')}")
        
        if health_status['issues']:
            print(f"\nIssues Found:")
            for issue in health_status['issues']:
                print(f"  • {issue}")
    
    # Return exit code based on health
    return 0 if health_status['overall_status'] == 'healthy' else 1


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Automation Task Management Utility',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--json', action='store_true', help='Output in JSON format')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    parser.add_argument('--config-dir', default='/app/config', help='Configuration directory')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List tasks command
    list_parser = subparsers.add_parser('list', help='List all available tasks')
    
    # Show schedules command
    schedules_parser = subparsers.add_parser('schedules', help='Show task schedules')
    
    # Enable task command
    enable_parser = subparsers.add_parser('enable', help='Enable a task')
    enable_parser.add_argument('task_name', help='Task name to enable')
    
    # Disable task command
    disable_parser = subparsers.add_parser('disable', help='Disable a task')
    disable_parser.add_argument('task_name', help='Task name to disable')
    
    # Update schedule command
    schedule_parser = subparsers.add_parser('schedule', help='Update task schedule')
    schedule_parser.add_argument('task_name', help='Task name')
    schedule_parser.add_argument('cron', help='Cron expression')
    schedule_parser.add_argument('--timeout', type=int, default=3600, help='Max runtime in seconds')
    schedule_parser.add_argument('--retries', type=int, default=1, help='Retry count')
    
    # Run task command
    run_parser = subparsers.add_parser('run', help='Run a task immediately')
    run_parser.add_argument('task_name', help='Task name to run')
    run_parser.add_argument('--config', help='Configuration file')
    
    # Task history command
    history_parser = subparsers.add_parser('history', help='Show task execution history')
    history_parser.add_argument('task_name', help='Task name')
    
    # Health check command
    health_parser = subparsers.add_parser('health', help='System health check')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    try:
        # Initialize components
        config_dir = Path(args.config_dir)
        config_dir.mkdir(parents=True, exist_ok=True)
        
        discovery = TaskDiscovery("scripts")
        registry = discovery.discover_tasks()
        
        schedules_file = config_dir / "schedules.yml"
        state_file = config_dir / "scheduler_state.json"
        
        scheduler = TaskScheduler(
            registry,
            schedules_file=str(schedules_file),
            state_file=str(state_file)
        )
        
        # Execute command
        if args.command == 'list':
            cmd_list_tasks(args, registry)
        
        elif args.command == 'schedules':
            cmd_show_schedules(args, scheduler)
        
        elif args.command == 'enable':
            cmd_enable_task(args, scheduler)
        
        elif args.command == 'disable':
            cmd_disable_task(args, scheduler)
        
        elif args.command == 'schedule':
            cmd_update_schedule(args, scheduler)
        
        elif args.command == 'run':
            return cmd_run_task(args, registry)
        
        elif args.command == 'history':
            return cmd_task_history(args, scheduler)
        
        elif args.command == 'health':
            return cmd_health_check(args, registry, scheduler)
        
        else:
            print(f"Unknown command: {args.command}")
            return 1
    
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=args.verbose)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())