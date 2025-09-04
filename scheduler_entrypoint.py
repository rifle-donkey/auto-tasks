#!/usr/bin/env python3
"""
Scheduler Entry Point

Main entry point for the containerized automation scheduler.
Discovers tasks and runs the scheduler daemon.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

# Add automation_core to Python path
sys.path.insert(0, str(Path(__file__).parent))

from automation_core import TaskDiscovery, TaskScheduler


def setup_logging():
    """Setup logging configuration for container environment."""
    log_dir = Path("/var/log/automation")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "scheduler.log")
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Logging configured for scheduler")
    return logger


def main():
    """Main scheduler entry point."""
    parser = argparse.ArgumentParser(
        description='Automation Framework Scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Container Usage Examples:
  # Run scheduler daemon (default)
  docker run automation-framework

  # Check scheduler status
  docker exec automation-scheduler python3 scheduler_entrypoint.py --status
  
  # Enable/disable tasks
  docker exec automation-scheduler python3 scheduler_entrypoint.py --enable monitoring/dns_monitor
  docker exec automation-scheduler python3 scheduler_entrypoint.py --disable hardware/refresh_palo
  
  # Add custom schedule
  docker exec automation-scheduler python3 scheduler_entrypoint.py --add-schedule myTask "0 */6 * * *"
        """
    )
    
    parser.add_argument(
        '--daemon', 
        action='store_true', 
        default=True,
        help='Run scheduler as daemon (default)'
    )
    
    parser.add_argument(
        '--status', 
        action='store_true', 
        help='Show scheduler status and exit'
    )
    
    parser.add_argument(
        '--list-tasks', 
        action='store_true', 
        help='List all available tasks and exit'
    )
    
    parser.add_argument(
        '--enable', 
        metavar='TASK_NAME',
        help='Enable a scheduled task'
    )
    
    parser.add_argument(
        '--disable', 
        metavar='TASK_NAME',
        help='Disable a scheduled task'
    )
    
    parser.add_argument(
        '--add-schedule', 
        nargs=2, 
        metavar=('TASK_NAME', 'CRON_EXPR'),
        help='Add or update schedule for a task'
    )
    
    parser.add_argument(
        '--discover', 
        action='store_true',
        help='Discover tasks and update registry'
    )
    
    parser.add_argument(
        '--config-dir',
        default='/app/config',
        help='Configuration directory (default: /app/config)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default=os.getenv('LOG_LEVEL', 'INFO'),
        help='Log level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger.info("=== Automation Framework Scheduler ===")
    logger.info(f"Python path: {sys.path[0]}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Config directory: {args.config_dir}")
    
    # Ensure config directory exists
    config_dir = Path(args.config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Discover tasks
        logger.info("Discovering automation tasks...")
        # Use enhanced discovery with cleanup capabilities
        try:
            from automation_core.enhanced_runner import EnhancedTaskDiscovery
            discovery = EnhancedTaskDiscovery("scripts")
            registry = discovery.discover_tasks_with_cleanup()
        except ImportError:
            # Fallback to standard discovery
            discovery = TaskDiscovery("scripts")
            registry = discovery.discover_tasks()
        
        # Save task registry
        registry_file = config_dir / "task_registry.json"
        registry.save_registry(str(registry_file))
        logger.info(f"Task registry saved to {registry_file}")
        
        if args.discover:
            logger.info(f"Discovery complete. Found {len(registry.list_tasks())} tasks")
            return 0
        
        # Create scheduler
        schedules_file = config_dir / "schedules.yml"
        state_file = config_dir / "scheduler_state.json"
        
        logger.info(f"Initializing scheduler with schedules: {schedules_file}")
        scheduler = TaskScheduler(
            registry, 
            schedules_file=str(schedules_file),
            state_file=str(state_file)
        )
        
        # Handle different commands
        if args.status:
            import json
            status = scheduler.get_status()
            print(json.dumps(status, indent=2))
            return 0
        
        if args.list_tasks:
            from automation_core import TaskRunner
            runner = TaskRunner(registry)
            runner.list_available_tasks()
            return 0
        
        if args.enable:
            scheduler.enable_task(args.enable)
            logger.info(f"Enabled task: {args.enable}")
            return 0
        
        if args.disable:
            scheduler.disable_task(args.disable)
            logger.info(f"Disabled task: {args.disable}")
            return 0
        
        if args.add_schedule:
            task_name, cron_expr = args.add_schedule
            scheduler.add_schedule(task_name, cron_expr)
            logger.info(f"Added/updated schedule for {task_name}: {cron_expr}")
            return 0
        
        # Run scheduler daemon
        if args.daemon:
            logger.info("Starting scheduler daemon...")
            logger.info(f"Loaded {len(scheduler.schedules)} scheduled tasks")
            
            # Log enabled tasks
            enabled_tasks = [name for name, sched in scheduler.schedules.items() if sched.enabled]
            logger.info(f"Enabled tasks: {enabled_tasks}")
            
            # Start scheduler loop
            scheduler.run_scheduler_loop()
            
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
        return 0
    
    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())