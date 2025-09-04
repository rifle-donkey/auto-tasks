"""
Enhanced Task Discovery with Dynamic Schedule Management

Additional functionality for detecting removed tasks and cleaning up orphaned schedules.
"""

import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from .runner import TaskDiscovery as BaseTaskDiscovery


class EnhancedTaskDiscovery(BaseTaskDiscovery):
    """Enhanced Task Discovery with dynamic schedule management and orphan cleanup."""
    
    def __init__(self, scripts_dir: str = "scripts", config_dir: str = "config"):
        super().__init__(scripts_dir, config_dir)
        self.previous_tasks: Set[str] = set()
        
    def discover_tasks_with_cleanup(self):
        """
        Discover tasks and perform cleanup of orphaned schedules.
        
        Returns:
            TaskRegistry with cleaned up schedules
        """
        # Store previous task list
        if hasattr(self, 'registry') and self.registry.list_tasks():
            self.previous_tasks = set(self.registry.list_tasks())
        
        # Perform normal discovery
        registry = self.discover_tasks()
        
        # Check for removed tasks and clean up orphaned schedules
        removed_tasks = self.detect_removed_tasks()
        if removed_tasks:
            self.cleanup_orphaned_schedules()
        
        # Validate task integrity
        validation_results = self.validate_task_integrity()
        if validation_results['invalid_tasks']:
            print(f"Warning: {len(validation_results['invalid_tasks'])} tasks have validation issues")
        
        return registry
    
    def detect_removed_tasks(self) -> List[str]:
        """
        Detect tasks that were previously discovered but no longer exist.
        
        Returns:
            List of removed task names
        """
        current_tasks = set(self.registry.list_tasks())
        removed_tasks = self.previous_tasks - current_tasks
        
        if removed_tasks:
            print(f"Detected {len(removed_tasks)} removed tasks:")
            for task_name in removed_tasks:
                print(f"  • {task_name}")
        
        return list(removed_tasks)
    
    def cleanup_orphaned_schedules(self) -> None:
        """
        Remove schedules for tasks that no longer exist.
        """
        if not self.schedules_file.exists():
            print(f"Schedules file {self.schedules_file} does not exist, skipping cleanup")
            return
        
        try:
            with open(self.schedules_file, 'r') as f:
                schedules = yaml.safe_load(f) or {}
            
            if 'schedules' not in schedules:
                schedules['schedules'] = {}
            
            current_tasks = set(self.registry.list_tasks())
            scheduled_tasks = set(schedules.get('schedules', {}).keys())
            orphaned_tasks = scheduled_tasks - current_tasks
            
            if orphaned_tasks:
                print(f"Cleaning up {len(orphaned_tasks)} orphaned schedules:")
                for task_name in orphaned_tasks:
                    print(f"  • Removing schedule for: {task_name}")
                    del schedules['schedules'][task_name]
                
                # Update schedules file
                self.update_container_schedules(schedules)
                
                # Save updated schedules
                self.config_dir.mkdir(parents=True, exist_ok=True)
                with open(self.schedules_file, 'w') as f:
                    yaml.safe_dump(schedules, f, default_flow_style=False, indent=2)
                
                print(f"Updated schedules configuration at {self.schedules_file}")
            else:
                print("No orphaned schedules found")
            
        except Exception as e:
            print(f"Error cleaning up orphaned schedules: {e}")
    
    def update_container_schedules(self, schedules: dict) -> None:
        """
        Update container schedules when tasks are removed.
        
        Args:
            schedules: Updated schedules configuration
        """
        try:
            # Signal scheduler to reload configuration
            scheduler_signal_file = "/tmp/automation_scheduler_reload"
            with open(scheduler_signal_file, 'w') as f:
                f.write(f"reload_requested_at:{datetime.now().isoformat()}\n")
                f.write(f"total_tasks:{len(self.registry.list_tasks())}\n")
                f.write(f"total_schedules:{len(schedules.get('schedules', {}))}\n")
            
            print("Signaled scheduler to reload configuration")
            
        except Exception as e:
            print(f"Warning: Could not signal scheduler reload: {e}")
    
    def validate_task_integrity(self) -> Dict[str, List[str]]:
        """
        Validate task dependencies and imports.
        
        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'valid_tasks': [],
            'invalid_tasks': [],
            'missing_dependencies': [],
            'import_errors': []
        }
        
        for task_name in self.registry.list_tasks():
            try:
                task_class = self.registry.get_task(task_name)
                metadata = self.registry.get_metadata(task_name)
                
                if not task_class or not metadata:
                    validation_results['invalid_tasks'].append(task_name)
                    validation_results['import_errors'].append(f"{task_name}: Missing class or metadata")
                    continue
                
                # Check dependencies
                dependencies = metadata.get('dependencies', [])
                missing_deps = []
                
                for dep in dependencies:
                    # Check if dependency credentials exist
                    if dep == 'IPAM':
                        cred_file = Path.home() / ".config" / "credential.ini"
                        if not cred_file.exists():
                            missing_deps.append(f"{dep} credentials not found at {cred_file}")
                    elif dep == 'HPE_OOB':
                        cred_file = Path.home() / ".config" / "credential.ini"
                        if not cred_file.exists():
                            missing_deps.append(f"{dep} credentials not found at {cred_file}")
                    # Add more dependency checks as needed
                
                if missing_deps:
                    validation_results['missing_dependencies'].extend(missing_deps)
                    validation_results['invalid_tasks'].append(task_name)
                else:
                    validation_results['valid_tasks'].append(task_name)
                    
            except Exception as e:
                validation_results['import_errors'].append(f"{task_name}: {str(e)}")
                validation_results['invalid_tasks'].append(task_name)
        
        # Print validation summary
        if validation_results['invalid_tasks']:
            print(f"\nTask Validation Summary:")
            print(f"  Valid tasks: {len(validation_results['valid_tasks'])}")
            print(f"  Invalid tasks: {len(validation_results['invalid_tasks'])}")
            if validation_results['missing_dependencies']:
                print(f"  Missing dependencies:")
                for dep in validation_results['missing_dependencies']:
                    print(f"    • {dep}")
            if validation_results['import_errors']:
                print(f"  Import errors:")
                for error in validation_results['import_errors']:
                    print(f"    • {error}")
        
        return validation_results
    
    def sync_schedules_with_discovered_tasks(self) -> None:
        """
        Ensure all discovered tasks have schedule entries (with defaults if needed).
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            if self.schedules_file.exists():
                with open(self.schedules_file, 'r') as f:
                    schedules = yaml.safe_load(f) or {}
            else:
                schedules = {}
            
            if 'schedules' not in schedules:
                schedules['schedules'] = {}
            
            # Add missing schedules for discovered tasks
            tasks_added = 0
            for task_name in self.registry.list_tasks():
                if task_name not in schedules['schedules']:
                    metadata = self.registry.get_metadata(task_name)
                    default_schedule = metadata.get('default_schedule')
                    
                    if default_schedule:
                        schedules['schedules'][task_name] = {
                            'cron': default_schedule,
                            'enabled': True,
                            'max_runtime': metadata.get('max_runtime', 3600),
                            'retry_count': metadata.get('retry_count', 1),
                            'description': metadata.get('description', ''),
                            'category': metadata.get('category', 'uncategorized')
                        }
                        tasks_added += 1
            
            # Save updated schedules if changes were made
            if tasks_added > 0:
                with open(self.schedules_file, 'w') as f:
                    yaml.safe_dump(schedules, f, default_flow_style=False, indent=2)
                print(f"Added schedules for {tasks_added} new tasks")
            
        except Exception as e:
            print(f"Error syncing schedules: {e}")


def enhanced_discovery_main():
    """Main function for enhanced task discovery with cleanup."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Automation Task Discovery')
    parser.add_argument('--cleanup', action='store_true', 
                       help='Perform full cleanup of orphaned schedules')
    parser.add_argument('--validate', action='store_true',
                       help='Validate task integrity and dependencies') 
    parser.add_argument('--sync-schedules', action='store_true',
                       help='Sync schedules with discovered tasks')
    parser.add_argument('--scripts-dir', default='scripts',
                       help='Scripts directory to scan (default: scripts)')
    parser.add_argument('--config-dir', default='config',
                       help='Configuration directory (default: config)')
    
    args = parser.parse_args()
    
    # Create enhanced discovery instance
    discovery = EnhancedTaskDiscovery(args.scripts_dir, args.config_dir)
    
    if args.cleanup:
        print("Performing enhanced task discovery with cleanup...")
        registry = discovery.discover_tasks_with_cleanup()
    else:
        print("Performing standard task discovery...")
        registry = discovery.discover_tasks()
    
    if args.validate:
        print("\nValidating task integrity...")
        validation_results = discovery.validate_task_integrity()
        print(f"Validation complete: {len(validation_results['valid_tasks'])} valid, "
              f"{len(validation_results['invalid_tasks'])} invalid tasks")
    
    if args.sync_schedules:
        print("\nSyncing schedules with discovered tasks...")
        discovery.sync_schedules_with_discovered_tasks()
    
    print(f"\nDiscovery complete: {len(registry.list_tasks())} tasks registered")


if __name__ == '__main__':
    enhanced_discovery_main()