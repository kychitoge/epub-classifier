"""
Cache Manager
Persistent cache for web search results and AI normalization results.
Reduces redundant API calls and web searches.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages persistent cache for expensive operations"""
    
    def __init__(self, cache_dir: str = ".cache", ttl_days: int = 30):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        
        # Cache files
        self.web_cache_path = self.cache_dir / "web_cache.json"
        self.ai_cache_path = self.cache_dir / "ai_cache.json"
        
        # In-memory cache
        self._web_cache: Dict[str, Dict] = {}
        self._ai_cache: Dict[str, Dict] = {}
        
        self._load_caches()
    
    def _load_caches(self) -> None:
        """Load caches from disk"""
        # Load web cache
        if self.web_cache_path.exists():
            try:
                with open(self.web_cache_path, 'r', encoding='utf-8') as f:
                    self._web_cache = json.load(f)
                logger.info(f"Loaded web cache: {len(self._web_cache)} entries")
            except Exception as e:
                logger.warning(f"Failed to load web cache: {e}")
                self._web_cache = {}
        
        # Load AI cache
        if self.ai_cache_path.exists():
            try:
                with open(self.ai_cache_path, 'r', encoding='utf-8') as f:
                    self._ai_cache = json.load(f)
                logger.info(f"Loaded AI cache: {len(self._ai_cache)} entries")
            except Exception as e:
                logger.warning(f"Failed to load AI cache: {e}")
                self._ai_cache = {}
        
        # Clean expired entries
        self._clean_expired()
    
    def _clean_expired(self) -> None:
        """Remove expired cache entries"""
        cutoff = datetime.now() - timedelta(days=self.ttl_days)
        cutoff_str = cutoff.isoformat()
        
        # Clean web cache
        expired_keys = [
            k for k, v in self._web_cache.items()
            if v.get("cached_at", "") < cutoff_str
        ]
        for k in expired_keys:
            del self._web_cache[k]
        
        # Clean AI cache
        expired_keys = [
            k for k, v in self._ai_cache.items()
            if v.get("cached_at", "") < cutoff_str
        ]
        for k in expired_keys:
            del self._ai_cache[k]
        
        if expired_keys:
            logger.info(f"Cleaned {len(expired_keys)} expired cache entries")
    
    def _make_cache_key(self, text: str) -> str:
        """Generate cache key from text (normalized)"""
        # Normalize: lowercase, strip, remove special chars
        normalized = text.lower().strip()
        # Remove common variations
        normalized = normalized.replace(" ", "_")
        return normalized
    
    def get_web_result(self, title: str) -> Optional[Dict]:
        """
        Get cached web search result.
        
        Args:
            title: Normalized title
        
        Returns:
            Cached result dict or None
        """
        key = self._make_cache_key(title)
        entry = self._web_cache.get(key)
        
        if not entry:
            return None
        
        # Check if expired
        cached_at = datetime.fromisoformat(entry.get("cached_at", ""))
        if datetime.now() - cached_at > timedelta(days=self.ttl_days):
            del self._web_cache[key]
            self._save_web_cache()
            return None
        
        return entry.get("data")
    
    def set_web_result(self, title: str, data: Dict) -> None:
        """Cache web search result"""
        key = self._make_cache_key(title)
        self._web_cache[key] = {
            "data": data,
            "cached_at": datetime.now().isoformat()
        }
        self._save_web_cache()
    
    def get_ai_result(self, filename: str) -> Optional[Dict]:
        """Get cached AI normalization result"""
        key = self._make_cache_key(filename)
        entry = self._ai_cache.get(key)
        
        if not entry:
            return None
        
        # Check if expired
        cached_at = datetime.fromisoformat(entry.get("cached_at", ""))
        if datetime.now() - cached_at > timedelta(days=self.ttl_days):
            del self._ai_cache[key]
            self._save_ai_cache()
            return None
        
        return entry.get("data")
    
    def set_ai_result(self, filename: str, data: Dict) -> None:
        """Cache AI normalization result"""
        key = self._make_cache_key(filename)
        self._ai_cache[key] = {
            "data": data,
            "cached_at": datetime.now().isoformat()
        }
        self._save_ai_cache()
    
    def _save_web_cache(self) -> None:
        """Save web cache to disk (atomic write)"""
        try:
            temp_path = self.web_cache_path.with_suffix(self.web_cache_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._web_cache, f, ensure_ascii=False, indent=2)
            
            if self.web_cache_path.exists():
                self.web_cache_path.unlink()
            temp_path.rename(self.web_cache_path)
        except Exception as e:
            logger.error(f"Failed to save web cache: {e}")
    
    def _save_ai_cache(self) -> None:
        """Save AI cache to disk (atomic write)"""
        try:
            temp_path = self.ai_cache_path.with_suffix(self.ai_cache_path.suffix + '.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._ai_cache, f, ensure_ascii=False, indent=2)
            
            if self.ai_cache_path.exists():
                self.ai_cache_path.unlink()
            temp_path.rename(self.ai_cache_path)
        except Exception as e:
            logger.error(f"Failed to save AI cache: {e}")
    
    def clear_cache(self, cache_type: str = "all") -> None:
        """Clear cache (for testing)"""
        if cache_type in ["all", "web"]:
            self._web_cache = {}
            if self.web_cache_path.exists():
                self.web_cache_path.unlink()
        
        if cache_type in ["all", "ai"]:
            self._ai_cache = {}
            if self.ai_cache_path.exists():
                self.ai_cache_path.unlink()
        
        logger.info(f"Cache cleared: {cache_type}")

