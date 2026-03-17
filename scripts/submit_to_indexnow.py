#!/usr/bin/env python3
"""
SteadiDay — Submit URLs to IndexNow
Notifies Bing, DuckDuckGo, Yandex, and other IndexNow-supporting search engines
about new or updated URLs.

Usage:
    python submit_to_indexnow.py                          # Submit sitemap URLs modified in last 2 days
    python submit_to_indexnow.py --url https://...        # Submit a specific URL
    python submit_to_indexnow.py --all                    # Submit all sitemap URLs

Requires:
    - INDEX_NOW_API_KEY env var
    - API key verification file deployed at site root
"""

import os
import sys
import json
import argparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from xml.etree import ElementTree
from datetime import datetime, timedelta, timezone

HOST = "www.steadiday.com"
SITEMAP_URL = f"https://{HOST}/sitemap.xml"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def get_api_key():
    """Get IndexNow API key from environment."""
    key = os.environ.get("INDEX_NOW_API_KEY")
    if not key:
        print("⚠️  INDEX_NOW_API_KEY not set. Skipping IndexNow submission.")
        sys.exit(0)
    return key


def get_sitemap_urls(days_ago=None):
    """Fetch and parse sitemap.xml, optionally filtering by lastmod date."""
    print(f"📥 Fetching sitemap: {SITEMAP_URL}")
    
    # Try local file first (we're likely running in the repo)
    if os.path.exists("sitemap.xml"):
        print("   Using local sitemap.xml")
        tree = ElementTree.parse("sitemap.xml")
        root = tree.getroot()
    else:
        req = Request(SITEMAP_URL, headers={"User-Agent": "SteadiDay-IndexNow/1.0"})
        response = urlopen(req, timeout=10)
        root = ElementTree.fromstring(response.read())
    
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    
    cutoff_date = None
    if days_ago is not None:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime('%Y-%m-%d')
    
    for url_elem in root.findall("sm:url", ns):
        loc = url_elem.find("sm:loc", ns)
        lastmod = url_elem.find("sm:lastmod", ns)
        
        if loc is not None:
            url = loc.text
            mod_date = lastmod.text if lastmod is not None else None
            
            if cutoff_date and mod_date:
                if mod_date >= cutoff_date:
                    urls.append(url)
            elif cutoff_date is None:
                urls.append(url)
    
    return urls


def submit_urls(api_key, urls):
    """Submit URLs to IndexNow API."""
    if not urls:
        print("ℹ️  No URLs to submit.")
        return
    
    print(f"\n🚀 Submitting {len(urls)} URL(s) to IndexNow...")
    
    key_location = f"https://{HOST}/{api_key}.txt"
    
    payload = {
        "host": HOST,
        "key": api_key,
        "keyLocation": key_location,
        "urlList": urls
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        INDEXNOW_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SteadiDay-IndexNow/1.0"
        },
        method="POST"
    )
    
    try:
        response = urlopen(req, timeout=15)
        status = response.getcode()
        
        if status == 200:
            print("✅ IndexNow accepted all URLs (200 OK)")
        elif status == 202:
            print("✅ IndexNow accepted URLs for processing (202 Accepted)")
        else:
            print(f"ℹ️  IndexNow responded with status {status}")
        
        # Print submitted URLs
        for url in urls:
            print(f"   ✓ {url}")
            
    except HTTPError as e:
        status = e.code
        if status == 422:
            print(f"⚠️  IndexNow rejected URLs (422) — check that {key_location} is accessible")
        elif status == 429:
            print("⚠️  IndexNow rate limited (429) — try again later")
        else:
            print(f"❌ IndexNow error: HTTP {status}")
            print(f"   {e.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"❌ Error submitting to IndexNow: {e}")


def main():
    parser = argparse.ArgumentParser(description="Submit URLs to IndexNow")
    parser.add_argument("--url", help="Submit a specific URL")
    parser.add_argument("--all", action="store_true", help="Submit all sitemap URLs")
    parser.add_argument("--days", type=int, default=2, help="Submit URLs modified in last N days (default: 2)")
    args = parser.parse_args()
    
    print("=" * 50)
    print("📡 SteadiDay IndexNow Submitter")
    print("=" * 50)
    
    api_key = get_api_key()
    
    if args.url:
        urls = [args.url]
        print(f"📌 Submitting specific URL: {args.url}")
    elif args.all:
        urls = get_sitemap_urls(days_ago=None)
        print(f"📌 Submitting ALL {len(urls)} sitemap URLs")
    else:
        urls = get_sitemap_urls(days_ago=args.days)
        print(f"📌 Submitting URLs modified in last {args.days} days: {len(urls)} found")
    
    submit_urls(api_key, urls)
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
