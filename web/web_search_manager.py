import os
import re
import json
import time
import random
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Tuple
from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import ElementNotFoundError, PageDisconnectedError

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === TRUSTED DOMAINS ===
TRUSTED_DOMAINS = [
    "metruyencv.com",
    "metruyenchu.com",
    "wikidich.com",
    "bachngocsach.com.vn",
    "tangthuvien.vn",
    "truyen.tangthuvien.vn",
    "truyenyy.vip",
    "truyenchu.vn",
    "truyenchu.net",
    "truyencv.vn",
]

DOMAIN_NAMES = {
    "metruyencv.com": "Metruyencv",
    "metruyenchu.com": "Metruyenchu",
    "wikidich.com": "WikiDich",
    "bachngocsach.com.vn": "BachNgocSach",
    "tangthuvien.vn": "TangThuVien",
    "truyen.tangthuvien.vn": "TangThuVien",
    "truyenyy.vip": "TruyenYY",
    "truyenchu.vn": "TruyenChu",
    "truyenchu.net": "TruyenChu",
    "truyencv.vn": "TruyenCV",
}

# === DOMAIN CONFIDENCE SCORE (NEW: USED FOR SCORING ONLY) ===
DOMAIN_SCORES = {
    "metruyencv.com": 0.45,
    "metruyenchu.com": 0.45,
    "wikidich.com": 0.40,
    "bachngocsach.com.vn": 0.40,
    "tangthuvien.vn": 0.42,
    "truyen.tangthuvien.vn": 0.42,
    "truyenyy.vip": 0.30,
    "truyenchu.vn": 0.32,
    "truyenchu.net": 0.32,
    "truyencv.vn": 0.30,
}

# === VIETNAMESE NORMALIZATION MAP ===
_VIET_MAP = str.maketrans(
    "àáạảãâầấậẩẫăằắặẳẵ"
    "èéẹẻẽêềếệểễ"
    "ìíịỉĩ"
    "òóọỏõôồốộổỗơờớợởỡ"
    "ùúụủũưừứựửữ"
    "ỳýỵỷỹđ",
    "aaaaaaaaaaaaaaaaa"
    "eeeeeeeeee"
    "iiiii"
    "oooooooooooooooooo"
    "uuuuuuuuuuu"
    "yyyyyd"
)

# === BROWSER CONFIG ===
BROWSER_CONFIG = {
    # Headless có thể giảm RAM nhưng đôi khi dễ bị Google soi hơn
    'headless': os.getenv('HEADLESS', 'false').lower() == 'true',
    'timeout_base': 12,
    'timeout_page_load': 25,
    'max_retries': 3,
    # Số lượt search tối đa cho 1 phiên browser trước khi recycle
    'max_searches_per_session': 25,
    # Backoff khi bị rate limit / CAPTCHA
    'captcha_backoff_base': 60,   # giây
    'captcha_backoff_max': 300,   # giây
    'user_agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}



class CaptchaOrRateLimitError(Exception):
    """Raised when Google blocks or rate-limits the session."""
    pass


class BrowserInitError(Exception):
    """Custom exception for browser initialization failures"""
    pass


class WebSearchManager:
    """Enhanced web search manager with expanded domain support and optimized scoring"""
    
    def __init__(self, config: dict):
        # Merge user config with defaults, user overrides
        merged = dict(BROWSER_CONFIG)
        if config:
            merged.update(config)
        self.config = merged
        self.page: Optional[ChromiumPage] = None
        # Đếm số lượt search để phục vụ browser recycling
        self._search_counter: int = 0
        self._init_browser()

    def _init_browser(self) -> None:
        """
        Initialize browser with optimized configuration.
        Đảm bảo luôn chỉ có 1 instance, tự cleanup trước khi tạo mới.
        """
        # Nếu đang có page cũ, đóng trước để tránh leak process
        if self.page is not None:
            self._cleanup()

        co = ChromiumOptions()
        co.auto_port()

        # Anti-detection & stability
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--disable-gpu')
        co.set_argument('--lang=vi-VN,vi,en-US,en')
        co.set_argument('--disable-software-rasterizer')

        # Memory / resource optimization cho laptop 8GB
        co.set_argument('--disable-extensions')
        co.set_argument('--disable-plugins')
        co.set_argument('--disable-features=Translate,ExtensionsToolbarMenu')
        co.set_argument('--disable-background-networking')
        co.set_argument('--disable-background-timer-throttling')
        co.set_argument('--disable-backgrounding-occluded-windows')
        co.set_argument('--disable-notifications')
        co.set_argument('--disable-default-apps')
        # Tắt tải ảnh để giảm băng thông & RAM
        co.set_argument('--blink-settings=imagesEnabled=false')

        co.set_user_agent(self.config['user_agent'])

        if self.config.get('headless'):
            co.headless()
            logger.info("🔇 Running in headless mode")

        try:
            self.page = ChromiumPage(addr_or_opts=co)
            time.sleep(1.0)

            self.page.get('about:blank', timeout=10)
            time.sleep(0.3)

            if not self.page.url:
                raise BrowserInitError("Browser URL is empty")

            self.page.set.timeouts(
                base=self.config['timeout_base'],
                page_load=self.config['timeout_page_load']
            )

            # Reset counter mỗi lần khởi tạo browser mới
            self._search_counter = 0

            logger.info(f"✅ Browser initialized: {self.page.address}")

        except Exception as e:
            logger.error(f"❌ Browser init failed: {type(e).__name__}: {e}")
            self._cleanup()
            raise BrowserInitError(f"Failed to initialize browser: {e}")

    def _cleanup(self) -> None:
        """Safe cleanup of browser resources"""
        if self.page:
            try:
                self.page.quit()
            except Exception as e:
                logger.warning(f"Cleanup warning: {e}")
            finally:
                self.page = None

    def close(self) -> None:
        """Public method to close browser"""
        self._cleanup()
        logger.info("🔒 Browser closed")

    def recycle_browser(self) -> None:
        """
        Force recycle browser instance to free RAM triệt để.
        Dùng khi search_counter chạm ngưỡng hoặc khi gặp lỗi nặng.
        """
        logger.info("♻️ Recycling browser instance to free memory...")
        self._cleanup()
        # Nghỉ 1 chút để OS thu hồi tài nguyên
        time.sleep(1.0)
        self._init_browser()

    def _should_recycle(self) -> bool:
        """Check if browser should be recycled based on search counter."""
        max_per_session = int(self.config.get('max_searches_per_session', 25))
        return self._search_counter >= max_per_session

    def _health_check(self) -> bool:
        """Verify browser is still responsive"""
        try:
            if not self.page:
                return False
            _ = self.page.url
            return True
        except Exception:
            return False

    def _navigate(self, url: str, max_retries: int = 3) -> bool:
        """Navigate with exponential backoff retry"""
        for attempt in range(max_retries):
            try:
                if not self._health_check():
                    logger.error("❌ Browser health check failed")
                    return False
                
                logger.info(f"🔗 Navigating to: {url[:70]}... (attempt {attempt + 1})")
                
                self.page.get(url, timeout=18)
                time.sleep(1.2)
                
                if self.page.url and self.page.url.startswith('http'):
                    logger.info(f"✅ Navigation successful")
                    return True
                else:
                    logger.warning(f"⚠️ Invalid URL after navigation: {self.page.url}")
                    
            except PageDisconnectedError:
                logger.error("🔌 Browser disconnected, reinitializing...")
                self._init_browser()
                
            except Exception as e:
                logger.warning(f"⚠️ Navigation attempt {attempt + 1} failed: {e}")
                
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                logger.info(f"⏳ Retrying in {delay}s...")
                time.sleep(delay)
        
        logger.error(f"❌ Navigation failed after {max_retries} attempts")
        return False

    @contextmanager
    def _safe_page_context(self):
        """Context manager for safe page operations"""
        try:
            yield self.page
        except ElementNotFoundError as e:
            logger.warning(f"⚠️ Element not found: {e}")
        except Exception as e:
            logger.error(f"❌ Page operation error: {type(e).__name__}: {e}")

    def _get_page_text(self, page) -> str:
        """Extract page text with multiple fallback strategies and logging"""
        try:
            body = page.ele('tag:body', timeout=2)
            if body and body.text and len(body.text) > 100:
                logger.debug("🧠 Text strategy: BODY")
                return body.text
        except Exception:
            pass

        try:
            paragraphs = page.eles('tag:p')
            text = '\n'.join(p.text for p in paragraphs if p.text)
            if len(text) > 100:
                logger.debug("🧠 Text strategy: PARAGRAPHS")
                return text
        except Exception:
            pass

        selectors = [
            '.content', '#content', '.post-content',
            '.article-content', '.main-content', '.story-content'
        ]
        for sel in selectors:
            try:
                el = page.ele(sel, timeout=1)
                if el and el.text and len(el.text) > 100:
                    logger.debug(f"🧠 Text strategy: {sel}")
                    return el.text
            except Exception:
                continue

        try:
            html = page.html
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            logger.debug("🧠 Text strategy: HTML_STRIP")
            return text
        except Exception as e:
            logger.error(f"❌ Failed to get page text: {e}")
            return ""

    def _normalize_text(self, text: str) -> str:
        """Vietnamese text normalization (Optimized with maketrans)"""
        if not text:
            return ""
        text = text.lower().translate(_VIET_MAP)
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _random_delay(self, min_sec: float = 1.0, max_sec: float = 2.5) -> None:
        """Human-like delay"""
        time.sleep(random.uniform(min_sec, max_sec))

    def _detect_captcha(self) -> None:
        """
        Detect CAPTCHA / rate limit page.

        Trong chế độ batch không tương tác, ta không chờ input()
        mà raise CaptchaOrRateLimitError để tầng trên xử lý backoff.
        """
        try:
            time.sleep(0.5)
            if not self.page:
                return
            page_text = (self.page.html or "").lower()

            captcha_keywords = ['captcha', 'unusual traffic', 'not a robot', 'recaptcha']
            if any(kw in page_text for kw in captcha_keywords):
                logger.warning("🚨 CAPTCHA / RATE LIMIT DETECTED!")
                raise CaptchaOrRateLimitError("Google CAPTCHA or rate limit page detected.")
        except CaptchaOrRateLimitError:
            # Propagate để tầng gọi xử lý backoff
            raise
        except Exception as e:
            logger.warning(f"⚠️ CAPTCHA check error: {e}")

    def _search_google(self, query: str) -> List[Dict[str, str]]:
        """
        Enhanced Google search với quản lý backoff khi bị chặn.
        Trả về [] nếu thất bại sau max_retries.
        """
        attempts = 0
        max_retries = int(self.config.get('max_retries', 3))

        while attempts < max_retries:
            attempts += 1
            try:
                logger.info(f"🔍 Searching: {query} (attempt {attempts}/{max_retries})")

                if not self._navigate("https://www.google.com/"):
                    continue

                self._random_delay(1.0, 1.5)
                self._detect_captcha()

                with self._safe_page_context() as page:
                    # Find search box
                    search_box = (
                        page.ele('@name=q', timeout=5) or
                        page.ele('textarea[name="q"]', timeout=2) or
                        page.ele('input[name="q"]', timeout=2)
                    )

                    if not search_box:
                        logger.error("❌ Search box not found")
                        return []

                    # Input search query
                    search_box.clear()
                    time.sleep(0.2)
                    search_box.input(query)
                    time.sleep(0.3)
                    search_box.input('\n')

                    # Wait for results
                    try:
                        page.wait.url_change(timeout=8)
                        page.wait.ele_displayed('#search', timeout=8)
                    except Exception:
                        logger.warning("⚠️ Timeout waiting for results")

                    self._random_delay(1.5, 2.0)
                    self._detect_captcha()

                    # Extract results
                    results = []
                    seen_urls = set()

                    # Strategy 1: Result containers
                    search_divs = page.eles('.g') or page.eles('[data-sokoban-container]')

                    if search_divs:
                        logger.info(f"📦 Found {len(search_divs)} result containers")
                        for div in search_divs[:20]:
                            try:
                                link = div.ele('tag:a', timeout=1)
                                if not link:
                                    continue

                                href = link.link
                                h3 = div.ele('tag:h3', timeout=1)
                                text = h3.text if h3 else link.text

                                if not href or not href.startswith('http'):
                                    continue

                                if any(d in href for d in ['google.com', 'webcache', 'translate.google']):
                                    continue

                                if not text or len(text.strip()) < 5:
                                    continue

                                if href in seen_urls:
                                    continue

                                seen_urls.add(href)
                                results.append({"url": href, "title": text.strip()})

                                logger.info(f"  ✓ [{len(results)}] {text[:50]}...")

                                if len(results) >= 15:
                                    break

                            except Exception:
                                continue

                    # Strategy 2: Fallback to all links
                    if len(results) < 5:
                        logger.info("📎 Fallback: scanning all links")
                        for link in page.eles('tag:a')[:60]:
                            try:
                                href = link.link
                                text = link.text

                                if not href or not href.startswith('http'):
                                    continue

                                if any(d in href for d in ['google.com', 'webcache', 'translate']):
                                    continue

                                if not text or len(text.strip()) < 10:
                                    continue

                                if href in seen_urls:
                                    continue

                                seen_urls.add(href)
                                results.append({"url": href, "title": text.strip()})

                                if len(results) >= 15:
                                    break

                            except Exception:
                                continue

                    logger.info(f"✅ Found {len(results)} results")
                    # Tăng counter và xem có cần recycle không
                    self._search_counter += 1
                    if self._should_recycle():
                        # Recycle sau khi trả kết quả để lần gọi tiếp theo dùng browser mới
                        logger.info(
                            f"♻️ Max searches per session reached "
                            f"({self._search_counter}), scheduling recycle."
                        )
                        # Recycle async-style: làm ngay để tránh giữ phiên cũ
                        self.recycle_browser()
                    return results

            except CaptchaOrRateLimitError as e:
                # CAPTCHA is not transient - don't retry, propagate immediately
                logger.warning(f"🚧 {e} – not retrying (CAPTCHA is session-wide)")
                # Recycle browser before propagating (cleanup)
                self.recycle_browser()
                # Propagate to caller for global flag handling
                raise
            except Exception as e:
                logger.error(f"❌ Search error: {type(e).__name__}: {e}")
                # Thử lại nếu còn lượt, có delay nhẹ để tránh spam
                if attempts < max_retries:
                    delay = 2 * attempts
                    logger.info(f"⏳ Retrying search in {delay}s...")
                    time.sleep(delay)

        logger.error("❌ Google search failed after max retries.")
        return []

    def _fetch_page(self, url: str) -> Optional[Dict[str, str]]:
        """Fetch page content with proper text extraction"""
        for attempt in range(2):
            try:
                if not self._navigate(url):
                    continue
                
                try:
                    self.page.wait.ele_displayed('tag:body', timeout=8)
                except Exception:
                    pass
                
                self._random_delay(1.0, 1.5)
                
                # Get page text (Uses optimized _get_page_text)
                page_text = self._get_page_text(self.page)
                
                # Get title
                try:
                    title = self.page.title
                except Exception:
                    title = ""
                
                # Get h1
                h1_text = ""
                try:
                    h1_elem = self.page.ele('tag:h1', timeout=3)
                    if h1_elem:
                        h1_text = h1_elem.text or ""
                except Exception:
                    pass
                
                return {
                    "text": page_text,
                    "title": title,
                    "h1": h1_text
                }
                    
            except Exception as e:
                logger.warning(f"⚠️ Fetch attempt {attempt + 1} failed: {e}")
                if attempt == 1:
                    return None
                time.sleep(2)
        
        return None

    def _parse_metadata(self, page_data: Dict[str, str], url: str) -> Optional[Dict[str, any]]:
        """Extract book metadata with enhanced parsing"""
        if not page_data:
            return None
        
        text = page_data['text']
        
        if not text or len(text) < 100:
            logger.warning(f"⚠️ Page text too short: {len(text)} chars")
            return None
        
        # Title extraction
        title = page_data['h1'] or page_data['title']
        # Clean title
        title = re.sub(r'\s*[-–—|]\s*.*$', '', title)
        title = re.sub(r'\s*\[.*?\]\s*', '', title)
        title = re.sub(r'\s*\(.*?\)\s*', '', title)
        title = title.strip()
        
        # Author extraction
        author = "Unknown"
        author_patterns = [
            r'Tác\s+giả\s*[:|\-]?\s*([^\n\r]{2,50})',
            r'Author\s*[:|\-]?\s*([^\n\r]{2,50})',
            r'Người\s+viết\s*[:|\-]?\s*([^\n\r]{2,50})',
            r'By\s+([^\n\r]{2,50})',
        ]
        
        for pattern in author_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                clean = re.sub(r'[^\w\s\u00C0-\u1EF9]', '', raw)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if 2 < len(clean) < 50:
                    author = clean
                    break
        
        # Status detection
        status = "DangRa"
        status_keywords = {
            "Full": ["full", "hoàn thành", "đã hoàn thành", "hoàn tất", "hết"],
            "DangRa": ["đang ra", "đang cập nhật", "updating", "chưa hoàn thành"]
        }
        
        text_lower = text.lower()
        for stat, keywords in status_keywords.items():
            if any(kw in text_lower for kw in keywords):
                status = stat
                break
        
        # Chapter extraction
        chapters = 0
        chapter_nums = re.findall(r'(?:Chương|Chapter)\s+(\d+)', text, re.IGNORECASE)
        if chapter_nums:
            nums = [int(x) for x in chapter_nums if int(x) < 10000]
            chapters = max(nums) if nums else 0
        
        # Detect domain
        source = "Unknown"
        for domain in TRUSTED_DOMAINS:
            if domain in url.lower():
                source = DOMAIN_NAMES.get(domain, domain)
                break
        
        logger.info(f"📄 Parsed: title={title[:30]}, author={author}, chapters={chapters}, source={source}")
        
        return {
            "web_title": title,
            "web_author": author,
            "web_status": status,
            "web_chapters": chapters,
            "web_source": source,
            "web_url": url
        }

    def _calculate_match_score(self, clean_title: str, result: Dict[str, str]) -> float:
        """
        Enhanced scoring algorithm using DOMAIN_SCORES
        Returns score from 0.0 to 1.0
        """
        score = 0.0
        url = result['url'].lower()
        title = result['title']

        # --- DOMAIN SCORE ---
        domain_score = 0.0
        for domain, d_score in DOMAIN_SCORES.items():
            if domain in url:
                domain_score = d_score
                break
        score += domain_score

        # --- TITLE MATCH ---
        norm_title = self._normalize_text(clean_title)
        norm_web = self._normalize_text(title)

        stop_words = {'truyen', 'chuong', 'tap', 'full', 'doc', 'net', 'vn'}
        t_words = set(norm_title.split()) - stop_words
        w_words = set(norm_web.split()) - stop_words

        if t_words and w_words:
            overlap = len(t_words & w_words)
            score += (overlap / max(len(t_words), len(w_words))) * 0.35

            if norm_title == norm_web:
                score += 0.10
            elif norm_title in norm_web or norm_web in norm_title:
                score += 0.07

        # --- PENALTIES ---
        bad_keywords = ['dong nhan', 'fanfic', 'review', 'cam nhan']
        if any(k in norm_web for k in bad_keywords):
            score *= 0.25

        if len(norm_web) > len(norm_title) * 3:
            score *= 0.6

        if domain_score == 0:
            score *= 0.5

        # --- URL BONUS ---
        slug = norm_title.replace(' ', '-')
        if slug in url or norm_title.replace(' ', '') in url:
            score += 0.08

        return round(min(score, 1.0), 4)

    def search_book(self, clean_title: str) -> Optional[Dict[str, any]]:
        """
        Main entry point - Search for book with enhanced algorithm.

        Đảm bảo:
        - Kiểm tra input
        - Sử dụng _search_google (có backoff & recycle)
        """
        try:
            if not clean_title or len(clean_title.strip()) < 2:
                logger.error("❌ Invalid title")
                return None

            clean_title = clean_title.strip()
            logger.info(f"🚀 Searching: {clean_title}")

            # Search Google
            query = f"{clean_title} truyện"
            results = self._search_google(query)

            if not results:
                logger.warning("⚠️ No search results found")
                return None

            # Score all results
            scored_results: List[Tuple[float, Dict[str, str]]] = []
            for r in results:
                score = self._calculate_match_score(clean_title, r)
                scored_results.append((score, r))

            # Sort by score descending
            scored_results.sort(key=lambda x: x[0], reverse=True)

            # Log top results
            logger.info(f"📊 Top 5 scores: {[f'{s:.2f}' for s, _ in scored_results[:5]]}")

            # Filter by threshold (lowered to 0.20)
            threshold = 0.20
            matches = [r for score, r in scored_results if score >= threshold]

            if not matches:
                logger.warning(f"⚠️ No matches above threshold {threshold}")
                if scored_results:
                    logger.info(f"💡 Best score was: {scored_results[0][0]:.2f}")
                return None

            logger.info(f"✅ Found {len(matches)} potential matches")

            # Try top 5 matches
            max_attempts = min(5, len(matches))
            for idx, match in enumerate(matches[:max_attempts], 1):
                logger.info(f"📖 Trying {idx}/{max_attempts}: {match['url'][:70]}...")

                page_data = self._fetch_page(match['url'])
                if not page_data:
                    logger.warning(f"⚠️ Failed to fetch page {idx}")
                    continue

                metadata = self._parse_metadata(page_data, match['url'])
                if metadata:
                    logger.info(f"✅ SUCCESS: {metadata['web_title']}")
                    return metadata
                else:
                    logger.warning(f"⚠️ Failed to parse metadata {idx}")

            logger.warning(f"⚠️ Could not parse any of {max_attempts} matches")
            return None

        except Exception as e:
            logger.error(f"❌ Search failed: {type(e).__name__}: {e}")
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


