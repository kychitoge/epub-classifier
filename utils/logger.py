"""
Tiện ích Logging Có Cấu Trúc
Cung cấp cả logging có thể đọc được bằng con người và máy móc (JSON).
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


class StructuredLogger:
    """Logger hỗ trợ cả đầu ra văn bản và JSON"""
    
    def __init__(self, name: str, log_dir: str = ".", json_log: bool = True):
        self.name = name
        self.logger = logging.getLogger(name)
        self.log_dir = Path(log_dir)
        self.json_log = json_log
        
        # Đảm bảo thư mục nhật ký tồn tại
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Thiết lập các xử lý
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Thiết lập các trình xử lý tệp và bảng điều khiển"""
        # Xóa các trình xử lý hiện có
        self.logger.handlers.clear()
        self.logger.setLevel(logging.INFO)
        
        # Tệp nhật ký văn bản (có thể đọc được)
        text_log_path = self.log_dir / "app.log"
        text_handler = logging.FileHandler(text_log_path, encoding='utf-8')
        text_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(text_handler)
        
        # Xử lý bảng điều khiển
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(console_handler)
        
        # Tệp nhật ký JSON (có thể đọc được bằng máy móc)
        if self.json_log:
            json_log_path = self.log_dir / "app.json.log"
            self.json_handler = logging.FileHandler(json_log_path, encoding='utf-8')
            self.json_handler.setLevel(logging.INFO)
            self.logger.addHandler(self.json_handler)
    
    def _log_json(self, level: str, message: str, extra: Optional[Dict[str, Any]] = None):
        """Viết mục nhập nhật ký JSON có cấu trúc"""
        if not self.json_log:
            return
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "logger": self.name,
            "message": message
        }
        
        if extra:
            log_entry.update(extra)
        
        json_str = json.dumps(log_entry, ensure_ascii=False)
        self.json_handler.stream.write(json_str + "\n")
        self.json_handler.stream.flush()
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.info(message)
        if extra:
            self._log_json("INFO", message, extra)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.warning(message)
        if extra:
            self._log_json("WARNING", message, extra)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.error(message)
        if extra:
            self._log_json("ERROR", message, extra)
    
    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.critical(message)
        if extra:
            self._log_json("CRITICAL", message, extra)
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.debug(message)
        if extra:
            self._log_json("DEBUG", message, extra)


# Phiên bản logger toàn cầu (sẽ được khởi tạo bằng cấu hình)
_logger_instance: Optional[StructuredLogger] = None


def get_logger(name: str = __name__) -> logging.Logger:
    """Lấy logger Python tiêu chuẩn (để tương thích ngược)"""
    return logging.getLogger(name)


def init_structured_logger(name: str, log_dir: str = ".", json_log: bool = True) -> StructuredLogger:
    """Khởi tạo và trả về logger có cấu trúc"""
    global _logger_instance
    _logger_instance = StructuredLogger(name, log_dir, json_log)
    return _logger_instance


def get_structured_logger() -> Optional[StructuredLogger]:
    """Lấy phiên bản logger có cấu trúc toàn cầu"""
    return _logger_instance

