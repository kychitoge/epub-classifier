"""
Checkpoint System for Resume Capability
Saves progress after each file, allows resuming from last checkpoint.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime
import logging

from utils.error_handler import SystemError

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoint file for resume capability"""
    
    def __init__(self, checkpoint_path: str = "processed_log.json"):
        self.checkpoint_path = Path(checkpoint_path)
        self._processed_files: Set[str] = set()
        self._corrupted_files: Set[str] = set()
        self._load_checkpoint()
    
    def _load_checkpoint(self) -> None:
        """Load checkpoint file if exists"""
        if not self.checkpoint_path.exists():
            logger.info(f"No checkpoint found at {self.checkpoint_path}, starting fresh")
            return
        
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract processed file keys
            if isinstance(data, dict):
                # Old format: {filename: {...}}
                self._processed_files = set(data.keys())
                # Extract corrupted files
                self._corrupted_files = {
                    k for k, v in data.items() 
                    if isinstance(v, dict) and v.get('status') == 'corrupted'
                }
            elif isinstance(data, list):
                # New format: [{filename: ..., status: ...}, ...]
                self._processed_files = {item.get('filename', '') for item in data if item.get('status') == 'ok'}
                self._corrupted_files = {item.get('filename', '') for item in data if item.get('status') == 'corrupted'}
            
            logger.info(f"Loaded checkpoint: {len(self._processed_files)} processed files, {len(self._corrupted_files)} corrupted files")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}, starting fresh")
            self._processed_files = set()
            self._corrupted_files = set()
    
    def is_processed(self, file_key: str) -> bool:
        """
        Check if file has been processed.
        
        Args:
            file_key: Unique identifier (usually filename or hash)
        
        Returns:
            True if file was successfully processed
        """
        return file_key in self._processed_files
    
    def mark_processed(self, file_key: str, metadata: Optional[Dict] = None) -> None:
        """
        Mark file as processed and save checkpoint.
        
        Args:
            file_key: Unique identifier
            metadata: Optional metadata to store
        """
        self._processed_files.add(file_key)
        self._save_checkpoint(file_key, metadata)
    
    def _save_checkpoint(self, file_key: str, metadata: Optional[Dict] = None) -> None:
        """Save checkpoint to file (atomic write)"""
        try:
            # Load existing data
            existing_data = {}
            if self.checkpoint_path.exists():
                try:
                    with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except:
                    existing_data = {}
            
            # Update with new entry
            if not isinstance(existing_data, dict):
                existing_data = {}
            
            entry = {
                "status": "ok",
                "processed_at": str(Path(file_key).stat().st_mtime) if os.path.exists(file_key) else None
            }
            if metadata:
                entry.update(metadata)
            
            existing_data[file_key] = entry
            
            # Atomic write
            temp_path = self.checkpoint_path.with_suffix(self.checkpoint_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            # Atomic replace
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
            temp_path.rename(self.checkpoint_path)
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            # Don't raise - checkpoint failure shouldn't stop processing
    
    def clear_checkpoint(self) -> None:
        """Clear checkpoint file (for testing or full re-run)"""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
        self._processed_files.clear()
        logger.info("Checkpoint cleared")
    
    def get_processed_count(self) -> int:
        """Get number of processed files"""
        return len(self._processed_files)
    
    def mark_corrupted(self, file_key: str) -> None:
        """
        Mark file as corrupted and save checkpoint.
        
        Args:
            file_key: Unique identifier (usually filename)
        """
        self._corrupted_files.add(file_key)
        self._save_corrupted_checkpoint(file_key)
    
    def get_corrupted_files(self) -> Set[str]:
        """Get set of corrupted file keys"""
        return self._corrupted_files.copy()
    
    def _save_corrupted_checkpoint(self, file_key: str) -> None:
        """Save corrupted file to checkpoint (atomic write)"""
        try:
            # Load existing data
            existing_data = {}
            if self.checkpoint_path.exists():
                try:
                    with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except:
                    existing_data = {}
            
            # Update with new entry
            if not isinstance(existing_data, dict):
                existing_data = {}
            
            entry = {
                "status": "corrupted",
                "marked_at": datetime.now().isoformat()
            }
            
            existing_data[file_key] = entry
            
            # Atomic write
            temp_path = self.checkpoint_path.with_suffix(self.checkpoint_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            # Atomic replace
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
            temp_path.rename(self.checkpoint_path)
            
        except Exception as e:
            logger.error(f"Failed to save corrupted file checkpoint: {e}")

