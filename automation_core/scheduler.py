"""
Built-in task scheduler with cron support.
Manages individual task schedules within the container.
"""
import asyncio
import json
import logging
import multiprocessing
import os
import signal
import time
import yaml
from croniter import croniter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

from .runner import TaskRegistry, TaskRunner


class TaskExecution:
    """Represents a single task execution."""
    
    def __init__(self, task_name: str, config: Dict[str, Any]):
        self.task_name = task_name
        self.config = config
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.success: bool = False
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.process: Optional[multiprocessing.Process] = None
        self.pid: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert execution to dictionary for serialization."""
        return {
            'task_name': self.task_name,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'success': self.success,
            'error': self.error,
            'pid': self.pid,
            'runtime': (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else None
        }


class TaskSchedule:
    """Represents a scheduled task configuration."""
    
    def __init__(self, task_name: str, schedule_config: Dict[str, Any]):
        self.task_name = task_name
        self.cron = schedule_config.get('cron', '0 0 * * *')  # Default daily at midnight
        self.enabled = schedule_config.get('enabled', True)
        self.max_runtime = schedule_config.get('max_runtime', 3600)  # 1 hour default
        self.retry_count = schedule_config.get('retry_count', 1)
        self.config = schedule_config.get('config', {})
        
        # Validate cron expression
        try:
            croniter(self.cron)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{self.cron}': {e}")
        
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = self._calculate_next_run()
        self.current_execution: Optional[TaskExecution] = None
        self.execution_history: List[TaskExecution] = []
    
    def _calculate_next_run(self, base_time: Optional[datetime] = None) -> datetime:
        """Calculate next run time based on cron expression."""
        base = base_time or datetime.now()
        cron = croniter(self.cron, base)
        return cron.get_next(datetime)
    
    def is_due(self, current_time: Optional[datetime] = None) -> bool:
        """Check if task is due to run."""
        if not self.enabled:
            return False
        
        current = current_time or datetime.now()
        return self.next_run and current >= self.next_run
    
    def is_running(self) -> bool:
        """Check if task is currently running."""
        if not self.current_execution:
            return False
        
        if not self.current_execution.process:
            return False
        
        return self.current_execution.process.is_alive()
    
    def update_next_run(self) -> None:
        """Update next run time after execution."""
        self.last_run = datetime.now()
        self.next_run = self._calculate_next_run(self.last_run)
    
    def add_execution(self, execution: TaskExecution) -> None:
        """Add execution to history and manage current execution."""
        self.current_execution = execution
        self.execution_history.append(execution)
        
        # Keep only last 100 executions
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]
    
    def get_recent_executions(self, count: int = 10) -> List[TaskExecution]:
        """Get recent executions."""
        return self.execution_history[-count:]


class TaskScheduler:
    """Main scheduler for automation tasks."""
    
    def __init__(self, 
                 registry: TaskRegistry,
                 schedules_file: str = "config/schedules.yml",
                 state_file: str = "config/scheduler_state.json"):
        self.registry = registry
        self.schedules_file = schedules_file
        self.state_file = state_file
        self.schedules: Dict[str, TaskSchedule] = {}
        self.runner = TaskRunner(registry)
        self.running = False
        self.logger = logging.getLogger(__name__)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Load schedules and state
        self.load_schedules()
        self.load_state()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down scheduler...")
        self.running = False
    
    def load_schedules(self) -> None:
        """Load task schedules from YAML configuration."""
        if not os.path.exists(self.schedules_file):
            self.logger.warning(f"Schedules file {self.schedules_file} not found, creating default")
            self._create_default_schedules()
        
        try:
            with open(self.schedules_file, 'r') as f:
                config = yaml.safe_load(f)
            
            schedules_config = config.get('schedules', {})
            
            for task_name, schedule_config in schedules_config.items():
                try:
                    self.schedules[task_name] = TaskSchedule(task_name, schedule_config)
                    self.logger.info(f"Loaded schedule for {task_name}: {schedule_config.get('cron')}")
                except Exception as e:
                    self.logger.error(f"Error loading schedule for {task_name}: {e}")
        
        except Exception as e:
            self.logger.error(f"Error loading schedules file: {e}")
    
    def _create_default_schedules(self) -> None:
        """Create default schedules file."""
        os.makedirs(os.path.dirname(self.schedules_file), exist_ok=True)
        
        # Generate default schedules from task metadata
        default_schedules = {'schedules': {}}
        
        for task_name in self.registry.list_tasks():
            metadata = self.registry.get_metadata(task_name)
            if metadata and metadata.get('default_schedule'):
                default_schedules['schedules'][task_name] = {
                    'cron': metadata['default_schedule'],
                    'enabled': True,
                    'max_runtime': metadata.get('max_runtime', 3600),
                    'retry_count': metadata.get('retry_count', 1)
                }
        
        with open(self.schedules_file, 'w') as f:
            yaml.dump(default_schedules, f, default_flow_style=False, sort_keys=True)
        
        self.logger.info(f"Created default schedules file: {self.schedules_file}")
    
    def save_schedules(self) -> None:
        """Save current schedules to YAML file."""
        schedules_config = {'schedules': {}}
        
        for task_name, schedule in self.schedules.items():
            schedules_config['schedules'][task_name] = {
                'cron': schedule.cron,
                'enabled': schedule.enabled,
                'max_runtime': schedule.max_runtime,
                'retry_count': schedule.retry_count,
                'config': schedule.config
            }
        
        with open(self.schedules_file, 'w') as f:
            yaml.dump(schedules_config, f, default_flow_style=False, sort_keys=True)
    
    def load_state(self) -> None:
        """Load scheduler state from JSON file."""
        if not os.path.exists(self.state_file):
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            for task_name, task_state in state.items():
                if task_name in self.schedules:
                    schedule = self.schedules[task_name]
                    
                    if task_state.get('last_run'):
                        schedule.last_run = datetime.fromisoformat(task_state['last_run'])
                    
                    if task_state.get('next_run'):
                        schedule.next_run = datetime.fromisoformat(task_state['next_run'])
        
        except Exception as e:
            self.logger.error(f"Error loading scheduler state: {e}")
    
    def save_state(self) -> None:
        """Save scheduler state to JSON file."""
        state = {}
        
        for task_name, schedule in self.schedules.items():
            state[task_name] = {
                'last_run': schedule.last_run.isoformat() if schedule.last_run else None,
                'next_run': schedule.next_run.isoformat() if schedule.next_run else None,
                'enabled': schedule.enabled
            }
        
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def add_schedule(self, task_name: str, cron: str, enabled: bool = True, 
                    max_runtime: int = 3600, retry_count: int = 1) -> None:
        """Add or update a task schedule."""
        schedule_config = {
            'cron': cron,
            'enabled': enabled,
            'max_runtime': max_runtime,
            'retry_count': retry_count
        }
        
        self.schedules[task_name] = TaskSchedule(task_name, schedule_config)
        self.save_schedules()
        self.logger.info(f"Added/updated schedule for {task_name}: {cron}")
    
    def enable_task(self, task_name: str) -> None:
        """Enable a scheduled task."""
        if task_name in self.schedules:
            self.schedules[task_name].enabled = True
            self.save_schedules()
            self.logger.info(f"Enabled task: {task_name}")
    
    def disable_task(self, task_name: str) -> None:
        """Disable a scheduled task."""
        if task_name in self.schedules:
            self.schedules[task_name].enabled = False
            self.save_schedules()
            self.logger.info(f"Disabled task: {task_name}")
    
    def _execute_task_in_process(self, task_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task in separate process with timeout."""
        try:
            result = self.runner.run_task(task_name, config)
            return result
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'task_result': None
            }
    
    def execute_scheduled_task(self, task_name: str) -> None:
        """Execute a scheduled task with proper isolation and timeout."""
        schedule = self.schedules.get(task_name)
        if not schedule:
            self.logger.error(f"Schedule not found for task: {task_name}")
            return
        
        # Check if already running
        if schedule.is_running():
            self.logger.warning(f"Task {task_name} is already running, skipping")
            return
        
        # Create execution record
        execution = TaskExecution(task_name, schedule.config)
        execution.start_time = datetime.now()
        
        self.logger.info(f"Starting scheduled execution of {task_name}")
        
        try:
            # Start task in separate process
            process = multiprocessing.Process(
                target=self._execute_task_in_process,
                args=(task_name, schedule.config)
            )
            
            execution.process = process
            process.start()
            execution.pid = process.pid
            
            # Wait for completion with timeout
            process.join(timeout=schedule.max_runtime)
            
            execution.end_time = datetime.now()
            
            if process.is_alive():
                # Task exceeded timeout
                self.logger.warning(f"Task {task_name} exceeded timeout, terminating")
                process.terminate()
                process.join(timeout=10)  # Wait for graceful termination
                
                if process.is_alive():
                    process.kill()  # Force kill if necessary
                
                execution.success = False
                execution.error = f"Task exceeded timeout of {schedule.max_runtime} seconds"
            
            else:
                # Task completed normally
                exit_code = process.exitcode
                execution.success = exit_code == 0
                
                if exit_code != 0:
                    execution.error = f"Task exited with code {exit_code}"
                
                self.logger.info(f"Task {task_name} completed with exit code {exit_code}")
        
        except Exception as e:
            execution.end_time = datetime.now()
            execution.success = False
            execution.error = str(e)
            self.logger.error(f"Error executing task {task_name}: {e}")
        
        # Update schedule
        schedule.add_execution(execution)
        schedule.update_next_run()
        
        # Save state
        self.save_state()
        
        self.logger.info(f"Next run for {task_name}: {schedule.next_run}")
    
    def run_scheduler_loop(self) -> None:
        """Main scheduler loop."""
        self.running = True
        self.logger.info("Starting task scheduler...")
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Check each scheduled task
                for task_name, schedule in self.schedules.items():
                    if schedule.is_due(current_time):
                        self.logger.info(f"Task {task_name} is due for execution")
                        self.execute_scheduled_task(task_name)
                
                # Save state periodically
                self.save_state()
                
                # Sleep for 60 seconds before next check
                time.sleep(60)
            
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                time.sleep(60)  # Continue despite errors
        
        self.logger.info("Scheduler stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        status = {
            'running': self.running,
            'total_tasks': len(self.schedules),
            'enabled_tasks': len([s for s in self.schedules.values() if s.enabled]),
            'running_tasks': len([s for s in self.schedules.values() if s.is_running()]),
            'tasks': {}
        }
        
        for task_name, schedule in self.schedules.items():
            status['tasks'][task_name] = {
                'enabled': schedule.enabled,
                'cron': schedule.cron,
                'last_run': schedule.last_run.isoformat() if schedule.last_run else None,
                'next_run': schedule.next_run.isoformat() if schedule.next_run else None,
                'is_running': schedule.is_running(),
                'recent_executions': [exec.to_dict() for exec in schedule.get_recent_executions(5)]
            }
        
        return status


def main():
    """Main function for scheduler daemon."""
    import argparse
    from .runner import TaskDiscovery
    
    parser = argparse.ArgumentParser(description='Automation Task Scheduler')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--status', action='store_true', help='Show scheduler status')
    parser.add_argument('--enable', help='Enable specific task')
    parser.add_argument('--disable', help='Disable specific task')
    parser.add_argument('--add-schedule', nargs=2, metavar=('TASK', 'CRON'), 
                       help='Add schedule for task')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Discover tasks
    discovery = TaskDiscovery()
    registry = discovery.discover_tasks()
    
    # Create scheduler
    scheduler = TaskScheduler(registry)
    
    if args.status:
        status = scheduler.get_status()
        print(json.dumps(status, indent=2))
    
    elif args.enable:
        scheduler.enable_task(args.enable)
    
    elif args.disable:
        scheduler.disable_task(args.disable)
    
    elif args.add_schedule:
        task_name, cron = args.add_schedule
        scheduler.add_schedule(task_name, cron)
    
    elif args.daemon:
        scheduler.run_scheduler_loop()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()