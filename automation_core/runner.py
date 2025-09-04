"""
Task discovery and execution system.
Automatically discovers and manages automation tasks.
"""
import importlib
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type, Any

from .base_task import BaseTask


class TaskRegistry:
    """Registry for discovered automation tasks."""
    
    def __init__(self):
        self.tasks: Dict[str, Type[BaseTask]] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
    
    def register_task(self, task_class: Type[BaseTask]) -> None:
        """
        Register a task class in the registry.
        
        Args:
            task_class: BaseTask subclass to register
        """
        task_name = task_class.name or task_class.__name__
        
        # Handle category/name path
        if task_class.category:
            full_name = f"{task_class.category}/{task_name}"
        else:
            full_name = task_name
        
        self.tasks[full_name] = task_class
        self.metadata[full_name] = {
            'name': task_name,
            'class_name': task_class.__name__,
            'module': task_class.__module__,
            'category': task_class.category,
            'description': task_class.description,
            'dependencies': task_class.dependencies,
            'default_schedule': task_class.default_schedule,
            'max_runtime': task_class.max_runtime,
            'retry_count': task_class.retry_count
        }
    
    def get_task(self, task_name: str) -> Optional[Type[BaseTask]]:
        """Get task class by name."""
        return self.tasks.get(task_name)
    
    def list_tasks(self) -> List[str]:
        """List all registered task names."""
        return list(self.tasks.keys())
    
    def get_tasks_by_category(self, category: str) -> List[str]:
        """Get all tasks in a specific category."""
        return [name for name, metadata in self.metadata.items() 
                if metadata.get('category') == category]
    
    def get_metadata(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get task metadata."""
        return self.metadata.get(task_name)
    
    def save_registry(self, filepath: str) -> None:
        """Save task registry to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.metadata, f, indent=2, sort_keys=True)
    
    def load_registry(self, filepath: str) -> None:
        """Load task registry from JSON file."""
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                self.metadata.update(json.load(f))


class TaskDiscovery:
    """Discovers automation tasks by scanning the scripts directory."""
    
    def __init__(self, scripts_dir: str = "scripts", config_dir: str = "config"):
        self.scripts_dir = Path(scripts_dir)
        self.config_dir = Path(config_dir)
        self.registry = TaskRegistry()
        self.schedules_file = self.config_dir / "schedules.yml"
        self.previous_tasks = set()
    
    def discover_tasks(self) -> TaskRegistry:
        """
        Discover all automation tasks in the scripts directory.
        
        Returns:
            TaskRegistry containing all discovered tasks
        """
        if not self.scripts_dir.exists():
            print(f"Scripts directory '{self.scripts_dir}' does not exist")
            return self.registry
        
        # Scan for Python files recursively
        python_files = list(self.scripts_dir.rglob("*.py"))
        
        for python_file in python_files:
            if python_file.name.startswith('__'):
                continue  # Skip __init__.py and __pycache__
                
            self._import_and_register_tasks(python_file)
        
        return self.registry
    
    def _import_and_register_tasks(self, python_file: Path) -> None:
        """
        Import a Python file and register any BaseTask subclasses found.
        
        Args:
            python_file: Path to Python file to import
        """
        try:
            # Create module name from file path
            relative_path = python_file.relative_to(Path.cwd())
            module_name = str(relative_path).replace('/', '.').replace('.py', '')
            
            # Import the module
            spec = importlib.util.spec_from_file_location(module_name, python_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                # Find BaseTask subclasses in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseTask) and 
                        obj is not BaseTask and 
                        obj.__module__ == module_name):
                        
                        print(f"Discovered task: {obj.__name__} in {python_file}")
                        self.registry.register_task(obj)
                        
        except Exception as e:
            print(f"Error importing {python_file}: {e}")


class TaskRunner:
    """Executes automation tasks with proper error handling and logging."""
    
    def __init__(self, registry: TaskRegistry):
        self.registry = registry
    
    def run_task(self, task_name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run a specific automation task.
        
        Args:
            task_name: Name of task to run (e.g., "hardware/refresh_palo_hwinfo")
            config: Optional configuration for the task
            
        Returns:
            Dictionary containing execution results
        """
        task_class = self.registry.get_task(task_name)
        if not task_class:
            raise ValueError(f"Task '{task_name}' not found in registry")
        
        # Create and execute task instance
        task_instance = task_class(config)
        return task_instance.execute()
    
    def run_category(self, category: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Run all tasks in a specific category.
        
        Args:
            category: Category name (e.g., "monitoring")
            config: Optional configuration for all tasks
            
        Returns:
            Dictionary mapping task names to execution results
        """
        task_names = self.registry.get_tasks_by_category(category)
        if not task_names:
            raise ValueError(f"No tasks found in category '{category}'")
        
        results = {}
        for task_name in task_names:
            try:
                results[task_name] = self.run_task(task_name, config)
            except Exception as e:
                results[task_name] = {
                    'success': False,
                    'error': str(e),
                    'task_result': None
                }
        
        return results
    
    def list_available_tasks(self) -> None:
        """Print all available tasks organized by category."""
        tasks_by_category = {}
        
        for task_name in self.registry.list_tasks():
            metadata = self.registry.get_metadata(task_name)
            category = metadata.get('category', 'uncategorized')
            
            if category not in tasks_by_category:
                tasks_by_category[category] = []
            
            tasks_by_category[category].append({
                'name': task_name,
                'description': metadata.get('description', 'No description'),
                'schedule': metadata.get('default_schedule', 'No default schedule'),
                'runtime': metadata.get('max_runtime', 3600)
            })
        
        print("\n=== Available Automation Tasks ===")
        for category, tasks in sorted(tasks_by_category.items()):
            print(f"\n📁 {category.upper()}:")
            for task in tasks:
                print(f"  • {task['name']}")
                print(f"    {task['description']}")
                if task['schedule']:
                    print(f"    Default schedule: {task['schedule']}")
                print(f"    Max runtime: {task['runtime']}s")
                print()


def main():
    """Main function for task discovery and execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Automation Task Runner')
    parser.add_argument('--task', help='Run specific task (e.g., hardware/refresh_palo_hwinfo)')
    parser.add_argument('--category', help='Run all tasks in category (e.g., monitoring)')
    parser.add_argument('--list', action='store_true', help='List all available tasks')
    parser.add_argument('--discover', action='store_true', help='Discover and register tasks')
    parser.add_argument('--config', help='Configuration file for tasks')
    
    args = parser.parse_args()
    
    # Discover tasks with enhanced cleanup capabilities
    try:
        from .enhanced_runner import EnhancedTaskDiscovery
        discovery = EnhancedTaskDiscovery()
        registry = discovery.discover_tasks_with_cleanup()
    except ImportError:
        # Fallback to standard discovery
        discovery = TaskDiscovery()
        registry = discovery.discover_tasks()
    
    # Save registry
    registry.save_registry('config/task_registry.json')
    
    if args.discover:
        print(f"Discovered {len(registry.list_tasks())} tasks")
        return
    
    if args.list:
        runner = TaskRunner(registry)
        runner.list_available_tasks()
        return
    
    # Load config if provided
    config = {}
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)
    
    runner = TaskRunner(registry)
    
    if args.task:
        try:
            result = runner.run_task(args.task, config)
            print(f"Task {args.task} completed:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error running task {args.task}: {e}")
            sys.exit(1)
    
    elif args.category:
        try:
            results = runner.run_category(args.category, config)
            print(f"Category {args.category} completed:")
            for task_name, result in results.items():
                print(f"\n{task_name}: {'✓' if result.get('success') else '✗'}")
                if not result.get('success'):
                    print(f"  Error: {result.get('error')}")
        except Exception as e:
            print(f"Error running category {args.category}: {e}")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()