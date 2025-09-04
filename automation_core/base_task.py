"""
Base class for all automation tasks in the framework.
Provides common functionality and standardized interface for task execution.
"""
import abc
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

from .auth import get_credential
from .utils import set_timestamp


class BaseTask(abc.ABC):
    """
    Base class for all automation tasks.
    
    All task scripts must inherit from this class and implement the run() method.
    Provides standard logging, credential management, and execution tracking.
    """
    
    # Task metadata - to be set by subclasses
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    dependencies: List[str] = []
    default_schedule: Optional[str] = None
    max_runtime: int = 3600  # Default 1 hour timeout
    retry_count: int = 1
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize base task.
        
        Args:
            config: Optional configuration dictionary for the task
        """
        self.config = config or {}
        self.start_time = None
        self.end_time = None
        self.logger = self._setup_logging()
        self.results = {}
        
        # Auto-derive name and category if not set
        if not self.name:
            self.name = self.__class__.__module__.split('.')[-1]
        if not self.category:
            module_path = self.__class__.__module__
            if 'scripts.' in module_path:
                parts = module_path.split('scripts.')[1].split('.')
                if len(parts) > 1:
                    self.category = parts[0]
    
    def _setup_logging(self) -> logging.Logger:
        """Setup task-specific logger."""
        logger_name = f"task.{self.name or self.__class__.__name__}"
        logger = logging.getLogger(logger_name)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        return logger
    
    def get_credential(self, section: str) -> tuple:
        """
        Get encrypted credentials for specified section.
        
        Args:
            section: Credential section name (IPAM, HPE_OOB, etc.)
            
        Returns:
            Tuple of (username, password) 
        """
        return get_credential(section)
    
    def log(self, message: str, level: str = "info") -> None:
        """
        Log message with task context.
        
        Args:
            message: Message to log
            level: Log level (debug, info, warning, error, critical)
        """
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(f"[{self.name}] {message}")
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute the task with timing and error handling.
        
        Returns:
            Dictionary containing execution results and metadata
        """
        self.start_time = datetime.now()
        self.log(f"Starting task execution at {self.start_time}")
        
        try:
            # Validate dependencies before execution
            self._validate_dependencies()
            
            # Run the actual task
            task_result = self.run()
            
            self.end_time = datetime.now()
            runtime = (self.end_time - self.start_time).total_seconds()
            
            self.results = {
                'success': True,
                'start_time': self.start_time.isoformat(),
                'end_time': self.end_time.isoformat(),
                'runtime_seconds': runtime,
                'task_result': task_result,
                'error': None
            }
            
            self.log(f"Task completed successfully in {runtime:.2f} seconds")
            
        except Exception as e:
            self.end_time = datetime.now()
            runtime = (self.end_time - self.start_time).total_seconds() if self.start_time else 0
            
            self.results = {
                'success': False,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat(),
                'runtime_seconds': runtime,
                'task_result': None,
                'error': str(e)
            }
            
            self.log(f"Task failed after {runtime:.2f} seconds: {e}", "error")
            raise
        
        return self.results
    
    def _validate_dependencies(self) -> None:
        """Validate that all required dependencies are available."""
        for dependency in self.dependencies:
            if dependency in ["IPAM", "HPE_OOB"]:
                try:
                    self.get_credential(dependency)
                    self.log(f"Validated credential dependency: {dependency}")
                except Exception as e:
                    raise RuntimeError(f"Failed to validate credential dependency {dependency}: {e}")
            else:
                # For other dependencies, just log them for now
                self.log(f"Noted dependency: {dependency}")
    
    @abc.abstractmethod
    def run(self) -> Any:
        """
        Main task execution logic.
        
        This method must be implemented by all task subclasses.
        Should return any results from the task execution.
        """
        raise NotImplementedError("Task subclasses must implement the run() method")
    
    def get_output_file(self, filename: str, create_dirs: bool = True) -> str:
        """
        Get standardized output file path for the task.
        
        Args:
            filename: Base filename
            create_dirs: Whether to create directories if they don't exist
            
        Returns:
            Full path to output file
        """
        timestamp = set_timestamp()
        output_dir = f"/var/automation_file/{self.category or 'general'}"
        
        if create_dirs and not os.path.exists(output_dir):
            os.makedirs(output_dir, mode=0o755, exist_ok=True)
        
        return os.path.join(output_dir, f"{timestamp}_{filename}")
    
    def __str__(self) -> str:
        """String representation of the task."""
        return f"{self.__class__.__name__}(name='{self.name}', category='{self.category}')"
    
    def __repr__(self) -> str:
        """Developer representation of the task."""
        return (f"{self.__class__.__name__}(name='{self.name}', "
                f"category='{self.category}', description='{self.description}')")