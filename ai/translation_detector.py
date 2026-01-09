"""
Translation Type Detector
Detects "Convert" (machine translation) vs "Dịch" (human translation).
Uses heuristic first, AI fallback for uncertain cases.
"""

import re
import logging
from typing import Dict, Optional
from datetime import datetime
import time

from utils.error_handler import AIError

logger = logging.getLogger(__name__)


class TranslationDetector:
    """
    Detects translation type (machine vs human) from filename & EPUB title.

    Canonical output labels (project-wide):
    - "machine_convert"   → machine / auto translation
    - "human_translation" → manually translated
    - "unknown"           → cannot determine
    """
    
    # Heuristic keywords
    CONVERT_KEYWORDS = {
        "convert", "converted", "mtl", "machine translation",
        "auto translate", "google translate", "dịch máy"
    }
    
    DICH_KEYWORDS = {
        "dịch", "dich", "translated", "human translation",
        "dịch bởi", "dich boi", "translator", "dịch giả"
    }
    
    def __init__(self, config: Dict):
        self.config = config
        self.model = None
        self.model_name = None
        self.rpm = 30
        self._last_api_call = datetime.min
        self.ai_enabled = False  # Explicit gate: AI only allowed if explicitly enabled
        self._genai = None  # Lazy import - load only if AI is enabled
        
        # Store API config for lazy initialization
        self.api_key = config.get("API_KEYS", {}).get("GOOGLE_API_KEY", "")
        self.ai_allowed = config.get("AI_ALLOWED", False)  # MUST be explicitly set to True
        
        # NOTE: Lazy import - google.generativeai is NOT imported at module load
        # This prevents deprecation/runtime warnings when AI_ALLOWED=False
        if self.api_key and self.ai_allowed:
            self._init_ai_model()
        elif self.api_key and not self.ai_allowed:
            logger.info("AI model available but AI_ALLOWED=False; using heuristic only")

        # Canonical labels allowed in-system
        self._CANONICAL_LABELS = {"machine_convert", "human_translation", "unknown"}
    
    def _init_ai_model(self):
        """Lazy initialization of AI model - ONLY called when AI is explicitly enabled."""
        if self._genai is not None:  # Already initialized
            return
        
        try:
            # LAZY IMPORT: Only import google.generativeai when AI is enabled
            # This prevents runtime warnings and deprecation messages when AI_ALLOWED=false
            import google.generativeai as genai
            self._genai = genai
            
            genai.configure(api_key=self.api_key)
            model_name = self.config.get("AI_STRATEGY", {}).get("PRIMARY", {}).get("NAME", "gemma-3-27b-it")
            self.model = genai.GenerativeModel(model_name)
            self.model_name = model_name
            self.rpm = int(self.config.get("AI_STRATEGY", {}).get("PRIMARY", {}).get("RPM", 30))
            self.ai_enabled = True
            logger.info(f"Translation detector AI initialized: {model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize AI model: {e}, using heuristic only")
    
    def detect(self, filename: str, epub_title: Optional[str] = None) -> Dict:
        """
        Detect translation type from filename and optional EPUB title.
        
        FROZEN decision order (non-negotiable):
        1. Canonicalize inputs
        2. Heuristic (strong filename/title patterns)
        3. Conflict detection → immediate unknown
        4. Soft heuristics (proposal only)
        5. AI (ONLY if allowed)
        6. Final canonicalization
        
        Returns a canonicalized result dict:
            {
                "translation_label": "machine_convert" | "human_translation" | "unknown",
                "raw_type": "Convert" | "Dịch" | "Unknown",
                "confidence": float (0.0-1.0),
                "method": "heuristic" | "ai" | "unknown",
                "reason": str
            }
        """
        # STEP 1: Canonicalize inputs
        text = filename.lower() if filename else ""
        if epub_title:
            text += " " + epub_title.lower()
        
        # STEP 2: Heuristic detection
        heuristic_result = self._heuristic_detect(text)
        raw_type = heuristic_result.get("translation_type", "Unknown")
        confidence = heuristic_result.get("confidence", 0.0)
        
        # STEP 3: Conflict detection → IMMEDIATE UNKNOWN (no fallback, no retry)
        # If both Convert and Dịch keywords found = conflict → unknown (FINAL)
        if heuristic_result.get("_conflict", False):
            return self._canonicalize_result({
                "translation_type": "Unknown",
                "confidence": 0.0,
                "method": "heuristic",
                "reason": "Conflict: both Convert and Dịch keywords found → unknown (no AI fallback)"
            })
        
        # STEP 4: Strong heuristic (high confidence) → return immediately
        if confidence >= 0.8:
            return self._canonicalize_result(heuristic_result)
        
        # STEP 5: Soft heuristics (no keyword match) → check if AI allowed
        if confidence <= 0.3 and self.api_key and self.ai_allowed:
            # Lazy init AI if needed
            if self._genai is None:
                self._init_ai_model()
            
            if self.ai_enabled:
                try:
                    ai_result = self._ai_detect(filename, epub_title)
                    # Only use AI if it has HIGHER confidence than heuristic
                    if ai_result.get("confidence", 0.0) > confidence:
                        return self._canonicalize_result(ai_result)
                except Exception as e:
                    logger.warning(f"AI detection failed: {e}, falling back to heuristic")
        
        # STEP 6: Final canonicalization (return best available result)
        return self._canonicalize_result(heuristic_result)
    
    def _heuristic_detect(self, text: str) -> Dict:
        """
        Heuristic detection using strong patterns.
        
        Conflict detection: if both Convert and Dịch keywords present → mark as conflict.
        """
        has_convert = any(kw in text for kw in self.CONVERT_KEYWORDS)
        has_dich = any(kw in text for kw in self.DICH_KEYWORDS)
        
        # CONFLICT DETECTION: both keywords present → cannot determine safely
        if has_convert and has_dich:
            return {
                "translation_type": "Unknown",
                "confidence": 0.0,
                "method": "heuristic",
                "reason": "Conflict: both Convert and Dịch keywords found",
                "_conflict": True  # Mark as conflict for enforcement
            }
        
        # Strong pattern: Convert only
        if has_convert and not has_dich:
            return {
                "translation_type": "Convert",
                "confidence": 0.85,
                "method": "heuristic",
                "reason": "Found Convert keywords",
                "_conflict": False
            }
        
        # Strong pattern: Dịch only
        if has_dich and not has_convert:
            return {
                "translation_type": "Dịch",
                "confidence": 0.85,
                "method": "heuristic",
                "reason": "Found Dịch keywords",
                "_conflict": False
            }
        
        # Soft heuristic: No keywords found (proposal only, AI fallback allowed)
        return {
            "translation_type": "Unknown",
            "confidence": 0.2,
            "method": "heuristic",
            "reason": "No translation keywords found",
            "_conflict": False
        }
    
    def _ai_detect(self, filename: str, epub_title: Optional[str] = None) -> Dict:
        """
        AI-based detection - ONLY callable if AI is explicitly enabled.
        
        GUARD: Impossible to trigger when forbidden.
        """
        # EXPLICIT GATE: Enforce AI_ALLOWED policy
        if not self.ai_enabled:
            raise AIError("AI detection called but AI_ALLOWED=False (policy violation)")
        
        if not self.model:
            raise AIError("AI model not initialized")
        
        # Rate limiting
        self._sleep_for_rate_limit()
        
        # Build prompt
        context = f"Filename: {filename}"
        if epub_title:
            context += f"\nEPUB Title: {epub_title}"
        
        prompt = f"""Analyze this Vietnamese novel filename and determine translation type:

{context}

Determine if this is:
- "Convert" (machine translation / auto-translated)
- "Dịch" (human translation / manually translated)
- "Unknown" (cannot determine)

Look for indicators:
- "Convert" keywords: convert, MTL, machine translation, auto translate
- "Dịch" keywords: dịch, dich, translated by, translator name

Return ONLY JSON:
{{
    "translation_type": "Convert" | "Dịch" | "Unknown",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}"""
        
        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Extract JSON from response
            import json
            json_match = re.search(r'\{[^}]+\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return {
                    "translation_type": result.get("translation_type", "Unknown"),
                    "confidence": float(result.get("confidence", 0.5)),
                    "method": "ai",
                    "reason": result.get("reason", "AI analysis"),
                }
            else:
                raise AIError("Invalid AI response format")
        
        except Exception as e:
            raise AIError(f"AI detection failed: {e}", original_error=e)
    
    def _sleep_for_rate_limit(self):
        """Enforce rate limit"""
        gap = (60.0 / self.rpm) * 1.15
        elapsed = (datetime.now() - self._last_api_call).total_seconds()
        
        if elapsed < gap:
            sleep_time = gap - elapsed
            time.sleep(sleep_time)
        
        self._last_api_call = datetime.now()

    # === Canonicalization ===
    def _canonicalize_result(self, raw: Dict) -> Dict:
        """
        Map model/heuristic-specific labels into project-wide canonical labels.

        Input (raw):
            {
              "translation_type": "Convert" | "Dịch" | "Unknown" | other,
              "confidence": float,
              "method": str,
              "reason": str,
            }
        """
        raw_type = (raw.get("translation_type") or "").strip()

        if raw_type.lower() in ["convert", "machine", "machine translation"]:
            label = "machine_convert"
        elif raw_type.lower() in ["dịch", "dich", "human", "human translation"]:
            label = "human_translation"
        else:
            label = "unknown"

        # Ensure method is one of allowed internal methods
        method = (raw.get("method") or "unknown").lower()
        if method not in ("heuristic", "ai"):
            method = "unknown"

        confidence = float(raw.get("confidence", 0.0))

        # Final safety: enforce canonical label set — never return legacy labels in logic
        if label not in self._CANONICAL_LABELS:
            label = "unknown"
            confidence = 0.0
            method = "unknown"

        return {
            "translation_label": label,
            "raw_type": raw_type or "Unknown",
            "confidence": confidence,
            "method": method,
            "reason": raw.get("reason", ""),
        }

