"""
Xây dựng gói triển khai tối thiểu cho EpubClassifier.
Sao chép chỉ các tệp và thư mục cần thiết vào `deploy/EpubClassifier`.
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DEPLOY_DIR = ROOT / "deploy" / "EpubClassifier"

INCLUDE_FILES = [
    "main.py",
    "config.json",
    "requirements.txt",
    "version.txt",
]

INCLUDE_DIRS = [
    "core",
    "ai",
    "web",
    "utils",
]

EXCLUDE_NAMES = {"__pycache__", ".cache", "tests", "processed_log.json", ".hash_registry.json", ".venv"}


def should_copy(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE_NAMES:
        return False
    if path.suffix in {'.pyc', '.pyo'}:
        return False
    return True


def copy_tree(src: Path, dst: Path) -> None:
    # Sao chép cây thư mục loại trừ các mục không mong muốn
    if not src.exists():
        return
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        dest_dir = dst / rel
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Lọc các thư mục
        dirs[:] = [d for d in dirs if should_copy(Path(d))]
        for f in files:
            sp = Path(root) / f
            if should_copy(sp):
                shutil.copy2(sp, dest_dir / f)


def build():
    if DEPLOY_DIR.exists():
        shutil.rmtree(DEPLOY_DIR)
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    # Sao chép tệp
    for f in INCLUDE_FILES:
        src = ROOT / f
        if src.exists() and should_copy(src):
            shutil.copy2(src, DEPLOY_DIR / f)

    # Sao chép thư mục
    for d in INCLUDE_DIRS:
        copy_tree(ROOT / d, DEPLOY_DIR / d)

    print(f"Gói triển khai được tạo tại: {DEPLOY_DIR}")


if __name__ == '__main__':
    build()
