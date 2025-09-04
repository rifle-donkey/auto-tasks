"""
Git operations module.
Provides standardized Git repository management functionality.
"""
import git
import hashlib
import logging
import os
import secrets
from typing import Dict, List, Any, Optional


class GitOperations:
    """Handles Git repository operations for automation tasks."""
    
    def __init__(self, repo_path: str):
        """
        Initialize Git operations for a repository.
        
        Args:
            repo_path: Path to Git repository
        """
        self.repo_path = repo_path
        self.logger = logging.getLogger(__name__)
        
        try:
            self.repo = git.Repo(repo_path)
        except git.exc.InvalidGitRepositoryError:
            self.logger.error(f"Invalid Git repository: {repo_path}")
            raise
    
    def pull_latest(self, result_dict: Optional[Dict[str, List[str]]] = None) -> str:
        """
        Pull latest changes from remote repository.
        
        Args:
            result_dict: Optional dict to append messages to
            
        Returns:
            Pull result message
        """
        try:
            msg = "Pulling latest changes from Git repository..."
            self.logger.info(msg)
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(msg)
            
            git_cmd = git.cmd.Git(self.repo_path)
            pull_result = git_cmd.pull()
            
            self.logger.info(f"Git pull result: {pull_result}")
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(pull_result)
            
            return pull_result
            
        except Exception as e:
            error_msg = f"Git pull failed: {str(e)}"
            self.logger.error(error_msg)
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(error_msg)
            
            raise
    
    def get_latest_commit_hash(self) -> str:
        """Get the latest commit hash."""
        return self.repo.head.commit.hexsha
    
    def get_commit_message(self) -> str:
        """Get the latest commit message."""
        return self.repo.head.commit.message.strip()
    
    def has_changes(self) -> bool:
        """Check if repository has uncommitted changes."""
        return self.repo.is_dirty()
    
    def get_branch_name(self) -> str:
        """Get current branch name."""
        return self.repo.active_branch.name
    
    def list_files_in_directory(self, directory: str, pattern: str = "*.csv", 
                               result_dict: Optional[Dict[str, List[str]]] = None) -> List[str]:
        """
        List files in repository directory matching pattern.
        
        Args:
            directory: Directory path within repository
            pattern: File pattern to match
            result_dict: Optional dict to append messages and results to
            
        Returns:
            List of matching filenames
        """
        import re
        
        full_dir_path = os.path.join(self.repo_path, directory)
        
        if not os.path.exists(full_dir_path):
            msg = f"Directory {directory} does not exist in repository"
            self.logger.warning(msg)
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(msg)
            
            return []
        
        msg = f"Listing files in {directory}..."
        self.logger.info(msg)
        
        if result_dict and 'messages' in result_dict:
            result_dict['messages'].append(msg)
        
        matching_files = []
        
        # Convert glob pattern to regex
        regex_pattern = pattern.replace('*', '.*').replace('?', '.')
        compiled_pattern = re.compile(regex_pattern)
        
        try:
            with os.scandir(full_dir_path) as entries:
                for entry in entries:
                    if entry.is_file() and compiled_pattern.match(entry.name):
                        matching_files.append(entry.name)
                        self.logger.debug(f"Found matching file: {entry.name}")
        
        except Exception as e:
            error_msg = f"Error scanning directory {directory}: {str(e)}"
            self.logger.error(error_msg)
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(error_msg)
        
        if result_dict and 'seed_file_list' in result_dict:
            result_dict['seed_file_list'].extend(matching_files)
        
        self.logger.info(f"Found {len(matching_files)} matching files")
        
        return matching_files
    
    def verify_file_change(self, file_path: str, hash_file: str, 
                          result_dict: Optional[Dict[str, List[str]]] = None) -> str:
        """
        Verify if a file has changed by comparing MD5 hashes.
        
        Args:
            file_path: Path to file to check
            hash_file: Path to file storing previous hash
            result_dict: Optional dict to append messages to
            
        Returns:
            "Changed" if file changed, "Unchanged" if not
        """
        full_file_path = os.path.join(self.repo_path, file_path)
        
        if not os.path.exists(full_file_path):
            msg = f"File {file_path} does not exist"
            self.logger.error(msg)
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(msg)
            
            return "Error"
        
        # Generate new hash
        try:
            with open(full_file_path, 'rb') as f:
                content = f.read()
            new_hash = hashlib.md5(content).hexdigest()
            
        except Exception as e:
            msg = f"Error reading file {file_path}: {str(e)}"
            self.logger.error(msg)
            
            if result_dict and 'messages' in result_dict:
                result_dict['messages'].append(msg)
            
            return "Error"
        
        # Read previous hash
        previous_hash = ""
        if os.path.exists(hash_file):
            try:
                with open(hash_file, 'r') as f:
                    previous_hash = f.read().strip()
            except Exception as e:
                self.logger.warning(f"Error reading hash file {hash_file}: {str(e)}")
        
        # Compare hashes
        if secrets.compare_digest(new_hash, previous_hash):
            status = "Unchanged"
            msg = f"No change found in {file_path}"
        else:
            status = "Changed" 
            msg = f"Found change in {file_path}"
        
        self.logger.info(msg)
        
        if result_dict and 'messages' in result_dict:
            result_dict['messages'].append(msg)
        
        # Update hash file
        try:
            os.makedirs(os.path.dirname(hash_file), exist_ok=True)
            with open(hash_file, 'w') as f:
                f.write(new_hash)
        except Exception as e:
            self.logger.error(f"Error writing hash file {hash_file}: {str(e)}")
        
        return status
    
    def get_file_path(self, relative_path: str) -> str:
        """
        Get full path to file in repository.
        
        Args:
            relative_path: Relative path within repository
            
        Returns:
            Full absolute path to file
        """
        return os.path.join(self.repo_path, relative_path)