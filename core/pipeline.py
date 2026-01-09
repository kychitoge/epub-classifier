"""
Main Pipeline Orchestrator
Coordinates 3-phase processing: Analysis → Enrichment → Organization
"""

import os
import glob
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd

from core.config_loader import ConfigLoader
from core.epub_analyzer import EPUBAnalyzer
from core.status_resolver import StatusResolver
from core.deduplicator import Deduplicator
from web.web_search_manager import WebSearchManager, CaptchaOrRateLimitError
from web.cache_manager import CacheManager
from utils.checkpoint import CheckpointManager
from utils.file_utils import safe_filename, get_unique_filename, ensure_directory, atomic_move
from utils.error_handler import ClassifiedError, InputError, AIError, WebError

logger = logging.getLogger(__name__)


class Pipeline:
    """Main pipeline orchestrator"""
    
    def __init__(self, config: ConfigLoader):
        self.config = config
        self.is_dry_run = config.is_dry_run()
        
        # Initialize components
        self.analyzer = EPUBAnalyzer()
        self.status_resolver = StatusResolver()
        self.deduplicator = Deduplicator()
        # NOTE: LAZY IMPORTS - AI classes are imported dynamically on first use
        # This prevents google.generativeai import and warnings when AI_ALLOWED=False
        self._ai_normalizer = None  # Lazy-loaded AINameNormalizer
        self._translation_detector = None  # Lazy-loaded TranslationDetector
        self.web_searcher = None  # Lazy init (requires browser)
        self.cache_manager = CacheManager(
            cache_dir=config.get("PATHS.CACHE_DIR", ".cache"),
            ttl_days=30
        ) if config.is_cache_enabled() else None
        self.checkpoint = CheckpointManager() if config.is_resume_enabled() else None
        
        # CAPTCHA handling state
        self._captcha_detected = False
        self._captcha_cooldown_until: Optional[datetime] = None
        captcha_cooldown_minutes = config.get("WEB_SEARCH.CAPTCHA_COOLDOWN_MINUTES", 10)
        self._captcha_cooldown_duration = timedelta(minutes=captcha_cooldown_minutes)
        
        # Corrupted files tracking
        self._corrupted_files: set = set()
        if self.checkpoint:
            self._corrupted_files = self.checkpoint.get_corrupted_files()
        
        # Paths
        self.input_folder = config.get("PATHS.INPUT_FOLDER", "books")
        self.output_base = config.get("PATHS.OUTPUT_BASE_FOLDER", "Output")
        
        # Results accumulator (used for both human & machine reports)
        self.result_rows: List[Dict] = []
    
    @property
    def ai_normalizer(self):
        """Lazy-load AINameNormalizer on first access (compliance: avoid import until needed)."""
        if self._ai_normalizer is None:
            from ai.ai_name_normalizer import AINameNormalizer
            self._ai_normalizer = AINameNormalizer(self.config.config)
        return self._ai_normalizer
    
    @property
    def translation_detector(self):
        """Lazy-load TranslationDetector on first access (compliance: avoid import until needed)."""
        if self._translation_detector is None:
            from ai.translation_detector import TranslationDetector
            self._translation_detector = TranslationDetector(self.config.config)
        return self._translation_detector
    
    def run(self) -> None:
        """Run full pipeline"""
        logger.info("=" * 60)
        logger.info("EPUB CLASSIFIER PIPELINE STARTED")
        logger.info(f"Mode: {'DRY-RUN' if self.is_dry_run else 'LIVE'}")
        logger.info("=" * 60)
        
        # Ensure input folder exists
        if not os.path.exists(self.input_folder):
            os.makedirs(self.input_folder)
            logger.info(f"Created input folder: {self.input_folder}")
            logger.info("Add EPUB files and run again.")
            return
        
        # Get EPUB files
        epub_files = glob.glob(os.path.join(self.input_folder, "*.epub"))
        if not epub_files:
            logger.info(f"No EPUB files found in {self.input_folder}")
            return
        
        logger.info(f"Found {len(epub_files)} EPUB files")
        
        # Initialize web searcher (lazy - only if needed)
        web_searcher_initialized = False
        
        try:
            # Process each file
            for idx, epub_path in enumerate(epub_files, 1):
                file_key = os.path.basename(epub_path)
                
                # Check checkpoint (skip if already processed)
                if self.checkpoint and self.checkpoint.is_processed(file_key):
                    logger.info(f"[{idx}/{len(epub_files)}] ⏭️ Skipping (already processed): {file_key}")
                    continue
                
                logger.info(f"[{idx}/{len(epub_files)}] 📖 Processing: {file_key}")
                
                try:
                    result = self._process_file(epub_path, idx, len(epub_files))
                    self.result_rows.append(result)
                    
                    # Mark as processed
                    if self.checkpoint:
                        self.checkpoint.mark_processed(file_key, {"status": result.get("final_status", "Unknown")})
                
                except ClassifiedError as e:
                    logger.error(f"❌ {file_key}: {e}")
                    self.result_rows.append({
                        "original_filename": file_key,
                        "final_status": "Error",
                        "error_type": e.error_type.value,
                        "error_message": str(e)
                    })
                except Exception as e:
                    logger.error(f"❌ {file_key}: Unexpected error: {e}")
                    self.result_rows.append({
                        "original_filename": file_key,
                        "final_status": "Error",
                        "error_type": "system_error",
                        "error_message": str(e)
                    })
            
            # Generate final report
            self._generate_report()
            
        finally:
            # Cleanup web searcher
            if self.web_searcher:
                try:
                    self.web_searcher.close()
                except:
                    pass
        
        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)
    
    def _process_file(self, epub_path: str, idx: int, total: int) -> Dict:
        """
        Process single EPUB file through all phases, in enforced order:

            1. Pre-validation (EPUB integrity)
            2. Local analysis (structure, chapters, metadata)
            3. Translation classification (blocking)
            4. Optional web enrichment (classification must succeed)
            5. Status resolution (Full / Đang ra / Unknown)
            6. Reporting field assembly and optional file move

        Returns:
            Result dictionary with full machine diagnostics.
        """
        filename = os.path.basename(epub_path)
        result: Dict = {
            "original_filename": filename,
            "filepath": epub_path,
            # Validation
            "validation_result": "pending",
            "validation_error": "",
            # Classification
            "classification_label": "unknown",
            "classification_status": "not_run",
            "classification_reason": "",
            "translation_confidence": 0.0,
            "translation_method": "",
            # Local analysis
            "chapter_count": 0,
            "content_hash": "",
            "file_size_mb": 0.0,
            "epub_title": None,
            "epub_author": None,
            # Web
            "web_attempted": False,
            "web_success": False,
            "web_title": "",
            "web_author": "",
            "web_status_raw": "",
            "web_chapters": 0,
            "web_source": "",
            "captcha_blocked": False,
            # Reader-facing status
            "reader_status": "Unknown",
            "reader_status_confidence": 0.0,
            "reader_status_reason": "",
            # Misc
            "is_duplicate": False,
            "duplicate_of": "",
            "final_status": "Unknown",
        }

        # Early exit for known corrupted files
        if filename in self._corrupted_files:
            logger.info("  ⏭️ Skipping corrupted file (permanent skip)")
            result["validation_result"] = "invalid_epub"
            result["validation_error"] = "Corrupted EPUB (permanently skipped)"
            result["final_status"] = "Error"
            return result

        # === 1. PRE-VALIDATION ===
        logger.info("  [Phase 1] Validating EPUB container...")
        if not self.analyzer.validate_format(epub_path):
            logger.warning("  ❌ EPUB format validation failed")
            self._corrupted_files.add(filename)
            if self.checkpoint:
                self.checkpoint.mark_corrupted(filename)
            result["validation_result"] = "invalid_epub"
            result["validation_error"] = "Basic EPUB format validation failed"
            result["final_status"] = "Error"
            return result

        # === 2. LOCAL ANALYSIS ===
        logger.info("  [Phase 2] Analyzing EPUB structure...")
        epub_data = self.analyzer.analyze(epub_path)

        result.update(
            {
                "chapter_count": epub_data["chapter_count"],
                "content_hash": epub_data["content_hash"],
                "file_size_mb": epub_data["file_size_mb"],
                "epub_title": epub_data["epub_title"],
                "epub_author": epub_data["epub_author"],
            }
        )

        if not epub_data["is_valid"]:
            logger.error("  ❌ EPUB parse failed, marking as corrupted")
            self._corrupted_files.add(filename)
            if self.checkpoint:
                self.checkpoint.mark_corrupted(filename)
            result["validation_result"] = "invalid_epub"
            result["validation_error"] = epub_data.get("error", "EPUB parsing failed")
            result["final_status"] = "Error"
            return result

        result["validation_result"] = "ok"

        # Duplicate detection (does not block downstream logic)
        if epub_data["content_hash"]:
            if self.deduplicator.is_duplicate(epub_data["content_hash"]):
                duplicate_path = self.deduplicator.get_duplicate_path(epub_data["content_hash"])
                logger.warning(f"  ⚠️ Duplicate detected (original: {duplicate_path})")
                result["is_duplicate"] = True
                result["duplicate_of"] = duplicate_path or ""
            else:
                self.deduplicator.register(epub_data["content_hash"], epub_path)

        # === 3. TRANSLATION CLASSIFICATION (BLOCKING) ===
        logger.info("  [Phase 3] Detecting translation type (blocking)...")
        translation_result = self.translation_detector.detect(
            filename,
            epub_data.get("epub_title"),
        )

        label = translation_result.get("translation_label", "unknown")
        result.update(
            {
                "classification_label": label,
                "classification_status": "success"
                if label in ("human_translation", "machine_convert")
                else "failed",
                "classification_reason": translation_result.get("reason", ""),
                "translation_confidence": translation_result.get("confidence", 0.0),
                "translation_method": translation_result.get("method", "unknown"),
                "translation_raw_type": translation_result.get("raw_type", ""),
            }
        )

        # Unknown classification → STOP human pipeline, NO web search
        if label == "unknown":
            logger.warning("  ⚠️ Translation type UNKNOWN → skipping web & human report")
            result["final_status"] = "ClassificationUnknown"
            return result

        # === 4. WEB METADATA (OPTIONAL, NON-BLOCKING) ===
        logger.info("  [Phase 4] Optional web metadata lookup...")
        web_data = None
        result["web_attempted"] = True

        # CAPTCHA cooldown
        if self._captcha_cooldown_until and datetime.now() < self._captcha_cooldown_until:
            remaining = (self._captcha_cooldown_until - datetime.now()).total_seconds()
            logger.warning(
                f"  ⚠️ CAPTCHA cooldown active ({int(remaining)}s remaining) - skipping web search"
            )
            result["captcha_blocked"] = True
            result["web_attempted"] = False
        else:
            if self._captcha_cooldown_until and datetime.now() >= self._captcha_cooldown_until:
                logger.info("  ✓ CAPTCHA cooldown expired, resuming web search")
                self._captcha_detected = False
                self._captcha_cooldown_until = None

            if self._captcha_detected:
                logger.warning("  ⚠️ Global CAPTCHA flag set → skipping web search")
                result["captcha_blocked"] = True
                result["web_attempted"] = False
            else:
                # Title normalization only for classification-successful items
                logger.info("  [Phase 4] Normalizing title for web search...")
                ai_result = None
                if self.cache_manager:
                    ai_result = self.cache_manager.get_ai_result(filename)

                if not ai_result:
                    normalized_list = self.ai_normalizer.normalize_filenames([filename])
                    if normalized_list:
                        ai_result = normalized_list[0]
                        if self.cache_manager:
                            self.cache_manager.set_ai_result(filename, ai_result)
                else:
                    logger.info("  ✓ Using cached AI title normalization")

                clean_title = (ai_result or {}).get("canonical_title", "") if ai_result else ""
                if not clean_title or clean_title.lower() == "unknown":
                    logger.warning("  ⚠️ Cannot search web: invalid normalized title")
                else:
                    cached_web = (
                        self.cache_manager.get_web_result(clean_title)
                        if self.cache_manager
                        else None
                    )
                    if cached_web:
                        logger.info("  ✓ Using cached web metadata")
                        web_data = cached_web
                        result["web_success"] = True
                    else:
                        if not self.web_searcher:
                            self.web_searcher = WebSearchManager(self.config.config)
                        try:
                            web_data = self.web_searcher.search_book(clean_title)
                            if web_data:
                                result["web_success"] = True
                                if self.cache_manager:
                                    self.cache_manager.set_web_result(clean_title, web_data)
                        except CaptchaOrRateLimitError:
                            self._captcha_detected = True
                            self._captcha_cooldown_until = (
                                datetime.now() + self._captcha_cooldown_duration
                            )
                            result["captcha_blocked"] = True
                            logger.error(
                                f"  🚨 CAPTCHA detected - cooldown for {self._captcha_cooldown_duration.total_seconds()/60:.0f} minutes"
                            )
                            logger.warning("  ⚠️ Disabling web search for remaining files")

        if web_data:
            result.update(
                {
                    "web_title": web_data.get("web_title", ""),
                    "web_author": web_data.get("web_author", ""),
                    "web_status_raw": web_data.get("web_status", ""),
                    "web_chapters": web_data.get("web_chapters", 0),
                    "web_source": web_data.get("web_source", ""),
                }
            )

        # === 5. STATUS RESOLUTION ===
        logger.info("  [Phase 5] Resolving reader-facing status...")
        status_result = self.status_resolver.resolve_status(
            result["chapter_count"],
            web_data,
        )

        result.update(
            {
                "reader_status": status_result["status"],
                "reader_status_reason": status_result["reason"],
                "reader_status_confidence": status_result["confidence"],
            }
        )

        # final_status is a coarse machine status for checkpoints / debugging
        result["final_status"] = "OK"

        # === 6. ORGANIZATION (optional) ===
        if not self.is_dry_run:
            logger.info("  [Phase 6] Organizing file on disk...")
            self._organize_file(epub_path, result, result["reader_status"])
        else:
            logger.info(
                f"  [DRY-RUN] Would organize file to: {self.output_base}/{result['reader_status']}/"
            )
            result["final_path"] = (
                f"[DRY-RUN] {self.output_base}/{result['reader_status']}/"
            )

        logger.info("  ✅ Complete")
        return result
    
    def _organize_file(self, epub_path: str, result: Dict, status: str) -> None:
        """Organize file: rename and move to output folder"""
        # Build new filename
        title = result.get("canonical_title", result.get("original_filename", "Unknown"))
        author = result.get("web_author", "Unknown")
        source = result.get("web_source", "")
        translation_type = result.get("translation_type", "")
        
        # Safe filenames
        safe_title = safe_filename(title)
        safe_author = safe_filename(author)
        safe_source = safe_filename(source) if source else ""
        
        # Build filename: [Status] Title - Author - Source.epub
        parts = [f"[{status}]", safe_title]
        if safe_author and safe_author != "Unknown":
            parts.append(f"- {safe_author}")
        if safe_source:
            parts.append(f"- {safe_source}")
        
        new_filename = " ".join(parts) + ".epub"
        
        # Destination folder
        dest_folder = os.path.join(self.output_base, status)
        ensure_directory(dest_folder)
        
        # Get unique filename (handle collisions)
        dest_path = get_unique_filename(dest_folder, new_filename)
        
        # Move file
        try:
            atomic_move(epub_path, dest_path)
            result["final_path"] = dest_path
            result["final_filename"] = os.path.basename(dest_path)
            logger.info(f"  ✓ Moved to: {dest_path}")
        except Exception as e:
            logger.error(f"  ❌ Failed to move file: {e}")
            raise
    
    def _generate_report(self) -> None:
        """
        Generate final Excel reports.

        - Human report  → only successfully classified items
        - Machine report → all files with diagnostics
        """
        if not self.result_rows:
            logger.warning("No results to report")
            return

        report_folder = "result"
        ensure_directory(report_folder)

        df = pd.DataFrame(self.result_rows)

        # Human-readable report
        if {"validation_result", "classification_label", "chapter_count"}.issubset(df.columns):
            human_mask = (
                (df["validation_result"] == "ok")
                & (df["classification_label"].isin(["human_translation", "machine_convert"]))
            )
            human_df = df.loc[human_mask].copy()

            if not human_df.empty:
                human_df_out = pd.DataFrame(
                    {
                        "Tên truyện": human_df["epub_title"].fillna(""),
                        "Tác giả": human_df["epub_author"].fillna(""),
                        "Số chương (local)": human_df["chapter_count"],
                        "Tình trạng": human_df["reader_status"],
                        "Thể loại dịch": human_df["classification_label"].map(
                            {
                                "human_translation": "Người dịch",
                                "machine_convert": "Convert",
                            }
                        ),
                        "Trạng thái phân loại": "success",
                    }
                )

                human_path = os.path.join(report_folder, "HumanReport.xlsx")
                try:
                    human_df_out.to_excel(human_path, index=False, engine="openpyxl")
                    logger.info(f"📘 Human report saved: {human_path}")
                    logger.info(f"   Human-visible books: {len(human_df_out)}")
                except Exception as e:
                    logger.error(f"❌ Failed to save human report: {e}")
            else:
                logger.info("No successfully classified books for human report")
        else:
            logger.warning("Result rows missing columns for human report; skipping human export")

        # Machine/system report (all files)
        machine_path = os.path.join(report_folder, "MachineReport.xlsx")
        try:
            df.to_excel(machine_path, index=False, engine="openpyxl")
            logger.info(f"🤖 Machine report saved: {machine_path}")
            logger.info(f"   Total files (incl. failures): {len(df)}")
        except Exception as e:
            logger.error(f"❌ Failed to save machine report: {e}")

