#!/usr/bin/env python3
"""
Inject Google Ads gtag + App Store conversion tracking into all HTML files.

What it does:
1. Finds every .html file in the repo
2. Injects the gtag.js base snippet after <head> (if not already present)
3. Injects an App Store click conversion tracker before </body> (if not already present)

Safe to run multiple times — skips files that already have the tags.
"""

import os
import sys

# ─── Configuration ───────────────────────────────────────────────────────────
GTAG_ID = "AW-17929124014"

# The conversion event snippet from Google Ads
# Replace the send_to value with your actual conversion label from Google Ads
CONVERSION_LABEL = "AW-17929124014/REPLACE_WITH_YOUR_CONVERSION_LABEL"

GTAG_SNIPPET = f'''<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GTAG_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GTAG_ID}');
</script>'''

CONVERSION_SNIPPET = f'''<!-- Google Ads: App Store click conversion tracking -->
<script>
  document.addEventListener('DOMContentLoaded', function() {{
    // Track clicks on all App Store links as conversions
    var links = document.querySelectorAll('a[href*="apps.apple.com"]');
    for (var i = 0; i < links.length; i++) {{
      links[i].addEventListener('click', function() {{
        if (typeof gtag === 'function') {{
          gtag('event', 'conversion', {{
            'send_to': '{CONVERSION_LABEL}',
            'event_callback': function() {{
              // Allow the link to proceed after tracking
            }}
          }});
        }}
      }});
    }}
  }});
</script>'''

# ─── Markers to detect existing injections ───────────────────────────────────
GTAG_MARKER = f"googletagmanager.com/gtag/js?id={GTAG_ID}"
CONVERSION_MARKER = "App Store click conversion tracking"

# ─── File discovery ──────────────────────────────────────────────────────────
SKIP_DIRS = {'.git', 'node_modules', '.github', '__pycache__'}


def find_html_files(root_dir):
    """Find all .html files, skipping irrelevant directories."""
    html_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith('.html'):
                html_files.append(os.path.join(dirpath, f))
    return html_files


def inject_into_file(filepath):
    """Inject gtag and conversion snippets into a single HTML file."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    modified = False

    # 1. Inject gtag after <head>
    if GTAG_MARKER not in content:
        # Try <head> with attributes first, then plain <head>
        for tag in ['<head>', '<HEAD>']:
            if tag in content:
                content = content.replace(tag, tag + '\n' + GTAG_SNIPPET, 1)
                modified = True
                break
        else:
            # Try regex-style match for <head ...>
            import re
            head_match = re.search(r'<head[^>]*>', content, re.IGNORECASE)
            if head_match:
                insert_pos = head_match.end()
                content = content[:insert_pos] + '\n' + GTAG_SNIPPET + content[insert_pos:]
                modified = True

    # 2. Inject conversion tracking before </body>
    if CONVERSION_MARKER not in content:
        for tag in ['</body>', '</BODY>']:
            if tag in content:
                content = content.replace(tag, CONVERSION_SNIPPET + '\n' + tag, 1)
                modified = True
                break

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    html_files = find_html_files(root)

    if not html_files:
        print(f"No .html files found in {os.path.abspath(root)}")
        return

    injected = 0
    skipped = 0

    for filepath in html_files:
        rel = os.path.relpath(filepath, root)
        if inject_into_file(filepath):
            print(f"  ✅ Injected: {rel}")
            injected += 1
        else:
            print(f"  ⏭️  Skipped (already has tags): {rel}")
            skipped += 1

    print(f"\nDone! {injected} files updated, {skipped} already had tags.")


if __name__ == '__main__':
    main()
