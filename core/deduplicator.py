"""
Công cụ Khử Trùng
Phát hiện trùng lặp dựa trên hash để tránh xử lý cùng một tệp nhiều lần.
"""

import json
import os
from pathlib import Path
from typing import Dict, Set, Optional
import logging

from utils.error_handler import SystemError

logger = logging.getLogger(__name__)


class Deduplicator:
    """Quản lý sổ đăng ký hash nội dung để phát hiện trùng lặp"""
    
    def __init__(self, registry_path: str = ".hash_registry.json"):
        self.registry_path = Path(registry_path)
        self._hash_to_file: Dict[str, str] = {}  # hash -> filepath
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Tải sổ đăng ký hash từ tệp"""
        if not self.registry_path.exists():
            logger.info(f"Không tìm thấy sổ đăng ký hash, bắt đầu mới")
            return
        
        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                self._hash_to_file = data
            
            logger.info(f"Đã tải sổ đăng ký hash: {len(self._hash_to_file)} mục")
        except Exception as e:
            logger.warning(f"Không thể tải sổ đăng ký hash: {e}, bắt đầu mới")
            self._hash_to_file = {}
    
    def is_duplicate(self, content_hash: str) -> bool:
        """
        Kiểm tra xem hash đã tồn tại trong sổ đăng ký.
        
        Args:
            content_hash: Hash MD5 hoặc SHA256 của nội dung tệp
        
        Returns:
            True nếu tìm thấy bản sao
        """
        return content_hash in self._hash_to_file
    
    def get_duplicate_path(self, content_hash: str) -> Optional[str]:
        """
        Lấy đường dẫn tệp của bản sao nếu tồn tại.
        
        Returns:
            Đường dẫn tệp gốc, hoặc None
        """
        return self._hash_to_file.get(content_hash)
    
    def register(self, content_hash: str, filepath: str) -> None:
        """
        Đăng ký hash tệp trong sổ đăng ký.
        
        Args:
            content_hash: Hash nội dung
            filepath: Đường dẫn tệp
        """
        if not content_hash:
            return
        
        self._hash_to_file[content_hash] = filepath
        self._save_registry()
    
    def _save_registry(self) -> None:
        """Lưu sổ đăng ký hash vào tệp (ghi nguyên tử)"""
        try:
            temp_path = self.registry_path.with_suffix(self.registry_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._hash_to_file, f, ensure_ascii=False, indent=2)
            
            # Thay thế nguyên tử
            if self.registry_path.exists():
                self.registry_path.unlink()
            temp_path.rename(self.registry_path)
        except Exception as e:
            logger.error(f"Không thể lưu sổ đăng ký hash: {e}")
            # Đừng nâng cao - lỗi sổ đăng ký không nên dừng xử lý
    
    def get_registry_size(self) -> int:
        """Lấy số lượng hash đã đăng ký"""
        return len(self._hash_to_file)
    
    def clear_registry(self) -> None:
        """Xóa sổ đăng ký (dành cho kiểm tra)"""
        self._hash_to_file = {}
        if self.registry_path.exists():
            self.registry_path.unlink()
        logger.info("Đã xóa sổ đăng ký hash")

