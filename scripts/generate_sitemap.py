#!/usr/bin/env python3
"""
SteadiDay Sitemap Generator
Scans the repo for all HTML pages and blog posts, generates a fresh sitemap.xml.
Designed to run in GitHub Actions after blog posts are generated.
"""

import os
import re
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring, ElementTree
from xml.dom.minidom import parseString

WEBSITE_URL = "https://www.steadiday.com"

# Priority and change frequency settings
PAGE_CONFIG = {
    "index.html": {"priority": "1.0", "changefreq": "weekly"},
    "security.html": {"priority": "0.5", "changefreq": "monthly"},
    "privacy.html": {"priority": "0.3", "changefreq": "monthly"},
    "terms.html": {"priority": "0.3", "changefreq": "monthly"},
    "blog/index.html": {"priority": "0.8", "changefreq": "daily"},
}

# Default config for blog posts
BLOG_POST_CONFIG = {"priority": "0.7", "changefreq": "monthly"}

# Featured/pillar content gets higher priority
PILLAR_POSTS = [
    "best-medication-reminder-apps-seniors.html",
]


def get_lastmod(filepath):
    """Get the last modified date of a file from git or filesystem."""
    try:
        # Try git log first (more accurate for deployed files)
        import subprocess
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", filepath],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:10]  # YYYY-MM-DD
    except Exception:
        pass
    
    # Fall back to filesystem modification time
    if os.path.exists(filepath):
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%d')
    
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def find_all_pages():
    """Find all HTML pages that should be in the sitemap."""
    pages = []
    
    # Top-level pages
    for filename in os.listdir('.'):
        if filename.endswith('.html') and not filename.startswith('_'):
            config = PAGE_CONFIG.get(filename, {"priority": "0.5", "changefreq": "monthly"})
            pages.append({
                "url": f"{WEBSITE_URL}/{filename}" if filename != "index.html" else WEBSITE_URL + "/",
                "lastmod": get_lastmod(filename),
                "changefreq": config["changefreq"],
                "priority": config["priority"],
                "filepath": filename,
            })
    
    # Blog index
    blog_index = "blog/index.html"
    if os.path.exists(blog_index):
        config = PAGE_CONFIG.get(blog_index, {"priority": "0.8", "changefreq": "daily"})
        pages.append({
            "url": f"{WEBSITE_URL}/blog/",
            "lastmod": get_lastmod(blog_index),
            "changefreq": config["changefreq"],
            "priority": config["priority"],
            "filepath": blog_index,
        })
    
    # Blog posts
    blog_dir = "blog"
    if os.path.isdir(blog_dir):
        for filename in sorted(os.listdir(blog_dir), reverse=True):
            if filename.endswith('.html') and filename != 'index.html':
                filepath = os.path.join(blog_dir, filename)
                
                # Pillar content gets higher priority
                is_pillar = filename in PILLAR_POSTS
                config = {"priority": "0.8", "changefreq": "weekly"} if is_pillar else BLOG_POST_CONFIG
                
                pages.append({
                    "url": f"{WEBSITE_URL}/blog/{filename}",
                    "lastmod": get_lastmod(filepath),
                    "changefreq": config["changefreq"],
                    "priority": config["priority"],
                    "filepath": filepath,
                })
    
    return pages


def generate_sitemap(pages):
    """Generate sitemap.xml content."""
    urlset = Element('urlset')
    urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    
    for page in pages:
        url_elem = SubElement(urlset, 'url')
        
        loc = SubElement(url_elem, 'loc')
        loc.text = page['url']
        
        lastmod = SubElement(url_elem, 'lastmod')
        lastmod.text = page['lastmod']
        
        changefreq = SubElement(url_elem, 'changefreq')
        changefreq.text = page['changefreq']
        
        priority = SubElement(url_elem, 'priority')
        priority.text = page['priority']
    
    # Pretty print
    rough_string = tostring(urlset, encoding='unicode')
    reparsed = parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding=None)
    
    # Remove the XML declaration line that minidom adds (we'll add our own)
    lines = pretty_xml.split('\n')
    if lines[0].startswith('<?xml'):
        lines = lines[1:]
    
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines)
    
    return xml_content


def main():
    print("=" * 50)
    print("🗺️  SteadiDay Sitemap Generator")
    print("=" * 50)
    
    pages = find_all_pages()
    print(f"\n📄 Found {len(pages)} pages:")
    for page in pages:
        print(f"   {page['url']} (priority: {page['priority']})")
    
    sitemap_xml = generate_sitemap(pages)
    
    output_path = "sitemap.xml"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(sitemap_xml)
    
    print(f"\n✅ Sitemap written to {output_path}")
    print(f"   Total URLs: {len(pages)}")


if __name__ == "__main__":
    main()
