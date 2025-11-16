#!/usr/bin/env python3
"""
Extract STAT+ authentication cookies from your browser for use with the crawler.

IMPORTANT: You need a STAT+ subscription to access premium content.

Usage:
    1. Log in to STAT+ in your browser (Chrome/Firefox)
    2. Run this script to extract your session cookies
    3. Save the output to config/stat_cookies.json
    4. The crawler will automatically use these cookies

For Chrome:
    python extract_stat_cookies.py --browser chrome

For Firefox:
    python extract_stat_cookies.py --browser firefox

Manual Method:
    If this script doesn't work, extract cookies manually:
    1. Log in to https://www.statnews.com
    2. Open DevTools (F12) -> Application/Storage -> Cookies
    3. Copy cookies for .statnews.com domain
    4. Create config/stat_cookies.json with this format:
       {
         "STAT": [
           {
             "name": "cookie_name",
             "value": "cookie_value",
             "domain": ".statnews.com",
             "path": "/",
             "secure": true,
             "httpOnly": true
           }
         ]
       }
"""

import argparse
import json
import sqlite3
import os
from pathlib import Path


def extract_chrome_cookies():
    """Extract STAT cookies from Chrome."""
    # Chrome cookie database paths
    if os.name == 'nt':  # Windows
        cookie_path = Path.home() / 'AppData' / 'Local' / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Cookies'
    elif os.name == 'posix':  # macOS/Linux
        if Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome':  # macOS
            cookie_path = Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome' / 'Default' / 'Cookies'
        else:  # Linux
            cookie_path = Path.home() / '.config' / 'google-chrome' / 'Default' / 'Cookies'
    else:
        print("Unsupported OS")
        return []

    if not cookie_path.exists():
        print(f"Chrome cookie database not found at {cookie_path}")
        print("Make sure Chrome is installed and you've logged into STAT+")
        return []

    # Copy the database (Chrome locks it while running)
    import shutil
    temp_db = Path('/tmp/chrome_cookies_temp.db')
    try:
        shutil.copy2(cookie_path, temp_db)
    except PermissionError:
        print("ERROR: Close Chrome before running this script")
        return []

    # Query cookies
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Chrome cookie schema
    cursor.execute("""
        SELECT name, value, host_key, path, is_secure, is_httponly
        FROM cookies
        WHERE host_key LIKE '%statnews.com%'
    """)

    cookies = []
    for row in cursor.fetchall():
        name, value, domain, path, secure, httponly = row
        cookies.append({
            'name': name,
            'value': value,
            'domain': domain,
            'path': path,
            'secure': bool(secure),
            'httpOnly': bool(httponly)
        })

    conn.close()
    temp_db.unlink()

    return cookies


def extract_firefox_cookies():
    """Extract STAT cookies from Firefox."""
    if os.name == 'nt':  # Windows
        firefox_dir = Path.home() / 'AppData' / 'Roaming' / 'Mozilla' / 'Firefox' / 'Profiles'
    else:  # macOS/Linux
        firefox_dir = Path.home() / 'Library' / 'Application Support' / 'Firefox' / 'Profiles'

    if not firefox_dir.exists():
        print(f"Firefox profile directory not found at {firefox_dir}")
        return []

    # Find the default profile
    profiles = list(firefox_dir.glob('*.default*'))
    if not profiles:
        print("No Firefox profile found")
        return []

    cookie_path = profiles[0] / 'cookies.sqlite'
    if not cookie_path.exists():
        print(f"Firefox cookie database not found at {cookie_path}")
        return []

    # Copy the database
    import shutil
    temp_db = Path('/tmp/firefox_cookies_temp.db')
    try:
        shutil.copy2(cookie_path, temp_db)
    except PermissionError:
        print("ERROR: Close Firefox before running this script")
        return []

    # Query cookies
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, value, host, path, isSecure, isHttpOnly
        FROM moz_cookies
        WHERE host LIKE '%statnews.com%'
    """)

    cookies = []
    for row in cursor.fetchall():
        name, value, domain, path, secure, httponly = row
        cookies.append({
            'name': name,
            'value': value,
            'domain': domain,
            'path': path,
            'secure': bool(secure),
            'httpOnly': bool(httponly)
        })

    conn.close()
    temp_db.unlink()

    return cookies


def main():
    parser = argparse.ArgumentParser(description='Extract STAT+ cookies from browser')
    parser.add_argument('--browser', choices=['chrome', 'firefox'], default='chrome',
                       help='Browser to extract cookies from (default: chrome)')
    args = parser.parse_args()

    print(f"Extracting STAT+ cookies from {args.browser.title()}...")
    print()

    if args.browser == 'chrome':
        cookies = extract_chrome_cookies()
    else:
        cookies = extract_firefox_cookies()

    if not cookies:
        print("❌ No STAT cookies found")
        print()
        print("Make sure you:")
        print("  1. Have logged into STAT+ in your browser")
        print("  2. Have closed the browser before running this script")
        print("  3. Have an active STAT+ subscription")
        return

    print(f"✅ Found {len(cookies)} STAT cookies")
    print()

    # Format for crawler
    cookie_config = {
        'STAT': cookies
    }

    # Save to file
    output_path = Path('config/stat_cookies.json')
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(cookie_config, f, indent=2)

    print(f"✅ Saved cookies to {output_path}")
    print()
    print("Cookie names found:")
    for cookie in cookies:
        print(f"  - {cookie['name']}")
    print()
    print("Next steps:")
    print("  1. Update step2_run_pipeline.py to load these cookies")
    print("  2. Run the crawler - it will now access STAT+ content")


if __name__ == '__main__':
    main()
