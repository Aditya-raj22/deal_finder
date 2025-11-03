"""Web scraping utilities with rate limiting and robots.txt compliance."""

import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from tenacity import retry, stop_after_attempt, wait_exponential


class RateLimiter:
    """Simple rate limiter per domain."""

    def __init__(self, requests_per_minute: int = 15):
        self.requests_per_minute = requests_per_minute
        self.domain_timestamps: dict[str, list[float]] = defaultdict(list)

    def wait_if_needed(self, domain: str) -> None:
        """Wait if rate limit would be exceeded."""
        now = time.time()
        window_start = now - 60  # 1 minute window

        # Clean old timestamps
        self.domain_timestamps[domain] = [
            ts for ts in self.domain_timestamps[domain] if ts > window_start
        ]

        # Check if we need to wait
        if len(self.domain_timestamps[domain]) >= self.requests_per_minute:
            oldest_timestamp = self.domain_timestamps[domain][0]
            sleep_time = 60 - (now - oldest_timestamp)
            if sleep_time > 0:
                time.sleep(sleep_time)
                now = time.time()

        # Record this request
        self.domain_timestamps[domain].append(now)


class RobotsTxtChecker:
    """Check robots.txt compliance."""

    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self.parsers: dict[str, RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self.parsers:
            parser = RobotFileParser()
            parser.set_url(f"{domain}/robots.txt")
            try:
                parser.read()
                self.parsers[domain] = parser
            except Exception:
                # If robots.txt can't be read, assume allowed
                return True

        return self.parsers[domain].can_fetch(self.user_agent, url)


class WebClient:
    """Web client with rate limiting, robots.txt compliance, and retries."""

    def __init__(
        self,
        user_agent: str,
        rate_limit_per_min: int = 15,
        timeout: int = 20,
        max_retries: int = 3,
        backoff_factor: int = 2,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self.rate_limiter = RateLimiter(rate_limit_per_min)
        self.robots_checker = RobotsTxtChecker(user_agent)

        self.session = requests.Session()
        # Use realistic browser headers to avoid bot detection
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })

    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def fetch(self, url: str, respect_robots: bool = True) -> Optional[requests.Response]:
        """Fetch URL with rate limiting and robots.txt compliance."""
        # Check robots.txt
        if respect_robots and not self.robots_checker.can_fetch(url):
            return None

        # Rate limit
        domain = self.get_domain(url)
        self.rate_limiter.wait_if_needed(domain)

        # Fetch
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            # Log error
            print(f"Error fetching {url}: {e}")
            raise

    def fetch_safe(self, url: str, respect_robots: bool = True) -> Optional[requests.Response]:
        """Fetch URL, returning None on error instead of raising."""
        try:
            return self.fetch(url, respect_robots)
        except Exception:
            return None
