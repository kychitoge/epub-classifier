"""
Bộ Phân Giải Trạng Thái
Xác định trạng thái cuối cùng (Full/Đang ra/Không xác định) bằng cách so sánh dữ liệu cục bộ với web.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class StatusResolver:
    """Giải quyết trạng thái hoàn thành dành cho người đọc bằng cách so sánh chương cục bộ với web.

    Quy tắc kinh doanh (không thể thay đổi):
    - "Full"    → local_chapters >= web_chapters (khi web khả dụng)
    - "Đang ra" → local_chapters <  web_chapters (khi web khả dụng)
    - "Unknown" → khi siêu dữ liệu web không khả dụng hoặc không thể sử dụng được
    """

    def __init__(self):
        pass

    def resolve_status(self, local_chapters: int, web_data: Optional[Dict]) -> Dict:
        """
        Giải quyết trạng thái cuối cùng bằng cách so sánh dữ liệu cục bộ và web.

        Args:
            local_chapters: Số chương từ EPUB (cục bộ)
            web_data: Từ điển siêu dữ liệu web tùy chọn với khóa:
                - web_chapters: int

        Returns:
            {
                "status": "Full" | "Đang ra" | "Unknown",
                "reason": str,
                "confidence": float
            }
        """
        # Không có web → Unknown (spec: "Unknown (if web unavailable)")
        if not web_data:
            return {
                "status": "Unknown",
                "reason": "Không có siêu dữ liệu web",
                "confidence": 0.0,
            }

        web_chapters = int(web_data.get("web_chapters", 0) or 0)

        # Web không có thông tin chương hữu ích → Unknown
        if web_chapters <= 0 or local_chapters <= 0:
            return {
                "status": "Unknown",
                "reason": f"Dữ liệu chương không đủ (local={local_chapters}, web={web_chapters})",
                "confidence": 0.0,
            }

        # Quy tắc cốt lõi: chỉ so sánh số lượng, KHÔNG tin cậy nhãn "status" web
        if local_chapters >= web_chapters:
            return {
                "status": "Full",
                "reason": f"Chương cục bộ ({local_chapters}) ≥ web ({web_chapters})",
                "confidence": 0.9,
            }

        # local_chapters < web_chapters
        return {
            "status": "Đang ra",
            "reason": f"Chương cục bộ ({local_chapters}) < web ({web_chapters})",
            "confidence": 0.9,
        }

