"""
Phân loại Lỗi và Xử lý
Cung cấp các loại lỗi có cấu trúc để gỡ lỗi và khôi phục tốt hơn.
"""

from enum import Enum
from typing import Optional


class ErrorType(Enum):
    """Phân loại lỗi để xử lý thích hợp"""
    INPUT_ERROR = "input_error"      # EPUB bị hỏng, định dạng không hợp lệ
    AI_ERROR = "ai_error"            # Lỗi API, giới hạn tốc độ, phản hồi không hợp lệ
    WEB_ERROR = "web_error"          # Lỗi mạng, CAPTCHA, timeout
    LOGIC_ERROR = "logic_error"     # Vi phạm quy tắc kinh doanh, không nhất quán dữ liệu
    SYSTEM_ERROR = "system_error"   # I/O tệp, quyền, lỗi HĐH


class ClassifiedError(Exception):
    """Lỗi có cấu trúc với phân loại"""
    
    def __init__(self, error_type: ErrorType, message: str, 
                 original_error: Optional[Exception] = None, 
                 recoverable: bool = False):
        self.error_type = error_type
        self.message = message
        self.original_error = original_error
        self.recoverable = recoverable
        super().__init__(self.message)
    
    def __str__(self):
        return f"[{self.error_type.value}] {self.message}"
    
    def to_dict(self):
        """Chuyển đổi sang từ điển để ghi nhật ký"""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "recoverable": self.recoverable,
            "original_error": str(self.original_error) if self.original_error else None
        }


class InputError(ClassifiedError):
    """Tệp đầu vào hoặc lỗi định dạng"""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(ErrorType.INPUT_ERROR, message, original_error, recoverable=False)


class AIError(ClassifiedError):
    """Lỗi xử lý hoặc API AI"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, recoverable: bool = True):
        super().__init__(ErrorType.AI_ERROR, message, original_error, recoverable)


class WebError(ClassifiedError):
    """Lỗi tìm kiếm web hoặc mạng"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, recoverable: bool = True):
        super().__init__(ErrorType.WEB_ERROR, message, original_error, recoverable)


class LogicError(ClassifiedError):
    """Lỗi logic kinh doanh hoặc không nhất quán dữ liệu"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, recoverable: bool = False):
        super().__init__(ErrorType.LOGIC_ERROR, message, original_error, recoverable)


class SystemError(ClassifiedError):
    """Lỗi cấp hệ thống (I/O, quyền, HĐH)"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, recoverable: bool = False):
        super().__init__(ErrorType.SYSTEM_ERROR, message, original_error, recoverable)

