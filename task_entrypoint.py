#!/usr/bin/env python3
"""
Task Entry Point

Entry point for executing individual automation tasks.
Used for manual task execution and testing.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add automation_core to Python path
sys.path.insert(0, str(Path(__file__).parent))

from automation_core import TaskDiscovery, TaskRunner


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration for task execution."""
    log_dir = Path("/var/log/automation")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "tasks.log")
        ]
    )
    
    return logging.getLogger(__name__)


def main():
    """Main task execution entry point."""
    parser = argparse.ArgumentParser(
        description='Automation Framework Task Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Container Usage Examples:
  # List all available tasks
  docker run --rm automation-framework python3 task_entrypoint.py --list
  
  # Run specific task
  docker run --rm automation-framework python3 task_entrypoint.py --task monitoring/console_health_monitor
  
  # Run all tasks in category
  docker run --rm automation-framework python3 task_entrypoint.py --category monitoring
  
  # Run task with custom config
  docker run --rm -v ./my-config.json:/config.json automation-framework \\
    python3 task_entrypoint.py --task hardware/refresh_ansible --config /config.json
        """
    )
    
    parser.add_argument(
        '--task',
        metavar='TASK_NAME',
        help='Run specific task (e.g., monitoring/dns_monitor, hardware/refresh_ansible)'
    )
    
    parser.add_argument(
        '--category',
        metavar='CATEGORY',
        help='Run all tasks in category (e.g., monitoring, hardware)'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available tasks'
    )
    
    parser.add_argument(
        '--discover',
        action='store_true',
        help='Discover and register tasks'
    )
    
    parser.add_argument(
        '--config',
        metavar='CONFIG_FILE',
        help='JSON configuration file for task execution'
    )
    
    parser.add_argument(
        '--output',
        metavar='OUTPUT_FILE',
        help='Save execution results to JSON file'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        metavar='SECONDS',
        help='Task execution timeout in seconds'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default=os.getenv('LOG_LEVEL', 'INFO'),
        help='Log level (default: INFO)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be executed without running tasks'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    logger.info("=== Automation Framework Task Runner ===")
    logger.info(f"Python path: {sys.path[0]}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Load configuration if provided
    config = {}
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return 1
    
    # Add timeout to config if specified
    if args.timeout:
        config['timeout'] = args.timeout
    
    try:
        # Discover tasks
        logger.info("Discovering automation tasks...")
        discovery = TaskDiscovery("scripts")
        registry = discovery.discover_tasks()
        
        logger.info(f"Discovered {len(registry.list_tasks())} tasks")
        
        if args.discover:
            # Save registry and exit
            registry_file = Path("config/task_registry.json")
            registry_file.parent.mkdir(exist_ok=True)
            registry.save_registry(str(registry_file))
            logger.info(f"Task registry saved to {registry_file}")
            return 0
        
        # Create task runner
        runner = TaskRunner(registry)
        
        if args.list:
            runner.list_available_tasks()
            return 0
        
        # Validate arguments
        if not args.task and not args.category:
            logger.error("Must specify either --task or --category")
            parser.print_help()
            return 1
        
        if args.task and args.category:
            logger.error("Cannot specify both --task and --category")
            return 1
        
        # Execute task(s)
        results = {}
        
        if args.task:
            if args.dry_run:
                task_class = registry.get_task(args.task)
                if task_class:
                    logger.info(f"Would execute task: {args.task}")
                    logger.info(f"Task description: {task_class.description}")
                    logger.info(f"Dependencies: {task_class.dependencies}")
                    logger.info(f"Max runtime: {task_class.max_runtime}s")
                else:
                    logger.error(f"Task not found: {args.task}")
                    return 1
            else:
                logger.info(f"Executing task: {args.task}")
                results[args.task] = runner.run_task(args.task, config)
        
        elif args.category:
            category_tasks = registry.get_tasks_by_category(args.category)
            if not category_tasks:
                logger.error(f"No tasks found in category: {args.category}")
                return 1
            
            if args.dry_run:
                logger.info(f"Would execute {len(category_tasks)} tasks in category: {args.category}")
                for task_name in category_tasks:
                    task_class = registry.get_task(task_name)
                    logger.info(f"  - {task_name}: {task_class.description}")
            else:
                logger.info(f"Executing {len(category_tasks)} tasks in category: {args.category}")
                results = runner.run_category(args.category, config)
        
        if args.dry_run:
            return 0
        
        # Process results
        success_count = 0
        total_count = len(results)
        
        for task_name, result in results.items():
            if result.get('success'):
                success_count += 1
                runtime = result.get('runtime_seconds', 0)
                logger.info(f"✓ {task_name} completed successfully in {runtime:.2f}s")
            else:
                error = result.get('error', 'Unknown error')
                logger.error(f"✗ {task_name} failed: {error}")
        
        logger.info(f"Execution summary: {success_count}/{total_count} tasks successful")
        
        # Save results if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            logger.info(f"Results saved to {output_path}")
        
        # Return appropriate exit code
        return 0 if success_count == total_count else 1
        
    except KeyboardInterrupt:
        logger.info("Task execution interrupted by user")
        return 1
    
    except Exception as e:
        logger.error(f"Task runner error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())