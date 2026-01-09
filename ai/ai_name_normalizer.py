"""
AI-Assisted Filename Normalization Module
Pre-processing layer for EPUB filenames → canonical novel titles.

Strict AI Contract:
- LLM analyzes strings ONLY
- NO guessing: chapter count, author, completion status
- NO web browsing
- Returns "unknown" if uncertain
"""

import json
import re
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AINameNormalizer:
    """
    Normalize EPUB filenames into clean, canonical novel titles.
    Output feeds directly into WebSearchManager.
    """

    def __init__(self, config: Dict):
        """Initialize with API config."""
        self.config = config
        self._genai = None  # Lazy import - load only if AI is needed
        self.model = None
        self.model_name = None
        self._last_api_call = datetime.min
        self.rpm = 30
        
        # NOTE: Lazy import - google.generativeai is NOT imported at module load
        # This prevents deprecation/runtime warnings when AI_ALLOWED=False
        # Model initialization deferred to _init_ai_model()

        # Junk tokens to remove
        self.JUNK_TOKENS = {
            "full", "dịch", "viétphrase", "kosuga", "convert", "epub", "pdf",
            "tl", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9",
            "final", "official", "raw", "scan", "digital", "repack"
        }

        # Side story keywords
        self.SIDE_STORY_KEYWORDS = {
            "ngoại truyện", "ngoai truyen", "side story", "spinoff",
            "ngoài truyện", "ngoai truyen"
        }

        # Fanfic keywords
        self.FANFIC_KEYWORDS = {
            "fanfic", "đồng nhân", "dong nhan", "fan-fiction",
            "doujinshi"
        }

        # Parody keywords
        self.PARODY_KEYWORDS = {
            "parody", "chế", "nhái", "satire"
        }

    def _init_ai_model(self):
        """Lazy initialization of AI model - ONLY called when AI normalization is needed."""
        if self._genai is not None:  # Already initialized
            return
        
        try:
            # LAZY IMPORT: Only import google.generativeai when needed
            # This prevents runtime warnings and deprecation messages when AI_ALLOWED=false
            import google.generativeai as genai
            self._genai = genai
            
            api_key = self.config.get("API_KEYS", {}).get("GOOGLE_API_KEY", "")
            if not api_key:
                logger.warning("No Google API key configured - AI normalization disabled")
                return
            
            genai.configure(api_key=api_key)
            model_name = self.config.get("AI_STRATEGY", {}).get("PRIMARY", {}).get("NAME", "gemini-pro")
            self.model = genai.GenerativeModel(model_name)
            self.model_name = model_name
            self.rpm = int(self.config.get("AI_STRATEGY", {}).get("PRIMARY", {}).get("RPM", 30))
            logger.info(f"✅ AINameNormalizer model initialized: {model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize AI normalizer: {e}")
            self.model = None

    def _sleep_for_rate_limit(self):
        """Enforce rate limit with 15% safety buffer."""
        gap = (60.0 / self.rpm) * 1.15
        elapsed = (datetime.now() - self._last_api_call).total_seconds()

        if elapsed < gap:
            sleep_time = gap - elapsed
            logger.debug(f"⏳ Rate limit sleep: {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self._last_api_call = datetime.now()

    def _build_normalization_prompt(self, filenames: List[str]) -> str:
        """
        Build LLM prompt for filename normalization.
        Strict rules: analyze strings ONLY, no guessing.
        """
        items = []
        for idx, fname in enumerate(filenames, start=1):
            items.append(f"File {idx}: {fname}")

        prompt = f"""Role: Filename Normalizer for Vietnamese novels (EPUB format).

Your STRICT rules:
1. Analyze ONLY the string provided
2. Extract the MOST COMMONLY USED novel title
3. Remove: uploader names, tags, junk ([Full], [Dịch], VietPhrase, Kosuga, Convert, EPUB, PDF)
4. Remove: chapter/volume indicators (Ch., Vol., C01, etc.)
5. PRESERVE Vietnamese accents (ả, ế, ị, ô, ư, etc.)
6. Return title SHORT and CLEAN
7. DO NOT guess: chapter count, author, completion status
8. If uncertain, return "unknown"
9. Confidence: 0.0-1.0 (1.0 = 100% confident it's a valid novel title)
10. Classify content_type:
    - "side_story" if contains: ngoại truyện, ngoai truyen, side story
    - "fanfic" if contains: fanfic, đồng nhân, dong nhan
    - "parody" if contains: parody, chế, nhái
    - "main_novel" otherwise

Input files:
{chr(10).join(items)}

IMPORTANT: Return ONLY valid JSON (no markdown, no explanation).

Output format (array of objects):
[
  {{
    "file": "original filename",
    "canonical_title": "cleaned title",
    "content_type": "main_novel | side_story | fanfic | parody | unknown",
    "noise_removed": ["item1", "item2"],
    "confidence": 0.95,
    "notes": ""
  }}
]
"""
        return prompt

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM with rate limiting."""
        if not self.model:
            logger.error("❌ LLM model not initialized")
            return None

        self._sleep_for_rate_limit()

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"❌ LLM call failed: {e}")
            return None

    def _parse_llm_response(self, response: str) -> Optional[List[Dict]]:
        """
        Parse and validate LLM JSON response.
        Retry once if invalid. Fallback: regex cleanup.
        """
        if not response:
            return None

        # Try to extract JSON from response
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            logger.warning("⚠️ No JSON array found in LLM response")
            return None

        json_str = json_match.group(0)

        # Attempt 1: Parse as-is
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

        # Attempt 2: Fix common JSON issues
        try:
            json_str = json_str.replace("'", '"')
            data = json.loads(json_str)
            if isinstance(data, list):
                logger.info("✅ Fixed JSON quotes issue")
                return data
        except json.JSONDecodeError:
            pass

        logger.error("❌ Failed to parse LLM JSON (both attempts)")
        return None

    def _regex_fallback_cleanup(self, filename: str) -> Dict:
        """
        Fallback: regex-only cleanup if LLM fails.
        No confidence guarantees.
        """
        name = re.sub(r'\.epub$', '', filename, flags=re.IGNORECASE)

        # Remove brackets
        name = re.sub(r'\[.*?\]', '', name)
        name = re.sub(r'\(.*?\)', '', name)

        # Remove common junk
        for token in self.JUNK_TOKENS:
            name = re.sub(rf'\b{re.escape(token)}\b', '', name, flags=re.IGNORECASE)

        # Remove chapter indicators
        name = re.sub(r'\b(?:ch|vol|c)\d+\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\b(?:chapter|volume)\s*\d+\b', '', name, flags=re.IGNORECASE)

        # Clean whitespace
        name = ' '.join(name.split())

        # Classify content type
        name_lower = name.lower()
        if any(kw in name_lower for kw in self.PARODY_KEYWORDS):
            content_type = "parody"
        elif any(kw in name_lower for kw in self.SIDE_STORY_KEYWORDS):
            content_type = "side_story"
        elif any(kw in name_lower for kw in self.FANFIC_KEYWORDS):
            content_type = "fanfic"
        else:
            content_type = "main_novel" if name.strip() else "unknown"

        return {
            "file": filename,
            "canonical_title": name if name.strip() else "unknown",
            "content_type": content_type,
            "noise_removed": [],
            "confidence": 0.3,
            "notes": "Regex fallback (LLM unavailable)"
        }

    def _validate_output_schema(self, item: Dict) -> bool:
        """Validate output matches required schema."""
        required_fields = {
            "file", "canonical_title", "content_type",
            "noise_removed", "confidence", "notes"
        }
        return required_fields.issubset(item.keys())

    def _enrich_with_metadata(self, items: List[Dict]) -> List[Dict]:
        """Add confidence flags and low_trust markers."""
        enriched = []
        for item in items:
            # Mark low confidence
            if item.get("confidence", 1.0) < 0.7:
                item["trust_level"] = "low_trust"
            else:
                item["trust_level"] = "high_trust"

            # Ensure canonical_title is not empty
            if not item.get("canonical_title") or item["canonical_title"].lower() == "unknown":
                item["trust_level"] = "low_trust"

            enriched.append(item)

        return enriched

    def normalize_filenames(self, filenames: List[str]) -> List[Dict]:
        """
        Main entry point: normalize list of EPUB filenames.

        Args:
            filenames: List of EPUB filenames

        Returns:
            List of normalized metadata dicts with schema:
            {
              "original_filename": str,
              "canonical_title": str,
              "content_type": str,
              "noise_removed": list,
              "confidence": float,
              "notes": str,
              "trust_level": str
            }
        """
        if not filenames:
            return []

        # LAZY INIT: Initialize AI model only when normalization is actually called
        if self._genai is None:
            self._init_ai_model()
        
        if not self.model:
            logger.warning("AI model not available - normalization unavailable")
            return []

        logger.info(f"📝 Normalizing {len(filenames)} filenames...")

        # Call LLM for normalization
        prompt = self._build_normalization_prompt(filenames)
        llm_response = self._call_llm(prompt)

        # Parse response
        parsed = None
        if llm_response:
            parsed = self._parse_llm_response(llm_response)

        results = []

        if parsed and isinstance(parsed, list):
            # LLM succeeded
            for idx, filename in enumerate(filenames):
                if idx < len(parsed):
                    item = parsed[idx]
                    # Validate and fix schema
                    if not self._validate_output_schema(item):
                        item = self._regex_fallback_cleanup(filename)
                    else:
                        item["file"] = filename
                else:
                    # Extra filenames not in LLM response
                    item = self._regex_fallback_cleanup(filename)

                results.append(item)
        else:
            # LLM failed: use regex fallback for all
            logger.warning("⚠️ LLM normalization failed, using regex fallback")
            for filename in filenames:
                results.append(self._regex_fallback_cleanup(filename))

        # Standardize field names
        standardized = []
        for item in results:
            standardized.append({
                "original_filename": item.get("file", ""),
                "canonical_title": item.get("canonical_title", "unknown"),
                "content_type": item.get("content_type", "unknown"),
                "noise_removed": item.get("noise_removed", []),
                "confidence": float(item.get("confidence", 0.0)),
                "notes": item.get("notes", "")
            })

        # Enrich with trust levels
        final = self._enrich_with_metadata(standardized)

        logger.info(f"✅ Normalized {len(final)} filenames")
        return final
