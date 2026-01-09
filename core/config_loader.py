"""
Trình Tải Cấu Hình
Tải cấu hình từ config.json và biến môi trường.
Xác thực các cài đặt bắt buộc.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any
import logging

from utils.error_handler import SystemError

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Tải và xác thực cấu hình"""
    
    DEFAULT_CONFIG = {
        "API_KEYS": {
            "GOOGLE_API_KEY": "",
            "METRUYENCV_COOKIE": ""
        },
        "AI_STRATEGY": {
            "PRIMARY": {
                "NAME": "gemma-3-27b-it",
                "RPM": 30,
                "BATCH_SIZE": 5
            },
            "FALLBACK": {
                "NAME": "gemini-2.0-flash-exp",
                "RPM": 5,
                "BATCH_SIZE": 4
            }
        },
        # Runtime is strictly single-process, single-browser; keep SYSTEM minimal and deterministic.
        "SYSTEM": {
            "MAX_WORKERS": 1,
            "SAVE_INTERVAL": 20
        },
        "PATHS": {
            "INPUT_FOLDER": "books",
            "OUTPUT_BASE_FOLDER": "Output",
            "LOG_FILE": "app.log",
            "CACHE_DIR": ".cache"
        },
        "FEATURES": {
            "DRY_RUN": False,
            "RESUME_ENABLED": True,
            "CACHE_ENABLED": True,
            "HEADLESS_BROWSER": False
        }
    }
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._apply_env_overrides()
        self._validate_config()
    
    def _load_config(self) -> None:
        """Tải cấu hình từ tệp JSON"""
        if not self.config_path.exists():
            logger.warning(f"Không tìm thấy tệp cấu hình tại {self.config_path}, sử dụng mặc định")
            self.config = self._deep_copy_dict(self.DEFAULT_CONFIG)
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            
            # Hợp nhất với mặc định (cấu hình tệp ghi đè mặc định)
            self.config = self._deep_merge(self.DEFAULT_CONFIG, file_config)
            logger.info(f"Đã tải cấu hình từ {self.config_path}")
        except Exception as e:
            raise SystemError(f"Không thể tải cấu hình: {e}", original_error=e)
    
    def _apply_env_overrides(self) -> None:
        """Áp dụng ghi đè biến môi trường"""
        # API Keys
        if os.getenv('GOOGLE_API_KEY'):
            self.config['API_KEYS']['GOOGLE_API_KEY'] = os.getenv('GOOGLE_API_KEY')
        
        # Đường dẫn
        if os.getenv('INPUT_FOLDER'):
            self.config['PATHS']['INPUT_FOLDER'] = os.getenv('INPUT_FOLDER')
        if os.getenv('OUTPUT_FOLDER'):
            self.config['PATHS']['OUTPUT_BASE_FOLDER'] = os.getenv('OUTPUT_FOLDER')
        
        # Tính năng
        if os.getenv('DRY_RUN', '').lower() == 'true':
            self.config['FEATURES']['DRY_RUN'] = True
        if os.getenv('HEADLESS', '').lower() == 'true':
            self.config['FEATURES']['HEADLESS_BROWSER'] = True
    
    def _validate_config(self) -> None:
        """Xác thực cấu hình bắt buộc"""
        # Kiểm tra API key
        api_key = self.config.get('API_KEYS', {}).get('GOOGLE_API_KEY', '')
        if not api_key:
            logger.warning("GOOGLE_API_KEY không được đặt - các tính năng AI sẽ thất bại")
        
        # Xác thực đường dẫn
        input_folder = self.config.get('PATHS', {}).get('INPUT_FOLDER', '')
        if not input_folder:
            raise SystemError("INPUT_FOLDER không được cấu hình")
        
        # Xác thực chiến lược AI
        primary = self.config.get('AI_STRATEGY', {}).get('PRIMARY', {})
        if not primary.get('NAME'):
            raise SystemError("AI_STRATEGY.PRIMARY.NAME không được cấu hình")
    
    def _deep_copy_dict(self, d: Dict) -> Dict:
        """Sao chép sâu từ điển"""
        import copy
        return copy.deepcopy(d)
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Hợp nhất sâu hai từ điển"""
        result = self._deep_copy_dict(base)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Lấy giá trị cấu hình theo đường dẫn được phân tách bằng dấu chấm.
        
        Ví dụ: get('API_KEYS.GOOGLE_API_KEY')
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def is_dry_run(self) -> bool:
        """Kiểm tra xem chế độ thử nghiệm có được bật không"""
        return self.config.get('FEATURES', {}).get('DRY_RUN', False)
    
    def is_resume_enabled(self) -> bool:
        """Kiểm tra xem tính năng tiếp tục có được bật không"""
        return self.config.get('FEATURES', {}).get('RESUME_ENABLED', True)
    
    def is_cache_enabled(self) -> bool:
        """Kiểm tra xem bộ nhớ đệm có được bật không"""
        return self.config.get('FEATURES', {}).get('CACHE_ENABLED', True)

