"""Hybrid web client using cloudscraper and Selenium."""

import time
from typing import Optional
import logging

import cloudscraper
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


class SeleniumWebClient:
    """Hybrid web client: tries cloudscraper first, falls back to Selenium."""

    def __init__(self, headless: bool = True, timeout: int = 20):
        self.headless = headless
        self.timeout = timeout
        self.driver = None
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True
            }
        )

    def _get_driver(self):
        """Get or create Chrome driver with error handling."""
        if self.driver is None:
            try:
                options = Options()
                if self.headless:
                    options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)
                options.add_argument("--window-size=1920,1080")
                # Add a realistic user agent
                options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

                # Install and use Chrome driver
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                self.driver.set_page_load_timeout(self.timeout)
                logger.info("ChromeDriver initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize ChromeDriver: {e}")
                self.driver = None
                raise

        return self.driver

    def fetch(self, url: str) -> Optional[str]:
        """Fetch URL and return HTML content.

        Strategy:
        1. Try cloudscraper first (fast, bypasses Cloudflare)
        2. If cloudscraper fails (403 or Cloudflare page), skip Selenium and return None
           (Selenium is too slow and unreliable for production)
        """
        # Try cloudscraper
        try:
            logger.debug(f"Fetching with cloudscraper: {url}")
            response = self.scraper.get(url, timeout=self.timeout)

            # Check if we got actual content
            if response.status_code == 200:
                html = response.text

                # Check if it's a Cloudflare challenge page
                if "cloudflare" in html.lower() and "ray id:" in html.lower() and len(html) < 5000:
                    logger.debug(f"Cloudscraper got Cloudflare challenge for {url}")
                    time.sleep(1)
                    return None
                else:
                    # Success!
                    logger.debug(f"✓ Cloudscraper fetched {len(html)} bytes from {url}")
                    time.sleep(1)  # Rate limit
                    return html
            elif response.status_code == 403:
                # Cloudflare blocking - skip this URL
                logger.debug(f"Cloudscraper blocked (403) for {url}")
                time.sleep(1)
                return None
            else:
                logger.warning(f"Cloudscraper got status {response.status_code} for {url}")
                time.sleep(1)
                return None

        except Exception as e:
            logger.warning(f"Cloudscraper exception for {url}: {e}")
            time.sleep(1)
            return None

    def close(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
