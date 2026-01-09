"""
Các Thao Tác Tệp An Toàn
Ghi nguyên tử, tạo tên tệp an toàn, xác thực tệp.
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Tuple
import re

from utils.error_handler import SystemError, InputError


def safe_filename(text: str, max_length: int = 200) -> str:
    """
    Tạo tên tệp an toàn từ văn bản.
    Loại bỏ các ký tự không hợp lệ, giới hạn độ dài.
    """
    # Loại bỏ ký tự không hợp lệ cho Windows/Linux
    safe = re.sub(r'[<>:"/\\|?*]', '-', text)
    # Loại bỏ dấu chấm và khoảng trắng ở đầu và cuối
    safe = safe.strip('. ')
    # Thay thế nhiều dấu gạch ngang/khoảng trắng bằng dấu gạch ngang đơn
    safe = re.sub(r'[-\s]+', '-', safe)
    # Giới hạn độ dài
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('-')
    # Đảm bảo không trống rỗng
    if not safe:
        safe = "unnamed"
    return safe


def atomic_write(content: bytes, filepath: str) -> None:
    """
    Ghi tệp nguyên tử bằng tệp tạm thời + đổi tên.
    Ngăn ghi một phần khi bị lỗi.
    """
    path = Path(filepath)
    temp_path = path.with_suffix(path.suffix + '.tmp')
    
    try:
        # Ghi vào tệp tạm
        with open(temp_path, 'wb') as f:
            f.write(content)
        
        # Đổi tên nguyên tử (hoạt động cấp HĐH)
        if path.exists():
            path.unlink()
        temp_path.rename(path)
    except Exception as e:
        # Dọn dẹp tệp tạm khi bị lỗi
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        raise SystemError(f"Không thể ghi tệp {filepath}: {e}", original_error=e)


def atomic_copy(src: str, dst: str) -> None:
    """
    Sao chép tệp nguyên tử bằng tệp tạm thời.
    """
    dst_path = Path(dst)
    temp_dst = dst_path.with_suffix(dst_path.suffix + '.tmp')
    
    try:
        # Sao chép đến vị trí tạm
        shutil.copy2(src, str(temp_dst))
        
        # Đổi tên nguyên tử
        if dst_path.exists():
            dst_path.unlink()
        temp_dst.rename(dst_path)
    except Exception as e:
        # Dọn dẹp khi bị lỗi
        if temp_dst.exists():
            try:
                temp_dst.unlink()
            except:
                pass
        raise SystemError(f"Không thể sao chép {src} thành {dst}: {e}", original_error=e)


def atomic_move(src: str, dst: str) -> None:
    """
    Di chuyển tệp nguyên tử bằng tệp tạm thời.
    """
    dst_path = Path(dst)
    temp_dst = dst_path.with_suffix(dst_path.suffix + '.tmp')
    
    try:
        # Sao chép đến vị trí tạm trước
        shutil.copy2(src, str(temp_dst))
        
        # Đổi tên nguyên tử
        if dst_path.exists():
            dst_path.unlink()
        temp_dst.rename(dst_path)
        
        # Chỉ xóa nguồn sau khi sao chép thành công
        os.remove(src)
    except Exception as e:
        # Dọn dẹp khi bị lỗi
        if temp_dst.exists():
            try:
                temp_dst.unlink()
            except:
                pass
        raise SystemError(f"Không thể di chuyển {src} thành {dst}: {e}", original_error=e)


def generate_content_hash(filepath: str, algorithm: str = 'md5') -> str:
    """
    Tạo hash nội dung cho tệp (để khử trùng).
    
    Args:
        filepath: Đường dẫn tệp
        algorithm: 'md5' hoặc 'sha256'
    
    Returns:
        Tóm tắt hex của hash tệp
    """
    hash_obj = hashlib.md5() if algorithm == 'md5' else hashlib.sha256()
    
    try:
        with open(filepath, 'rb') as f:
            # Đọc theo từng phần để xử lý các tệp lớn
            for chunk in iter(lambda: f.read(4096), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        raise InputError(f"Không thể tạo hash cho {filepath}: {e}", original_error=e)


def ensure_directory(dirpath: str) -> None:
    """Đảm bảo thư mục tồn tại, tạo nếu chưa có"""
    Path(dirpath).mkdir(parents=True, exist_ok=True)


def get_unique_filename(base_path: str, filename: str) -> str:
    """
    Tạo tên tệp duy nhất bằng cách nối thêm bộ đếm nếu tệp tồn tại.
    
    Returns:
        Đường dẫn tệp duy nhất
    """
    path = Path(base_path) / filename
    
    if not path.exists():
        return str(path)
    
    # Extract name and extension
    stem = path.stem
    suffix = path.suffix
    
    counter = 1
    while True:
        new_name = f"{stem}_v{counter}{suffix}"
        new_path = path.parent / new_name
        if not new_path.exists():
            return str(new_path)
        counter += 1


def validate_epub_file(filepath: str) -> bool:
    """
    Basic EPUB validation (file exists, has .epub extension, readable).
    Does NOT validate EPUB structure (that's done in epub_analyzer).
    """
    path = Path(filepath)
    
    if not path.exists():
        return False
    
    if path.suffix.lower() != '.epub':
        return False
    
    if not os.access(filepath, os.R_OK):
        return False
    
    return True

