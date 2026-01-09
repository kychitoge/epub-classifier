"""
Epub Classifier - Điểm Vào Chính
Điểm vào sản xuất với hỗ trợ dòng lệnh.
"""

import sys
import argparse
import logging
from pathlib import Path

from core.config_loader import ConfigLoader
from core.pipeline import Pipeline
from utils.logger import init_structured_logger

# Khởi tạo logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Điểm vào chính"""
    parser = argparse.ArgumentParser(
        description="Epub Classifier - Phân tích, chuẩn hóa và tổ chức EPUB tiểu thuyết.\n"
                    "Thư mục đầu vào được cấu hình trong config.json (PATHS.INPUT_DIR).",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config.json',
        help='Đường dẫn tệp config.json (bắt buộc; chỉ định thư mục đầu vào và tất cả cài đặt)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Chế độ thử nghiệm: phân tích nhưng không sửa đổi tệp'
    )
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Vô hiệu hóa khả năng tiếp tục (bắt đầu từ đầu)'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Vô hiệu hóa bộ nhớ đệm (buộc gọi AI/web mới)'
    )
    
    args = parser.parse_args()
    
    # Tải cấu hình
    try:
        config = ConfigLoader(args.config)
    except Exception as e:
        logger.error(f"Không thể tải cấu hình: {e}")
        sys.exit(1)
    
    # Ghi đè cấu hình bằng đối số CLI
    if args.dry_run:
        config.config['FEATURES']['DRY_RUN'] = True
    if args.no_resume:
        config.config['FEATURES']['RESUME_ENABLED'] = False
    if args.no_cache:
        config.config['FEATURES']['CACHE_ENABLED'] = False
    
    # Khởi tạo logger có cấu trúc
    log_dir = config.get("PATHS.LOG_FILE", ".")
    if log_dir and Path(log_dir).is_file():
        log_dir = Path(log_dir).parent
    init_structured_logger("epub_classifier", str(log_dir), json_log=True)
    
    # Chạy pipeline
    try:
        pipeline = Pipeline(config)
        pipeline.run()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Bị gián đoạn bởi người dùng")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Lỗi nghiêm trọng: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

