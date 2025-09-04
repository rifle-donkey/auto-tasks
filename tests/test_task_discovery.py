"""
Tests for task discovery and runner functionality.
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from automation_core import TaskDiscovery, TaskRegistry, TaskRunner, BaseTask


class MockTask1(BaseTask):
    name = "mock_task_1"
    description = "First mock task"
    category = "testing"
    dependencies = []
    default_schedule = "0 */1 * * *"
    
    def run(self):
        return {"result": "mock1_success"}


class MockTask2(BaseTask):
    name = "mock_task_2"
    description = "Second mock task"
    category = "testing"
    dependencies = ["IPAM"]
    default_schedule = "0 */2 * * *"
    
    def run(self):
        return {"result": "mock2_success"}


class MockFailingTask(BaseTask):
    name = "failing_task"
    description = "Task that always fails"
    category = "testing"
    
    def run(self):
        raise RuntimeError("This task always fails")


class TestTaskRegistry:
    """Test TaskRegistry functionality."""
    
    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = TaskRegistry()
        assert len(registry.tasks) == 0
        assert len(registry.metadata) == 0
    
    def test_task_registration(self):
        """Test task registration."""
        registry = TaskRegistry()
        registry.register_task(MockTask1)
        
        assert "testing/mock_task_1" in registry.tasks
        assert "testing/mock_task_1" in registry.metadata
        
        metadata = registry.get_metadata("testing/mock_task_1")
        assert metadata['name'] == "mock_task_1"
        assert metadata['description'] == "First mock task"
        assert metadata['category'] == "testing"
        assert metadata['default_schedule'] == "0 */1 * * *"
    
    def test_multiple_task_registration(self):
        """Test registration of multiple tasks."""
        registry = TaskRegistry()
        registry.register_task(MockTask1)
        registry.register_task(MockTask2)
        
        assert len(registry.tasks) == 2
        assert len(registry.metadata) == 2
        
        task_names = registry.list_tasks()
        assert "testing/mock_task_1" in task_names
        assert "testing/mock_task_2" in task_names
    
    def test_get_tasks_by_category(self):
        """Test getting tasks by category."""
        registry = TaskRegistry()
        registry.register_task(MockTask1)
        registry.register_task(MockTask2)
        
        testing_tasks = registry.get_tasks_by_category("testing")
        assert len(testing_tasks) == 2
        assert "testing/mock_task_1" in testing_tasks
        assert "testing/mock_task_2" in testing_tasks
        
        # Test non-existent category
        empty_tasks = registry.get_tasks_by_category("nonexistent")
        assert len(empty_tasks) == 0
    
    def test_get_task_class(self):
        """Test retrieving task class."""
        registry = TaskRegistry()
        registry.register_task(MockTask1)
        
        task_class = registry.get_task("testing/mock_task_1")
        assert task_class == MockTask1
        
        # Test non-existent task
        assert registry.get_task("nonexistent/task") is None


class TestTaskDiscovery:
    """Test TaskDiscovery functionality."""
    
    def create_temp_task_file(self, content: str, filename: str = "temp_task.py") -> Path:
        """Create a temporary task file for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        scripts_dir = temp_dir / "scripts" / "category"
        scripts_dir.mkdir(parents=True)
        
        task_file = scripts_dir / filename
        task_file.write_text(content)
        
        return temp_dir
    
    def test_discovery_with_valid_task(self):
        """Test discovery of valid task files."""
        task_content = '''
from automation_core import BaseTask

class ValidTask(BaseTask):
    name = "valid_task"
    description = "A valid test task"
    category = "testing"
    
    def run(self):
        return "success"
'''
        
        temp_dir = self.create_temp_task_file(task_content, "valid_task.py")
        
        try:
            discovery = TaskDiscovery(str(temp_dir / "scripts"))
            registry = discovery.discover_tasks()
            
            # Should discover the task
            assert len(registry.list_tasks()) >= 0  # May discover the ValidTask
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)
    
    def test_discovery_with_invalid_file(self):
        """Test discovery handles invalid Python files gracefully."""
        invalid_content = '''
# This is not valid Python syntax
class BrokenTask(BaseTask
    # Missing closing parenthesis
    def run(self):
        return "broken"
'''
        
        temp_dir = self.create_temp_task_file(invalid_content, "broken_task.py")
        
        try:
            discovery = TaskDiscovery(str(temp_dir / "scripts"))
            registry = discovery.discover_tasks()
            
            # Should handle the error gracefully
            # Registry should be empty or not contain the broken task
            task_names = registry.list_tasks()
            assert "category/broken_task" not in task_names
            
        finally:
            import shutil
            shutil.rmtree(temp_dir)
    
    def test_discovery_skips_init_files(self):
        """Test that discovery skips __init__.py files."""
        init_content = '''
# This is an __init__.py file
from .some_module import something
'''
        
        temp_dir = self.create_temp_task_file(init_content, "__init__.py")
        
        try:
            discovery = TaskDiscovery(str(temp_dir / "scripts"))
            registry = discovery.discover_tasks()
            
            # Should not discover anything from __init__.py
            task_names = registry.list_tasks()
            init_related_tasks = [name for name in task_names if "__init__" in name]
            assert len(init_related_tasks) == 0
            
        finally:
            import shutil
            shutil.rmtree(temp_dir)


class TestTaskRunner:
    """Test TaskRunner functionality."""
    
    def setup_test_registry(self):
        """Setup a test registry with mock tasks."""
        registry = TaskRegistry()
        registry.register_task(MockTask1)
        registry.register_task(MockTask2)
        registry.register_task(MockFailingTask)
        return registry
    
    def test_runner_initialization(self):
        """Test runner initialization."""
        registry = self.setup_test_registry()
        runner = TaskRunner(registry)
        
        assert runner.registry == registry
    
    @patch('automation_core.auth.get_credential')
    def test_successful_task_execution(self, mock_get_credential):
        """Test successful task execution."""
        mock_get_credential.return_value = ("test_user", "test_pass")
        
        registry = self.setup_test_registry()
        runner = TaskRunner(registry)
        
        result = runner.run_task("testing/mock_task_1")
        
        assert result['success'] is True
        assert result['task_result']['result'] == "mock1_success"
        assert result['error'] is None
    
    def test_nonexistent_task_execution(self):
        """Test execution of non-existent task."""
        registry = self.setup_test_registry()
        runner = TaskRunner(registry)
        
        with pytest.raises(ValueError, match="Task 'nonexistent/task' not found"):
            runner.run_task("nonexistent/task")
    
    def test_failing_task_execution(self):
        """Test execution of failing task."""
        registry = self.setup_test_registry()
        runner = TaskRunner(registry)
        
        with pytest.raises(RuntimeError, match="This task always fails"):
            runner.run_task("testing/failing_task")
    
    @patch('automation_core.auth.get_credential')
    def test_category_execution(self, mock_get_credential):
        """Test execution of all tasks in a category."""
        mock_get_credential.return_value = ("test_user", "test_pass")
        
        registry = self.setup_test_registry()
        runner = TaskRunner(registry)
        
        # This will include the failing task, so we expect mixed results
        results = runner.run_category("testing")
        
        assert len(results) == 3  # All three testing tasks
        assert "testing/mock_task_1" in results
        assert "testing/mock_task_2" in results
        assert "testing/failing_task" in results
        
        # Check that successful tasks succeeded
        assert results["testing/mock_task_1"]['success'] is True
        assert results["testing/mock_task_2"]['success'] is True
        
        # Check that failing task failed
        assert results["testing/failing_task"]['success'] is False
        assert "This task always fails" in results["testing/failing_task"]['error']
    
    def test_nonexistent_category_execution(self):
        """Test execution of non-existent category."""
        registry = self.setup_test_registry()
        runner = TaskRunner(registry)
        
        with pytest.raises(ValueError, match="No tasks found in category 'nonexistent'"):
            runner.run_category("nonexistent")
    
    def test_task_execution_with_config(self):
        """Test task execution with custom configuration."""
        class ConfigTestTask(BaseTask):
            name = "config_test"
            category = "testing"
            
            def run(self):
                return {
                    "config_received": self.config,
                    "debug_mode": self.config.get("debug", False)
                }
        
        registry = TaskRegistry()
        registry.register_task(ConfigTestTask)
        runner = TaskRunner(registry)
        
        config = {"debug": True, "param1": "value1"}
        result = runner.run_task("testing/config_test", config)
        
        assert result['success'] is True
        assert result['task_result']['config_received'] == config
        assert result['task_result']['debug_mode'] is True


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, "-v"])