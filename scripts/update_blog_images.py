#!/usr/bin/env python3
"""
SteadiDay Blog Image Deduplicator
==================================
Scans all existing blog posts in the blog/ directory, identifies repeated
Unsplash images across posts, and replaces duplicates with fresh unique images.

How it works:
1. Scans every .html file in blog/ for Unsplash image URLs
2. Builds a map of which images appear in which posts
3. For images used in multiple posts, keeps the FIRST occurrence (oldest post)
   and replaces all later occurrences with fresh images from a replacement pool
4. Hero images and inline images are replaced separately with appropriate sizes
5. Updates og:image and twitter:image meta tags when hero images change

Run from the repo root (where the blog/ directory lives):
    python scripts/update_blog_images.py

Add --dry-run to preview changes without writing files:
    python scripts/update_blog_images.py --dry-run
"""

import os
import re
import sys
import glob
import random
from collections import defaultdict

BLOG_DIR = "blog"

# =============================================================================
# REPLACEMENT IMAGE POOLS
# Fresh Unsplash images NOT already used in the existing blog posts.
# Organized by visual theme so replacements are contextually appropriate.
# =============================================================================

# Hero-sized replacements (w=1200) grouped by visual theme
HERO_REPLACEMENTS = {
    "nature_calm": [
        "https://images.unsplash.com/photo-1501854140801-50d01698950b?w=1200&q=80",
        "https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?w=1200&q=80",
        "https://images.unsplash.com/photo-1475924156734-496f6cac6ec1?w=1200&q=80",
        "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1200&q=80",
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1200&q=80",
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1200&q=80",
        "https://images.unsplash.com/photo-1529693662653-9d480530a697?w=1200&q=80",
    ],
    "health_wellness": [
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80",
        "https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=1200&q=80",
        "https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=1200&q=80",
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=1200&q=80",
        "https://images.unsplash.com/photo-1599058945522-28d584b6f0ff?w=1200&q=80",
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=1200&q=80",
    ],
    "food_nutrition": [
        "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=1200&q=80",
        "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80",
        "https://images.unsplash.com/photo-1490818387583-1baba5e638af?w=1200&q=80",
        "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=1200&q=80",
        "https://images.unsplash.com/photo-1543362906-acfc16c67564?w=1200&q=80",
        "https://images.unsplash.com/photo-1547592180-85f173990554?w=1200&q=80",
    ],
    "medical_safety": [
        "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200&q=80",
        "https://images.unsplash.com/photo-1584432810601-6c7f27d2362b?w=1200&q=80",
        "https://images.unsplash.com/photo-1612531386530-97286d97c2d2?w=1200&q=80",
        "https://images.unsplash.com/photo-1530497610245-94d3c16cda28?w=1200&q=80",
        "https://images.unsplash.com/photo-1585435557343-3b092031a831?w=1200&q=80",
    ],
    "learning_brain": [
        "https://images.unsplash.com/photo-1507413245164-6160d8298b31?w=1200&q=80",
        "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1200&q=80",
        "https://images.unsplash.com/photo-1513475382585-d06e58bcb0e0?w=1200&q=80",
        "https://images.unsplash.com/photo-1488190211105-8b0e65b80b4e?w=1200&q=80",
        "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=1200&q=80",
    ],
    "sleep_rest": [
        "https://images.unsplash.com/photo-1455642305367-68834a1da7ab?w=1200&q=80",
        "https://images.unsplash.com/photo-1520206183501-b80df61043c2?w=1200&q=80",
        "https://images.unsplash.com/photo-1495197359483-d092478c170a?w=1200&q=80",
        "https://images.unsplash.com/photo-1507652313519-d4e9174996dd?w=1200&q=80",
        "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=1200&q=80",
    ],
    "people_social": [
        "https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=1200&q=80",
        "https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=1200&q=80",
        "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=1200&q=80",
        "https://images.unsplash.com/photo-1530268729831-4b0b9e170218?w=1200&q=80",
        "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=1200&q=80",
    ],
}

# Inline-sized replacements (w=800) — a flat pool of diverse images
INLINE_REPLACEMENTS = [
    {"url": "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=800&q=80", "alt": "Journaling with tea"},
    {"url": "https://images.unsplash.com/photo-1506252374453-ef5237291d83?w=800&q=80", "alt": "Peaceful garden path"},
    {"url": "https://images.unsplash.com/photo-1517021897933-0e0319cfbc28?w=800&q=80", "alt": "Sunrise over calm water"},
    {"url": "https://images.unsplash.com/photo-1500904156668-a21764a29575?w=800&q=80", "alt": "Cozy reading corner"},
    {"url": "https://images.unsplash.com/photo-1484627147104-f5197bcd6651?w=800&q=80", "alt": "Gentle morning light"},
    {"url": "https://images.unsplash.com/photo-1446511437394-d789541e7f95?w=800&q=80", "alt": "Walking in nature"},
    {"url": "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80", "alt": "Balance exercises"},
    {"url": "https://images.unsplash.com/photo-1599058945522-28d584b6f0ff?w=800&q=80", "alt": "Outdoor tai chi"},
    {"url": "https://images.unsplash.com/photo-1545389336-cf090694435e?w=800&q=80", "alt": "Gentle stretching"},
    {"url": "https://images.unsplash.com/photo-1518459031867-a89b944bffe4?w=800&q=80", "alt": "Park exercise"},
    {"url": "https://images.unsplash.com/photo-1606787366850-de6330128bfc?w=800&q=80", "alt": "Breakfast spread"},
    {"url": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=800&q=80", "alt": "Avocado toast"},
    {"url": "https://images.unsplash.com/photo-1484980972926-edee96e0960d?w=800&q=80", "alt": "Berry bowl"},
    {"url": "https://images.unsplash.com/photo-1455619452474-d2be8b1e70cd?w=800&q=80", "alt": "Warm soup"},
    {"url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800&q=80", "alt": "Herbal tea at night"},
    {"url": "https://images.unsplash.com/photo-1540518614846-7eded433c457?w=800&q=80", "alt": "Soft pillows"},
    {"url": "https://images.unsplash.com/photo-1445991842772-097fea258e7b?w=800&q=80", "alt": "Sunset transition"},
    {"url": "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=800&q=80", "alt": "Relaxing bath"},
    {"url": "https://images.unsplash.com/photo-1516321497487-e288fb19713f?w=800&q=80", "alt": "Digital literacy"},
    {"url": "https://images.unsplash.com/photo-1453928582365-b6ad33cbcf64?w=800&q=80", "alt": "Focused thinking"},
    {"url": "https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=800&q=80", "alt": "Healthcare checklist"},
    {"url": "https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80", "alt": "Mobile health app"},
    {"url": "https://images.unsplash.com/photo-1510414842594-a61c69b5ae57?w=800&q=80", "alt": "Ocean calm"},
    {"url": "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&q=80", "alt": "Forest path"},
    {"url": "https://images.unsplash.com/photo-1530268729831-4b0b9e170218?w=800&q=80", "alt": "Community gathering"},
    {"url": "https://images.unsplash.com/photo-1581579438747-104c53d7fbc4?w=800&q=80", "alt": "Morning stretch"},
    {"url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&q=80", "alt": "Confident smile"},
    {"url": "https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&q=80", "alt": "Patient care"},
]

# Map blog post topics to visual themes for contextual hero replacement
FILENAME_TO_THEME = {
    "heart-guidelines": "health_wellness",
    "workmate": "people_social",
    "soul-mate": "people_social",
    "brain-training": "learning_brain",
    "dementia": "learning_brain",
    "workplace": "people_social",
    "warm-connections": "people_social",
    "joint-pain": "food_nutrition",
    "social-connection": "people_social",
    "brains-best": "learning_brain",
    "vaccination": "medical_safety",
    "blood-pressure": "health_wellness",
    "calm-your-mind": "nature_calm",
    "breathing": "nature_calm",
    "stretches": "health_wellness",
    "mobility": "health_wellness",
    "chronic-pain": "health_wellness",
    "heart-healthy": "food_nutrition",
    "recipes": "food_nutrition",
    "memory": "learning_brain",
    "sleep": "sleep_rest",
    "mindfulness": "nature_calm",
    "medication": "medical_safety",
}


def get_theme_for_file(filename):
    """Determine the best visual theme for a blog post based on its filename."""
    fname_lower = filename.lower()
    for keyword, theme in FILENAME_TO_THEME.items():
        if keyword in fname_lower:
            return theme
    return "nature_calm"  # safe default


def extract_photo_id(url):
    """Extract the Unsplash photo ID from a URL."""
    match = re.search(r'photo-([a-zA-Z0-9_-]+)', url)
    return match.group(0) if match else None


def scan_posts():
    """Scan all blog posts and build an image usage map.

    Returns:
        posts: dict of {filename: {"hero": photo_id, "inline": [photo_ids], "content": str}}
        image_usage: dict of {photo_id: [filenames]} — which posts use each image
    """
    posts = {}
    image_usage = defaultdict(list)

    for filepath in sorted(glob.glob(os.path.join(BLOG_DIR, "*.html"))):
        filename = os.path.basename(filepath)
        if filename == "index.html" or filename == "rss.xml":
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        # Skip files that don't use Unsplash images
        if "images.unsplash.com" not in content:
            continue

        # Find hero image
        hero_match = re.search(
            r'<img\s+src="(https://images\.unsplash\.com/[^"]+)"[^>]*class="hero-image"',
            content
        )
        hero_id = None
        if hero_match:
            hero_id = extract_photo_id(hero_match.group(1))

        # Find all inline images (in figure tags or article-image class)
        inline_ids = []
        for match in re.finditer(
            r'<img\s+src="(https://images\.unsplash\.com/[^"]+)"[^>]*loading="lazy"',
            content
        ):
            pid = extract_photo_id(match.group(1))
            if pid and pid != hero_id:
                inline_ids.append(pid)

        all_ids = ([hero_id] if hero_id else []) + inline_ids
        for pid in all_ids:
            if pid:
                image_usage[pid].append(filename)

        posts[filename] = {
            "hero": hero_id,
            "inline": inline_ids,
            "content": content,
            "filepath": filepath,
        }

    return posts, image_usage


def build_replacement_plan(posts, image_usage):
    """Determine which images need replacement and assign fresh ones.

    Strategy: For each duplicated image, keep the OLDEST post's usage and
    replace in all newer posts.

    Returns:
        replacements: dict of {filename: [(old_photo_id, new_url, is_hero)]}
    """
    # All images currently used across any post — we won't replace with these
    all_used = set(image_usage.keys())

    # Build flat pool of hero replacements, excluding already-used images
    hero_pool = []
    for theme_images in HERO_REPLACEMENTS.values():
        for url in theme_images:
            pid = extract_photo_id(url)
            if pid not in all_used:
                hero_pool.append(url)
    random.shuffle(hero_pool)

    # Build flat pool of inline replacements, excluding already-used images
    inline_pool = []
    for img in INLINE_REPLACEMENTS:
        pid = extract_photo_id(img["url"])
        if pid not in all_used:
            inline_pool.append(img)
    random.shuffle(inline_pool)

    hero_pool_idx = 0
    inline_pool_idx = 0
    assigned_images = set()  # Track what we've assigned to avoid new duplicates

    replacements = defaultdict(list)

    # Find duplicated images (used in 2+ posts)
    duplicated = {pid: fnames for pid, fnames in image_usage.items() if len(fnames) > 1}

    print(f"\nFound {len(duplicated)} duplicated images across posts:")
    for pid, fnames in sorted(duplicated.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {pid}: used in {len(fnames)} posts")
        for fn in fnames:
            print(f"    - {fn}")

    for photo_id, filenames in duplicated.items():
        # Sort by date (filename starts with date) — keep oldest
        sorted_files = sorted(filenames)
        keeper = sorted_files[0]
        to_replace = sorted_files[1:]

        for filename in to_replace:
            post = posts[filename]
            is_hero = (post["hero"] == photo_id)

            if is_hero:
                # Pick a themed hero replacement
                theme = get_theme_for_file(filename)
                themed_pool = [
                    url for url in HERO_REPLACEMENTS.get(theme, [])
                    if extract_photo_id(url) not in all_used
                    and extract_photo_id(url) not in assigned_images
                ]
                if themed_pool:
                    new_url = themed_pool[0]
                elif hero_pool_idx < len(hero_pool):
                    new_url = hero_pool[hero_pool_idx]
                    hero_pool_idx += 1
                else:
                    print(f"  ⚠ No hero replacement available for {filename}, skipping")
                    continue

                new_pid = extract_photo_id(new_url)
                assigned_images.add(new_pid)
                all_used.add(new_pid)
                replacements[filename].append((photo_id, new_url, True))
            else:
                # Pick an inline replacement
                available = [
                    img for img in inline_pool
                    if extract_photo_id(img["url"]) not in all_used
                    and extract_photo_id(img["url"]) not in assigned_images
                ]
                if available:
                    new_img = available[0]
                    inline_pool.remove(new_img)
                elif inline_pool_idx < len(inline_pool):
                    new_img = inline_pool[inline_pool_idx]
                    inline_pool_idx += 1
                else:
                    print(f"  ⚠ No inline replacement available for {photo_id} in {filename}, skipping")
                    continue

                new_pid = extract_photo_id(new_img["url"])
                assigned_images.add(new_pid)
                all_used.add(new_pid)
                replacements[filename].append((photo_id, new_img["url"], False))

    return replacements


def apply_replacements(posts, replacements, dry_run=False):
    """Apply image replacements to the actual HTML files."""
    total_changes = 0

    for filename, swaps in sorted(replacements.items()):
        post = posts[filename]
        content = post["content"]
        filepath = post["filepath"]
        file_changes = 0

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Updating {filename}:")

        for old_photo_id, new_url, is_hero in swaps:
            # Build regex to match the old image URL (any width/quality params)
            old_pattern = re.compile(
                r'https://images\.unsplash\.com/' + re.escape(old_photo_id) + r'\?[^"]*'
            )

            matches = old_pattern.findall(content)
            if not matches:
                print(f"  ⚠ Could not find {old_photo_id} in file")
                continue

            # Replace all occurrences of this photo ID in the file
            content = old_pattern.sub(new_url, content)

            # If hero was replaced, also update og:image and twitter:image meta tags
            if is_hero:
                new_hero_1200 = new_url.replace("w=800", "w=1200")
                # The og:image/twitter:image might reference the old hero
                og_pattern = re.compile(
                    r'(content="https://images\.unsplash\.com/)' + re.escape(old_photo_id) + r'\?[^"]*(")'
                )
                content = og_pattern.sub(r'\g<1>' + extract_photo_id(new_url) + '?w=1200&q=80"', content)

            label = "HERO" if is_hero else "inline"
            new_pid = extract_photo_id(new_url)
            print(f"  {label}: {old_photo_id} → {new_pid}")
            file_changes += len(matches)

        if file_changes > 0 and not dry_run:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            # Update the cached content
            posts[filename]["content"] = content

        total_changes += file_changes

    return total_changes


def verify_no_duplicates(posts):
    """Post-run verification: check that no image is used in more than one post."""
    image_usage = defaultdict(list)
    for filename, post in posts.items():
        all_matches = re.findall(
            r'https://images\.unsplash\.com/(photo-[a-zA-Z0-9_-]+)',
            post["content"]
        )
        for pid in set(all_matches):
            image_usage[pid].append(filename)

    remaining_dupes = {pid: fnames for pid, fnames in image_usage.items() if len(fnames) > 1}
    if remaining_dupes:
        print(f"\n⚠ {len(remaining_dupes)} images still appear in multiple posts:")
        for pid, fnames in remaining_dupes.items():
            print(f"  {pid}: {', '.join(fnames)}")
        return False
    else:
        print("\n✅ Verification passed: no duplicate images across posts")
        return True


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("SteadiDay Blog Image Deduplicator")
    print("=" * 60)

    if dry_run:
        print("Mode: DRY RUN (no files will be modified)\n")
    else:
        print("Mode: LIVE (files will be updated)\n")

    if not os.path.exists(BLOG_DIR):
        print(f"Error: {BLOG_DIR}/ directory not found. Run from the repo root.")
        sys.exit(1)

    # Step 1: Scan
    print("Step 1: Scanning blog posts for images...")
    posts, image_usage = scan_posts()
    print(f"  Found {len(posts)} posts with Unsplash images")
    print(f"  Found {len(image_usage)} unique images total")

    # Step 2: Plan
    print("\nStep 2: Building replacement plan...")
    replacements = build_replacement_plan(posts, image_usage)
    total_swaps = sum(len(swaps) for swaps in replacements.values())
    print(f"  {total_swaps} replacements planned across {len(replacements)} files")

    if total_swaps == 0:
        print("\n✅ No duplicate images found. Nothing to do!")
        return

    # Step 3: Apply
    print(f"\nStep 3: {'Previewing' if dry_run else 'Applying'} replacements...")
    total_changes = apply_replacements(posts, replacements, dry_run=dry_run)
    print(f"\n{'Would update' if dry_run else 'Updated'} {total_changes} image references in {len(replacements)} files")

    # Step 4: Verify
    if not dry_run:
        print("\nStep 4: Verifying results...")
        # Re-scan to verify
        for filename in replacements:
            filepath = os.path.join(BLOG_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                posts[filename]["content"] = f.read()
        verify_no_duplicates(posts)

    if dry_run:
        print("\nRe-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
