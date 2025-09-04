"""
Reporting utilities module.
Provides standardized logging, CSV, and Splunk output functionality.
"""
import csv
import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union


class ReportingUtilities:
    """Utilities for generating reports and logging output."""
    
    def __init__(self, output_dir: str = "/var/automation_file", debug: bool = False):
        """
        Initialize reporting utilities.
        
        Args:
            output_dir: Base directory for output files
            debug: Enable debug logging
        """
        self.output_dir = Path(output_dir)
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        
        if debug:
            self.logger.setLevel(logging.DEBUG)
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def write_to_log(self, content: Union[str, List[str]], log_file: str, 
                    category: str = "general") -> None:
        """
        Write content to log file.
        
        Args:
            content: String or list of strings to write
            log_file: Log file name
            category: Category subdirectory
        """
        category_dir = self.output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        log_path = category_dir / log_file
        
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                if isinstance(content, list):
                    for line in content:
                        f.write(f"{line}\n")
                else:
                    f.write(f"{content}\n")
            
            # Set file permissions
            os.chmod(log_path, 0o644)
            
            self.logger.debug(f"Written to log file: {log_path}")
            
        except Exception as e:
            self.logger.error(f"Error writing to log file {log_path}: {e}")
    
    def write_to_csv(self, data: List[Dict[str, Any]], csv_file: str, 
                    category: str = "general", fieldnames: Optional[List[str]] = None) -> None:
        """
        Write data to CSV file.
        
        Args:
            data: List of dictionaries to write as CSV rows
            csv_file: CSV file name
            category: Category subdirectory
            fieldnames: Optional list of field names (uses keys from first row if not provided)
        """
        if not data:
            self.logger.warning(f"No data to write to CSV file: {csv_file}")
            return
        
        category_dir = self.output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        csv_path = category_dir / csv_file
        
        try:
            # Determine fieldnames
            if not fieldnames:
                fieldnames = list(data[0].keys())
            
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            
            # Set file permissions
            os.chmod(csv_path, 0o644)
            
            self.logger.info(f"Written {len(data)} rows to CSV: {csv_path}")
            
        except Exception as e:
            self.logger.error(f"Error writing CSV file {csv_path}: {e}")
    
    def write_to_json(self, data: Union[Dict, List], json_file: str, 
                     category: str = "general", pretty: bool = True) -> None:
        """
        Write data to JSON file.
        
        Args:
            data: Data to write as JSON
            json_file: JSON file name
            category: Category subdirectory
            pretty: Whether to format JSON nicely
        """
        category_dir = self.output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        json_path = category_dir / json_file
        
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                if pretty:
                    json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
                else:
                    json.dump(data, f, ensure_ascii=False)
            
            # Set file permissions
            os.chmod(json_path, 0o644)
            
            self.logger.info(f"Written JSON data to: {json_path}")
            
        except Exception as e:
            self.logger.error(f"Error writing JSON file {json_path}: {e}")
    
    def write_to_splunk(self, data: List[Dict[str, Any]], splunk_file: str, 
                       category: str = "general", script_name: Optional[str] = None) -> None:
        """
        Write data in Splunk key-value format.
        
        Args:
            data: List of dictionaries to write in Splunk format
            splunk_file: Splunk log file name
            category: Category subdirectory
            script_name: Script name to add to each log entry
        """
        if not data:
            self.logger.warning(f"No data to write to Splunk file: {splunk_file}")
            return
        
        category_dir = self.output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        splunk_path = category_dir / splunk_file
        
        try:
            with open(splunk_path, 'w', encoding='utf-8') as f:
                for item in data:
                    # Add script name if provided
                    if script_name:
                        item = item.copy()  # Don't modify original
                        item["Script"] = script_name
                    
                    # Add timestamp if not present
                    if "timestamp" not in item:
                        item["timestamp"] = datetime.now().isoformat()
                    
                    # Format as key="value" pairs
                    line_parts = []
                    for key, value in item.items():
                        # Escape quotes in values
                        escaped_value = str(value).replace('"', '\\"')
                        line_parts.append(f'{key}="{escaped_value}"')
                    
                    f.write(" ".join(line_parts) + "\n")
            
            # Set file permissions
            os.chmod(splunk_path, 0o644)
            
            self.logger.info(f"Written {len(data)} entries to Splunk format: {splunk_path}")
            
        except Exception as e:
            self.logger.error(f"Error writing Splunk file {splunk_path}: {e}")
    
    def archive_file(self, file_path: str, archive_name: Optional[str] = None, 
                    category: str = "general") -> Optional[str]:
        """
        Archive a file using ZIP compression.
        
        Args:
            file_path: Path to file to archive
            archive_name: Name for archive file (auto-generated if not provided)
            category: Category subdirectory
            
        Returns:
            Path to created archive file, or None if failed
        """
        source_path = Path(file_path)
        
        if not source_path.exists():
            self.logger.warning(f"File to archive does not exist: {file_path}")
            return None
        
        # Generate archive name if not provided
        if not archive_name:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            archive_name = f"{source_path.stem}_{timestamp}.zip"
        
        # Create archive in category subdirectory
        category_dir = self.output_dir / category / "archive"
        category_dir.mkdir(parents=True, exist_ok=True)
        
        archive_path = category_dir / archive_name
        
        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(source_path, source_path.name)
            
            # Set file permissions
            os.chmod(archive_path, 0o644)
            
            self.logger.info(f"Archived {file_path} to {archive_path}")
            
            return str(archive_path)
            
        except Exception as e:
            self.logger.error(f"Error archiving file {file_path}: {e}")
            return None
    
    def create_execution_report(self, task_name: str, execution_results: Dict[str, Any], 
                              category: str = "reports") -> str:
        """
        Create a standardized execution report.
        
        Args:
            task_name: Name of the executed task
            execution_results: Results from task execution
            category: Category subdirectory
            
        Returns:
            Path to created report file
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = f"{task_name.replace('/', '_')}_{timestamp}_report.json"
        
        report_data = {
            "task_name": task_name,
            "execution_timestamp": timestamp,
            "report_generated": datetime.now().isoformat(),
            "execution_results": execution_results,
            "summary": {
                "success": execution_results.get("success", False),
                "runtime_seconds": execution_results.get("runtime_seconds", 0),
                "error": execution_results.get("error")
            }
        }
        
        category_dir = self.output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        report_path = category_dir / report_file
        
        self.write_to_json(report_data, report_file, category)
        
        return str(report_path)
    
    def create_monitoring_dashboard_data(self, monitoring_results: Dict[str, Any], 
                                       category: str = "monitoring") -> str:
        """
        Create dashboard-ready data from monitoring results.
        
        Args:
            monitoring_results: Results from monitoring tasks
            category: Category subdirectory
            
        Returns:
            Path to dashboard data file
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dashboard_file = f"monitoring_dashboard_{timestamp}.json"
        
        # Transform monitoring results into dashboard format
        dashboard_data = {
            "last_updated": datetime.now().isoformat(),
            "dashboard_type": "monitoring_summary",
            "data": monitoring_results,
            "widgets": []
        }
        
        # Add health summary widgets
        if "summary" in monitoring_results:
            summary = monitoring_results["summary"]
            dashboard_data["widgets"].append({
                "type": "health_summary",
                "title": "System Health Overview",
                "data": {
                    "healthy_percentage": summary.get("health_percentage", 0),
                    "total_checked": summary.get("total_checked", 0),
                    "healthy_count": summary.get("reachable_count", 0),
                    "unhealthy_count": summary.get("unreachable_count", 0)
                }
            })
        
        # Add performance widgets if available
        if "performance_metrics" in monitoring_results:
            dashboard_data["widgets"].append({
                "type": "performance_chart",
                "title": "Performance Metrics",
                "data": monitoring_results["performance_metrics"]
            })
        
        self.write_to_json(dashboard_data, dashboard_file, category)
        
        return str(self.output_dir / category / dashboard_file)
    
    def cleanup_old_files(self, category: str, days_to_keep: int = 30, 
                         file_pattern: str = "*") -> int:
        """
        Clean up old files in a category directory.
        
        Args:
            category: Category subdirectory to clean
            days_to_keep: Number of days of files to keep
            file_pattern: File pattern to match for cleanup
            
        Returns:
            Number of files cleaned up
        """
        category_dir = self.output_dir / category
        
        if not category_dir.exists():
            return 0
        
        cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 3600)
        cleaned_count = 0
        
        try:
            for file_path in category_dir.glob(file_pattern):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    cleaned_count += 1
                    self.logger.debug(f"Cleaned up old file: {file_path}")
            
            self.logger.info(f"Cleaned up {cleaned_count} files from {category}")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup of {category}: {e}")
        
        return cleaned_count
    
    def get_file_path(self, filename: str, category: str = "general") -> str:
        """
        Get full path for a file in the specified category.
        
        Args:
            filename: Name of the file
            category: Category subdirectory
            
        Returns:
            Full path to the file
        """
        category_dir = self.output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        return str(category_dir / filename)