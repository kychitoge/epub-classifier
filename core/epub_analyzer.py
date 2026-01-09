"""
Công cụ Phân tích EPUB
Xác thực định dạng EPUB, trích xuất siêu dữ liệu, tính số chương.
"""

import ebooklib
from ebooklib import epub
from pathlib import Path
from typing import Dict, Optional
import logging

from utils.error_handler import InputError
from utils.file_utils import generate_content_hash

logger = logging.getLogger(__name__)


class EPUBAnalyzer:
    """Phân tích tệp EPUB để trích xuất siêu dữ liệu và cấu trúc"""
    
    def __init__(self):
        pass
    
    def analyze(self, epub_path: str) -> Dict:
        """
        Phân tích tệp EPUB và trích xuất siêu dữ liệu.
        
        Trả về:
            {
                "filepath": str,
                "filename": str,
                "chapter_count": int,
                "content_hash": str,
                "file_size_mb": float,
                "epub_title": Optional[str],
                "epub_author": Optional[str],
                "is_valid": bool,
                "error": Optional[str]
            }
        """
        path = Path(epub_path)
        
        result = {
            "filepath": str(path.absolute()),
            "filename": path.name,
            "chapter_count": 0,
            "content_hash": "",
            "file_size_mb": 0.0,
            "epub_title": None,
            "epub_author": None,
            "is_valid": False,
            "error": None
        }
        
        try:
            # Kích thước tệp
            result["file_size_mb"] = path.stat().st_size / (1024 * 1024)
            
            # Hash nội dung (để khử trùng)
            try:
                result["content_hash"] = generate_content_hash(str(path))
            except Exception as e:
                logger.warning(f"Không thể tạo hash cho {path.name}: {e}")
                result["error"] = f"Tạo hash không thành công: {e}"
            
            # Phân tích EPUB
            try:
                book = epub.read_epub(str(path))
                
                # Số chương (các mục tài liệu trong spine)
                items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
                result["chapter_count"] = max(0, len(items))
                
                # Trích xuất siêu dữ liệu
                metadata = book.get_metadata('DC', 'title')
                if metadata:
                    result["epub_title"] = metadata[0][0] if metadata[0] else None
                
                metadata = book.get_metadata('DC', 'creator')
                if metadata:
                    result["epub_author"] = metadata[0][0] if metadata[0] else None
                
                result["is_valid"] = True
                
            except Exception as e:
                error_msg = f"Phân tích EPUB không thành công: {e}"
                logger.error(f"{path.name}: {error_msg}")
                result["error"] = error_msg
                result["is_valid"] = False
                # Không nâng cao - trả về kết quả với cờ lỗi
        
        except FileNotFoundError:
            raise InputError(f"Không tìm thấy tệp: {epub_path}")
        except PermissionError as e:
            raise InputError(f"Quyền truy cập bị từ chối: {epub_path}", original_error=e)
        except Exception as e:
            raise InputError(f"Không thể phân tích EPUB: {epub_path}", original_error=e)
        
        return result
    
    def validate_format(self, epub_path: str) -> bool:
        """
        Xác thực định dạng nhanh (không phân tích cấu trúc đầy đủ).
        
        Trả về:
            True nếu tệp dường như là EPUB hợp lệ
        """
        path = Path(epub_path)
        
        if not path.exists():
            return False
        
        if path.suffix.lower() != '.epub':
            return False
        
        # Cố gắng mở dưới dạng ZIP (EPUB là lưu trữ ZIP)
        try:
            import zipfile
            with zipfile.ZipFile(str(path), 'r') as zf:
                # Kiểm tra tệp loại MIME
                if 'mimetype' not in zf.namelist():
                    return False
                # Kiểm tra nội dung loại MIME
                mimetype = zf.read('mimetype').decode('utf-8').strip()
                if mimetype != 'application/epub+zip':
                    return False
            return True
        except Exception:
            return False

