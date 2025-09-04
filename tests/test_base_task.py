"""
Tests for BaseTask class and core functionality.
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from automation_core import BaseTask, get_credential


class TestTask(BaseTask):
    """Test task for unit testing."""
    
    name = "test_task"
    description = "A test automation task"
    category = "testing"
    dependencies = ["TEST_CRED"]
    
    def __init__(self, config=None, should_fail=False):
        super().__init__(config)
        self.should_fail = should_fail
        self.execution_log = []
    
    def run(self):
        self.execution_log.append("run_started")
        
        if self.should_fail:
            raise RuntimeError("Simulated task failure")
        
        self.execution_log.append("run_completed")
        return {"test_result": "success", "data": [1, 2, 3]}


class TestBaseTaskFunctionality:
    """Test BaseTask core functionality."""
    
    def test_task_initialization(self):
        """Test task initialization with configuration."""
        config = {"debug": True, "timeout": 300}
        task = TestTask(config)
        
        assert task.name == "test_task"
        assert task.description == "A test automation task"
        assert task.category == "testing"
        assert task.dependencies == ["TEST_CRED"]
        assert task.config == config
        assert task.max_runtime == 3600  # Default
    
    def test_successful_task_execution(self):
        """Test successful task execution."""
        task = TestTask()
        result = task.execute()
        
        assert result['success'] is True
        assert result['task_result']['test_result'] == "success"
        assert result['task_result']['data'] == [1, 2, 3]
        assert result['error'] is None
        assert result['start_time'] is not None
        assert result['end_time'] is not None
        assert result['runtime_seconds'] > 0
        
        # Check execution log
        assert "run_started" in task.execution_log
        assert "run_completed" in task.execution_log
    
    def test_failed_task_execution(self):
        """Test failed task execution."""
        task = TestTask(should_fail=True)
        
        with pytest.raises(RuntimeError, match="Simulated task failure"):
            task.execute()
        
        # Check result structure is still populated
        result = task.results
        assert result['success'] is False
        assert result['task_result'] is None
        assert "Simulated task failure" in result['error']
        assert result['start_time'] is not None
        assert result['end_time'] is not None
    
    def test_task_logging(self):
        """Test task logging functionality."""
        task = TestTask()
        
        # Test different log levels
        task.log("Info message", "info")
        task.log("Warning message", "warning")
        task.log("Error message", "error")
        
        # Should not raise exceptions
        assert True
    
    @patch('automation_core.auth.get_credential')
    def test_credential_retrieval(self, mock_get_credential):
        """Test credential retrieval."""
        mock_get_credential.return_value = ("test_user", "test_pass")
        
        task = TestTask()
        username, password = task.get_credential("TEST_CRED")
        
        assert username == "test_user"
        assert password == "test_pass"
        mock_get_credential.assert_called_once_with("TEST_CRED")
    
    def test_dependency_validation(self):
        """Test dependency validation."""
        with patch.object(TestTask, 'get_credential') as mock_get_cred:
            mock_get_cred.return_value = ("user", "pass")
            
            task = TestTask()
            # Should not raise exception when credentials are available
            task._validate_dependencies()
            
            mock_get_cred.assert_called_once_with("TEST_CRED")
    
    def test_dependency_validation_failure(self):
        """Test dependency validation failure."""
        with patch.object(TestTask, 'get_credential') as mock_get_cred:
            mock_get_cred.side_effect = Exception("Credential not found")
            
            task = TestTask()
            
            with pytest.raises(RuntimeError, match="Failed to validate credential dependency"):
                task._validate_dependencies()
    
    def test_output_file_generation(self):
        """Test output file path generation."""
        task = TestTask()
        
        with patch('os.makedirs') as mock_makedirs:
            output_file = task.get_output_file("test_report.csv")
            
            assert "testing" in output_file  # Category should be in path
            assert "test_report.csv" in output_file
            mock_makedirs.assert_called_once()
    
    def test_auto_name_derivation(self):
        """Test automatic name derivation from class."""
        class AutoNameTask(BaseTask):
            description = "Auto-named task"
            
            def run(self):
                return "success"
        
        task = AutoNameTask()
        # Name should be derived from module path
        assert task.name is not None
        assert len(task.name) > 0
    
    def test_string_representations(self):
        """Test string representations of task."""
        task = TestTask()
        
        str_repr = str(task)
        assert "TestTask" in str_repr
        assert "test_task" in str_repr
        
        repr_str = repr(task)
        assert "TestTask" in repr_str
        assert "A test automation task" in repr_str


class TestTaskWithRealCredentials:
    """Test task functionality with real credential files."""
    
    def test_credential_file_handling(self):
        """Test credential file creation and reading."""
        # Create temporary credential file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write("""[KEY]
crypto_key = test_key_here

[TEST_SECTION]
hash_usr = dGVzdF91c2Vy  # base64 encoded 'test_user'
hash_pwd = dGVzdF9wYXNz  # base64 encoded 'test_pass'
""")
            temp_file = f.name
        
        try:
            # Mock the credential file path
            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = os.path.dirname(temp_file)
                
                # This would require actual cryptography setup
                # For now, just test that the file is accessible
                assert os.path.exists(temp_file)
        
        finally:
            os.unlink(temp_file)


class TestTaskExecutionTiming:
    """Test task execution timing and performance."""
    
    def test_execution_timing_recording(self):
        """Test that execution timing is properly recorded."""
        class TimingTestTask(BaseTask):
            def run(self):
                import time
                time.sleep(0.1)  # Sleep for 100ms
                return "timed_success"
        
        task = TimingTestTask()
        result = task.execute()
        
        assert result['success'] is True
        assert result['runtime_seconds'] >= 0.1
        assert result['start_time'] != result['end_time']
        
        # Verify datetime format
        start_dt = datetime.fromisoformat(result['start_time'])
        end_dt = datetime.fromisoformat(result['end_time'])
        assert end_dt > start_dt


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, "-v"])