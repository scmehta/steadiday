#!/usr/bin/env python3
"""
Rebuild blog/index.html from actual post files on disk.
Fixes: missing thumbnails, 404 entries for deleted posts, broken image URLs.

Usage:
  python scripts/rebuild_blog_index.py           # Dry run
  python scripts/rebuild_blog_index.py --apply   # Overwrite index.html
"""
import os, re, sys, glob

BLOG_DIR = "blog"
INDEX_PATH = os.path.join(BLOG_DIR, "index.html")
WEBSITE_URL = "https://www.steadiday.com"
APP_STORE_URL = "https://apps.apple.com/app/steadiday/id6758526744"

# One safe, verified thumbnail per category (manually checked April 2026)
SAFE_THUMBNAILS = {
    "Mental Wellness":    "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80",
    "Medication Tips":    "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&q=80",
    "Healthy Aging":      "https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=800&q=80",
    "Exercise":           "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80",
    "Nutrition":          "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80",
    "Sleep":              "https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=800&q=80",
    "Heart Health":       "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80",
    "Brain Health":       "https://images.unsplash.com/photo-1559757175-5700dde675bc?w=800&q=80",
    "Safety":             "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80",
    "Wellness":           "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80",
    "Technology":         "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&q=80",
    "Chronic Conditions": "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80",
    "Relationships":      "https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=800&q=80",
    "Women's Health":     "https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80",
    "Men's Health":       "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80",
    "Preventive Care":    "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80",
    "Comparison":         "https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80",
}

def scan_posts():
    """Read all blog post HTML files and extract metadata."""
    posts = []
    for filepath in glob.glob(os.path.join(BLOG_DIR, "*.html")):
        filename = os.path.basename(filepath)
        if filename == "index.html":
            continue
        try:
            if os.path.getsize(filepath) < 1024:
                continue
        except OSError:
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(8000)

        title = ""
        m = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
        if m:
            title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not title:
            m2 = re.search(r'<title>(.*?)[\|<]', content)
            if m2:
                title = m2.group(1).strip()

        category = ""
        # Try to get from blog-card-tag (if present from old index injection)
        cat_m = re.search(r'class="blog-card-tag">([^<]+)<', content)
        if cat_m:
            category = cat_m.group(1).strip()
        # Also try from the article header area
        if not category:
            # Check meta keywords for category hints
            kw_m = re.search(r'<meta\s+name="keywords"\s+content="([^"]*)"', content)
            if kw_m:
                kws = kw_m.group(1).lower()
                for cat in SAFE_THUMBNAILS:
                    if cat.lower().replace("'", "") in kws:
                        category = cat
                        break
        if not category:
            category = "Wellness"

        meta_desc = ""
        desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', content)
        if desc_m:
            meta_desc = desc_m.group(1).strip()

        read_time = "7"
        rt_m = re.search(r'(\d+)\s*min\s*read', content)
        if rt_m:
            read_time = rt_m.group(1)

        date_str = ""
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', filename)
        if date_match:
            date_str = date_match.group(1)

        # Check if this is the featured comparison guide
        is_featured = "best-medication-reminder" in filename

        posts.append({
            "filename": filename,
            "title": title,
            "category": category,
            "meta_desc": meta_desc,
            "read_time": read_time,
            "date": date_str,
            "is_featured": is_featured,
        })

    # Sort by date descending, featured items go to end
    posts.sort(key=lambda p: (not p["is_featured"], p.get("date", "")), reverse=True)
    return posts


def format_date(date_str):
    """Convert 2026-04-20 to April 20, 2026."""
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return d.strftime('%B %d, %Y')
    except:
        return date_str


def build_card(post, is_first=False):
    """Generate HTML for a single blog card."""
    cat = post["category"]
    thumb = SAFE_THUMBNAILS.get(cat, SAFE_THUMBNAILS["Wellness"])
    date_display = format_date(post["date"]) if post["date"] else ""
    featured_class = ' featured' if is_first else ''

    if post["is_featured"]:
        return f'''            <article class="blog-card">
                <div class="blog-card-image" style="background-image: url('{thumb}');"><span class="blog-card-tag">{cat}</span><span class="blog-card-tag featured-tag">Featured Guide</span></div>
                <div class="blog-card-content">
                    <h2><a href="{post['filename']}">{post['title']}</a></h2>
                    <div class="blog-meta"><span>{date_display}</span><span>*</span><span>{post['read_time']} min read</span></div>
                    <p class="blog-excerpt">{post['meta_desc']}</p>
                    <a href="{post['filename']}" class="read-more">Read full guide<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg></a>
                </div></article>
'''

    return f'''            <article class="blog-card{featured_class}">
                <div class="blog-card-image" style="background-image: url('{thumb}');"><span class="blog-card-tag">{cat}</span></div>
                <div class="blog-card-content">
                    <h2><a href="{post['filename']}">{post['title']}</a></h2>
                    <div class="blog-meta"><span>{date_display}</span><span>*</span><span>{post['read_time']} min read</span></div>
                    <p class="blog-excerpt">{post['meta_desc']}</p>
                    <a href="{post['filename']}" class="read-more">Read full article<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg></a>
                </div></article>
'''


def rebuild_index(posts):
    """Replace the blog entries section in index.html."""
    if not os.path.exists(INDEX_PATH):
        print(f"ERROR: {INDEX_PATH} not found")
        sys.exit(1)

    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    start_marker = "<!--BLOG_ENTRIES_START-->"
    end_marker = "<!--BLOG_ENTRIES_END-->"

    start_pos = html.find(start_marker)
    end_pos = html.find(end_marker)

    if start_pos == -1:
        print("ERROR: <!--BLOG_ENTRIES_START--> marker not found in index.html")
        sys.exit(1)

    # Build new entries
    cards = []
    for i, post in enumerate(posts):
        cards.append(build_card(post, is_first=(i == 0)))

    new_entries = "\n".join(cards)

    if end_pos != -1:
        # Replace between markers
        html = html[:start_pos + len(start_marker)] + "\n" + new_entries + "\n            " + html[end_pos:]
    else:
        # No end marker — inject after start and hope for the best
        # Find the next major section after entries
        html = html[:start_pos + len(start_marker)] + "\n" + new_entries + "\n" + html[start_pos + len(start_marker):]
        print("  ⚠ No BLOG_ENTRIES_END marker found. Entries injected but old ones may remain.")

    return html


def main():
    apply = "--apply" in sys.argv

    print("=" * 60)
    print("SteadiDay Blog Index Rebuilder")
    print("=" * 60)
    print(f"Mode: {'APPLY' if apply else 'DRY RUN'}\n")

    posts = scan_posts()
    print(f"Found {len(posts)} blog posts on disk:\n")

    for p in posts:
        flag = " [FEATURED]" if p["is_featured"] else ""
        print(f"  {p['date']}  [{p['category']}]  {p['title'][:50]}{flag}")

    print()

    new_html = rebuild_index(posts)

    if apply:
        with open(INDEX_PATH, 'w', encoding='utf-8') as f:
            f.write(new_html)
        print(f"✅ Rebuilt {INDEX_PATH} with {len(posts)} entries")
        print("   Review with: git diff blog/index.html")
    else:
        print(f"DRY RUN: Would rebuild {INDEX_PATH} with {len(posts)} entries")
        print("   Run with --apply to save changes")

    print("=" * 60)


if __name__ == "__main__":
    main()
