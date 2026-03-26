#!/usr/bin/env python3
“””
SteadiDay Blog Generator v3.6
Changes from v3.5:

- Fixed: Added verify_youtube_video() that checks YouTube oEmbed API before embedding
- Fixed: Fallback videos from CATEGORY_VIDEOS are now verified before use (skips dead/private videos)
- Fixed: If no working video is found, blog publishes without a video instead of showing “Video unavailable”
- Fixed: Dynamically-found videos are also verified before embedding
  Changes from v3.4:
- Fixed: YouTube embeds now use youtube.com instead of youtube-nocookie.com
  (youtube-nocookie.com is blocked by Brave, many ad blockers, and some CSPs)
- Fixed: Removed loading=“lazy” from video iframes (caused iframes to never load
  inside height:0 responsive containers)
- Fixed: Removed deprecated frameborder=“0” (already handled by CSS border:0)
- Updated: referrerpolicy to strict-origin-when-cross-origin (matches YouTube’s
  recommended embed code)
  Changes from v3.3:
- Fixed: call_with_retry() now handles 429 rate limit errors (not just 529/5xx)
- Increased max_retries from 3 to 5 for better resilience
  Changes from v3.2:
- Added: Retry logic with exponential backoff for transient API errors (529 Overloaded, 5xx)
- Added: call_with_retry() helper wrapping all client.messages.create() calls
  Changes from v3.1:
- Fixed: YouTube videos now found dynamically via web search (no more stale hardcoded IDs)
- Kept: CATEGORY_VIDEOS as fallback if dynamic search fails
- Added: find_youtube_video() function using Claude web_search tool
  Changes from v3.0:
- Added: RSS feed generation (blog/rss.xml) – auto-updates on every blog post
- Added: Buttondown email newsletter draft creation via API
- Added: RSS <link> tag in blog post HTML template <head>
  “””

import anthropic
from anthropic import APIStatusError
import random
import re
import os
import sys
import glob
import json
import time
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher

WEBSITE_URL = “https://www.steadiday.com”
BLOG_BASE_URL = f”{WEBSITE_URL}/blog”
APP_STORE_URL = “https://apps.apple.com/app/steadiday/id6758526744”

# ============================================================

# RETRY HELPER – handles 429 Rate Limit, 529 Overloaded, 5xx

# ============================================================

def call_with_retry(func, max_retries=5, base_delay=30):
“”“Call func() with exponential backoff on transient API errors.”””
for attempt in range(max_retries + 1):
try:
return func()
except APIStatusError as e:
if e.status_code in (429, 529) or e.status_code >= 500:
if attempt == max_retries:
raise
delay = base_delay * (2 ** attempt)
print(f”  API error {e.status_code} (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s…”)
time.sleep(delay)
else:
raise

def get_existing_posts(blog_dir=“blog”):
“”“Scan existing blog posts and extract titles and slugs.”””
existing = []
if not os.path.exists(blog_dir):
return existing
for filepath in glob.glob(os.path.join(blog_dir, “*.html”)):
filename = os.path.basename(filepath)
if filename == “index.html”:
continue
# Skip redirect files (under 1KB)
try:
if os.path.getsize(filepath) < 1024:
continue
except OSError:
pass
title = “”
try:
with open(filepath, ‘r’, encoding=‘utf-8’) as f:
content = f.read(5000)
m = re.search(r’<h1[^>]*>(.*?)</h1>’, content, re.DOTALL)
if m:
title = re.sub(r’<[^>]+>’, ‘’, m.group(1)).strip()
except Exception:
pass
slug = re.sub(r’^\d{4}-\d{2}-\d{2}-’, ‘’, filename.replace(’.html’, ‘’))
existing.append({“filename”: filename, “title”: title, “slug”: slug})
return existing

def normalize_text(text):
“”“Normalize text for comparison: lowercase, strip punctuation, collapse whitespace.”””
text = text.lower().strip()
text = re.sub(r’[^a-z0-9\s]’, ‘’, text)
text = re.sub(r’\s+’, ’ ’, text)
return text

def get_content_words(text):
“”“Extract meaningful content words, removing stop words.”””
stop = {
‘the’, ‘a’, ‘an’, ‘for’, ‘and’, ‘or’, ‘to’, ‘of’, ‘in’, ‘your’,
‘how’, ‘that’, ‘with’, ‘after’, ‘from’, ‘is’, ‘are’, ‘was’, ‘were’,
‘be’, ‘been’, ‘being’, ‘have’, ‘has’, ‘had’, ‘do’, ‘does’, ‘did’,
‘will’, ‘would’, ‘could’, ‘should’, ‘may’, ‘might’, ‘can’, ‘this’,
‘these’, ‘those’, ‘it’, ‘its’, ‘you’, ‘we’, ‘they’, ‘them’, ‘our’,
‘my’, ‘me’, ‘what’, ‘which’, ‘who’, ‘whom’, ‘when’, ‘where’, ‘why’,
‘not’, ‘no’, ‘so’, ‘if’, ‘but’, ‘as’, ‘at’, ‘by’, ‘on’, ‘up’,
‘about’, ‘into’, ‘over’, ‘than’, ‘then’, ‘too’, ‘very’, ‘just’,
‘also’, ‘more’, ‘most’, ‘some’, ‘any’, ‘all’, ‘each’, ‘every’,
‘simple’, ‘easy’, ‘best’, ‘top’, ‘guide’, ‘tips’, ‘ways’,
‘adults’, ‘seniors’, ‘50’, ‘over’, ‘after’, ‘really’, ‘complete’,
}
words = set(normalize_text(text).split())
return words - stop

def is_duplicate(new_title, new_slug, existing_posts, threshold_title=0.55, threshold_slug=0.60):
ntl = normalize_text(new_title)
nsl = normalize_text(new_slug)
for post in existing_posts:
etl = normalize_text(post[‘title’])
esl = normalize_text(post[‘slug’])
title_ratio = SequenceMatcher(None, ntl, etl).ratio()
if title_ratio >= threshold_title:
return (True, f”Title similarity {title_ratio:.2f}”, post[‘filename’])
slug_ratio = SequenceMatcher(None, nsl, esl).ratio()
if slug_ratio >= threshold_slug:
return (True, f”Slug similarity {slug_ratio:.2f}”, post[‘filename’])
new_words = get_content_words(new_title)
existing_words = get_content_words(post[‘title’])
if new_words and existing_words:
overlap = new_words & existing_words
min_len = min(len(new_words), len(existing_words))
if min_len > 0:
overlap_ratio = len(overlap) / min_len
if len(overlap) >= 2 and overlap_ratio >= 0.6:
return (True, f”Keyword overlap ({overlap})”, post[‘filename’])
return (False, “”, “”)

def check_semantic_duplicate(client, new_title, existing_posts):
if not existing_posts:
return False, “”
existing_titles = [p[‘title’] for p in existing_posts if p[‘title’]]
if not existing_titles:
return False, “”
titles_list = “\n”.join([f”- {t}” for t in existing_titles])
prompt = f””“You are a blog content deduplication checker.

PROPOSED NEW POST TITLE: “{new_title}”

EXISTING POSTS:
{titles_list}

Would the proposed post cover substantially the same ground as any existing post?
Consider: same core topic, same target advice, same actionable takeaways.
Different angles on the same broad category (e.g., “nutrition”) are OK.
Same specific advice reworded (e.g., “blood pressure explained” vs “understanding blood pressure numbers”) is NOT OK.

Reply with ONLY one of:
UNIQUE - if the topic is sufficiently different
DUPLICATE OF: [existing title] - if it overlaps too much”””

```
msg = call_with_retry(lambda: client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=200,
    messages=[{"role": "user", "content": prompt}]
))
result = msg.content[0].text.strip()
if result.startswith("DUPLICATE"):
    return True, result
return False, ""
```

def generate_news_driven_topic(client, existing_posts):
existing_titles = [p[‘title’] for p in existing_posts if p[‘title’]]
avoid = “\n”.join([f”- {t}” for t in existing_titles]) if existing_titles else “None yet.”
prompt = f””“Search for recent health news, studies, or guidelines relevant to adults over 50.
Look for stories from the past 2 weeks from sources like NIH, CDC, Mayo Clinic, AARP, or major health journals.

Then suggest ONE blog topic based on what you find that would be timely and useful.

EXISTING POSTS (do NOT duplicate these topics):
{avoid}

Consider topics like: new medical guidelines, seasonal health alerts, recent study findings,
emerging wellness trends for older adults, new recommendations from health organizations.

FORMAT YOUR RESPONSE EXACTLY AS:
TOPIC: [specific description of the topic]
TITLE: [blog title under 55 characters]
KEYWORD: [primary SEO keyword phrase]
CATEGORY: [exactly one of: Mental Wellness|Medication Tips|Healthy Aging|Exercise|Nutrition|Sleep|Heart Health|Brain Health|Safety|Wellness]
ANGLE: [what makes this timely - reference the specific news/study]
SOURCE: [the news source or study you found]”””

```
msg = call_with_retry(lambda: client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1000,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    messages=[{"role": "user", "content": prompt}]
))
response_text = ""
for block in msg.content:
    if hasattr(block, 'text'):
        response_text += block.text

topic = re.search(r'TOPIC:\s*(.+?)(?:\n|$)', response_text)
title = re.search(r'TITLE:\s*(.+?)(?:\n|$)', response_text)
kw = re.search(r'KEYWORD:\s*(.+?)(?:\n|$)', response_text)
cat = re.search(r'CATEGORY:\s*(.+?)(?:\n|$)', response_text)
angle = re.search(r'ANGLE:\s*(.+?)(?:\n|$)', response_text)
source = re.search(r'SOURCE:\s*(.+?)(?:\n|$)', response_text)

valid_categories = [
    "Mental Wellness", "Medication Tips", "Healthy Aging", "Exercise",
    "Nutrition", "Sleep", "Heart Health", "Brain Health", "Safety", "Wellness"
]
c = cat.group(1).strip() if cat else "Wellness"
if c not in valid_categories:
    c = "Wellness"

result = {
    "topic": topic.group(1).strip() if topic else "Health tips for adults 50+",
    "keyword": kw.group(1).strip() if kw else "health tips seniors",
    "category": c,
    "suggested_title": title.group(1).strip() if title else "",
    "angle": angle.group(1).strip() if angle else "",
    "source": source.group(1).strip() if source else "",
}
print(f"  News source: {result.get('source', 'N/A')}")
return result
```

TOPIC_CATEGORIES = [
{“topic”: “Chair exercises you can do while watching TV”, “keyword”: “chair exercises seniors”, “category”: “Exercise”},
{“topic”: “Balance exercises to prevent falls at home”, “keyword”: “balance exercises seniors”, “category”: “Exercise”},
{“topic”: “Gentle yoga poses for beginners over 50”, “keyword”: “yoga seniors beginners”, “category”: “Exercise”},
{“topic”: “Walking for health: Getting started safely”, “keyword”: “walking exercise seniors”, “category”: “Exercise”},
{“topic”: “How to build a medication routine that sticks”, “keyword”: “medication routine tips”, “category”: “Medication Tips”},
{“topic”: “Understanding common medication side effects”, “keyword”: “medication side effects”, “category”: “Medication Tips”},
{“topic”: “Questions to ask your pharmacist at every visit”, “keyword”: “pharmacist questions seniors”, “category”: “Medication Tips”},
{“topic”: “How to safely store medications at home”, “keyword”: “medication storage tips”, “category”: “Medication Tips”},
{“topic”: “Foods that naturally lower cholesterol”, “keyword”: “lower cholesterol naturally”, “category”: “Heart Health”},
{“topic”: “Warning signs your heart needs attention”, “keyword”: “heart warning signs seniors”, “category”: “Heart Health”},
{“topic”: “5 brain exercises to keep your mind sharp”, “keyword”: “brain exercises seniors”, “category”: “Brain Health”},
{“topic”: “How social connection protects your brain”, “keyword”: “social connection brain health”, “category”: “Brain Health”},
{“topic”: “Crossword puzzles and games for cognitive health”, “keyword”: “brain games seniors”, “category”: “Brain Health”},
{“topic”: “The importance of staying hydrated as we age”, “keyword”: “hydration tips elderly”, “category”: “Nutrition”},
{“topic”: “Healthy snacks for sustained energy after 50”, “keyword”: “healthy snacks seniors”, “category”: “Nutrition”},
{“topic”: “Anti-inflammatory foods for joint pain relief”, “keyword”: “anti inflammatory foods seniors”, “category”: “Nutrition”},
{“topic”: “Meal planning made simple for one or two”, “keyword”: “meal planning seniors”, “category”: “Nutrition”},
{“topic”: “Calcium and vitamin D for strong bones”, “keyword”: “calcium vitamin D seniors”, “category”: “Nutrition”},
{“topic”: “Why sleep patterns change as we age”, “keyword”: “sleep changes aging”, “category”: “Sleep”},
{“topic”: “Creating a bedtime routine that works”, “keyword”: “bedtime routine seniors”, “category”: “Sleep”},
{“topic”: “Staying social: Why connection matters after 60”, “keyword”: “social connection elderly”, “category”: “Mental Wellness”},
{“topic”: “Dealing with loneliness after retirement”, “keyword”: “loneliness retirement seniors”, “category”: “Mental Wellness”},
{“topic”: “Gratitude journaling for better mental health”, “keyword”: “gratitude journal seniors”, “category”: “Mental Wellness”},
{“topic”: “How volunteering boosts your wellbeing”, “keyword”: “volunteering seniors benefits”, “category”: “Mental Wellness”},
{“topic”: “How to prevent falls at home”, “keyword”: “fall prevention seniors”, “category”: “Safety”},
{“topic”: “Home safety checklist for aging in place”, “keyword”: “home safety seniors checklist”, “category”: “Safety”},
{“topic”: “Staying safe in extreme heat and cold”, “keyword”: “weather safety seniors”, “category”: “Safety”},
{“topic”: “The health benefits of gardening after 50”, “keyword”: “gardening health benefits seniors”, “category”: “Wellness”},
{“topic”: “How pets improve health and happiness”, “keyword”: “pets health benefits seniors”, “category”: “Wellness”},
{“topic”: “Eye health tips to protect your vision”, “keyword”: “eye health tips seniors”, “category”: “Wellness”},
{“topic”: “Hearing health and when to get tested”, “keyword”: “hearing health seniors”, “category”: “Wellness”},
{“topic”: “Skin care and sun protection after 50”, “keyword”: “skin care seniors sun protection”, “category”: “Wellness”},
{“topic”: “Managing arthritis pain with daily habits”, “keyword”: “arthritis management seniors”, “category”: “Wellness”},
{“topic”: “Digestive health tips for adults over 50”, “keyword”: “digestive health seniors”, “category”: “Wellness”},
]

CATEGORY_IMAGES = {
“Mental Wellness”: “https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80”,
“Medication Tips”: “https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&q=80”,
“Healthy Aging”: “https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=800&q=80”,
“Exercise”: “https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80”,
“Nutrition”: “https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80”,
“Sleep”: “https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=800&q=80”,
“Heart Health”: “https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80”,
“Brain Health”: “https://images.unsplash.com/photo-1559757175-5700dde675bc?w=800&q=80”,
“Safety”: “https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80”,
“Wellness”: “https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80”,
}

HERO_IMAGES = {
“Mental Wellness”: [“https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80”, “https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=1200&q=80”, “https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=1200&q=80”],
“Medication Tips”: [“https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1200&q=80”, “https://images.unsplash.com/photo-1471864190281-a93a3070b6de?w=1200&q=80”, “https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=1200&q=80”],
“Healthy Aging”: [“https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=1200&q=80”, “https://images.unsplash.com/photo-1516307365426-bea591f05011?w=1200&q=80”, “https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=1200&q=80”],
“Exercise”: [“https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80”, “https://images.unsplash.com/photo-1486218119243-13883505764c?w=1200&q=80”, “https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=1200&q=80”],
“Nutrition”: [“https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80”, “https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=1200&q=80”, “https://images.unsplash.com/photo-1606923829579-0cb981a83e2e?w=1200&q=80”],
“Sleep”: [“https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=1200&q=80”, “https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=1200&q=80”, “https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=1200&q=80”],
“Heart Health”: [“https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=1200&q=80”, “https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=1200&q=80”, “https://images.unsplash.com/photo-1628348070889-cb656235b4eb?w=1200&q=80”],
“Brain Health”: [“https://images.unsplash.com/photo-1559757175-5700dde675bc?w=1200&q=80”, “https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=1200&q=80”, “https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&q=80”],
“Safety”: [“https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80”, “https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=1200&q=80”],
“Wellness”: [“https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80”, “https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80”, “https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=1200&q=80”],
}

INLINE_IMAGES = {
“Mental Wellness”: [{“url”: “https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80”, “alt”: “Person relaxing peacefully”}, {“url”: “https://images.unsplash.com/photo-1508672019048-805c876b67e2?w=800&q=80”, “alt”: “Peaceful beach scene”}, {“url”: “https://images.unsplash.com/photo-1545205597-3d9d02c29547?w=800&q=80”, “alt”: “Meditation hands”}, {“url”: “https://images.unsplash.com/photo-1515377905703-c4788e51af15?w=800&q=80”, “alt”: “Sunlight through trees”}, {“url”: “https://images.unsplash.com/photo-1528715471579-d1bcf0ba5e83?w=800&q=80”, “alt”: “Calm space with plants”}],
“Medication Tips”: [{“url”: “https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=800&q=80”, “alt”: “Pill organizer”}, {“url”: “https://images.unsplash.com/photo-1576602976047-174e57a47881?w=800&q=80”, “alt”: “Healthcare professional”}, {“url”: “https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80”, “alt”: “Healthy lifestyle”}, {“url”: “https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800&q=80”, “alt”: “Morning routine”}, {“url”: “https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80”, “alt”: “Doctor consultation”}],
“Healthy Aging”: [{“url”: “https://images.unsplash.com/photo-1516307365426-bea591f05011?w=800&q=80”, “alt”: “Active senior outdoors”}, {“url”: “https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80”, “alt”: “Healthy choices”}, {“url”: “https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&q=80”, “alt”: “Couple walking”}, {“url”: “https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=800&q=80”, “alt”: “Family moment”}, {“url”: “https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=800&q=80”, “alt”: “Active aging”}],
“Exercise”: [{“url”: “https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80”, “alt”: “Stretching at home”}, {“url”: “https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=800&q=80”, “alt”: “Resistance training”}, {“url”: “https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=800&q=80”, “alt”: “Walking outdoors”}, {“url”: “https://images.unsplash.com/photo-1518611012118-696072aa579a?w=800&q=80”, “alt”: “Group fitness”}, {“url”: “https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80”, “alt”: “Yoga exercises”}],
“Nutrition”: [{“url”: “https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=800&q=80”, “alt”: “Meal preparation”}, {“url”: “https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=800&q=80”, “alt”: “Fresh produce”}, {“url”: “https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=800&q=80”, “alt”: “Balanced meal”}, {“url”: “https://images.unsplash.com/photo-1606923829579-0cb981a83e2e?w=800&q=80”, “alt”: “Salmon dish”}, {“url”: “https://images.unsplash.com/photo-1544025162-d76694265947?w=800&q=80”, “alt”: “Cooking at home”}],
“Sleep”: [{“url”: “https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=800&q=80”, “alt”: “Peaceful bedroom”}, {“url”: “https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=800&q=80”, “alt”: “Bedtime routine”}, {“url”: “https://images.unsplash.com/photo-1495197359483-d092478c170a?w=800&q=80”, “alt”: “Comfortable bed”}, {“url”: “https://images.unsplash.com/photo-1544027993-37dbfe43562a?w=800&q=80”, “alt”: “Herbal tea”}, {“url”: “https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80”, “alt”: “Morning light”}],
“Heart Health”: [{“url”: “https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80”, “alt”: “Healthy lifestyle”}, {“url”: “https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80”, “alt”: “Fresh vegetables”}, {“url”: “https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80”, “alt”: “Cardio exercise”}, {“url”: “https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=800&q=80”, “alt”: “Jogging outdoors”}, {“url”: “https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80”, “alt”: “Heart-healthy meal”}],
“Brain Health”: [{“url”: “https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=800&q=80”, “alt”: “Learning and education”}, {“url”: “https://images.unsplash.com/photo-1456406644174-8ddd4cd52a06?w=800&q=80”, “alt”: “Reading”}, {“url”: “https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=800&q=80”, “alt”: “Puzzles and games”}, {“url”: “https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&q=80”, “alt”: “Social connection”}, {“url”: “https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80”, “alt”: “Relaxation”}],
“Safety”: [{“url”: “https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=800&q=80”, “alt”: “Home safety”}, {“url”: “https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80”, “alt”: “Medical guidance”}, {“url”: “https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80”, “alt”: “Well-lit home”}, {“url”: “https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&q=80”, “alt”: “Accessible design”}, {“url”: “https://images.unsplash.com/photo-1494438639946-1ebd1d20bf85?w=800&q=80”, “alt”: “Clear pathways”}],
“Wellness”: [{“url”: “https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80”, “alt”: “Mindfulness”}, {“url”: “https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80”, “alt”: “Yoga”}, {“url”: “https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80”, “alt”: “Morning wellness”}, {“url”: “https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80”, “alt”: “Self-care”}, {“url”: “https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=800&q=80”, “alt”: “Nature walk”}],
}

CATEGORY_VIDEOS = {
“Mental Wellness”: [{“id”: “inpok4MKVLM”, “title”: “5-Minute Meditation”, “channel”: “Goodful”}, {“id”: “ZToicYcHIOU”, “title”: “Breathing for Stress Relief”, “channel”: “Therapy in a Nutshell”}, {“id”: “SEfs5TJZ6Nk”, “title”: “How to Practice Mindfulness”, “channel”: “Psych Hub”}],
“Medication Tips”: [{“id”: “xLUaVeKhbK8”, “title”: “Managing Multiple Medications”, “channel”: “AARP”}, {“id”: “Ry_bVsdcYvM”, “title”: “Organize Your Medications”, “channel”: “Walgreens”}, {“id”: “QB1kk0p_E0I”, “title”: “Understanding Prescriptions”, “channel”: “Cleveland Clinic”}],
“Healthy Aging”: [{“id”: “3PycZtfns_U”, “title”: “Secrets to Healthy Aging”, “channel”: “Mayo Clinic”}, {“id”: “TUqEu0mBMr8”, “title”: “Staying Active as You Age”, “channel”: “AARP”}],
“Exercise”: [{“id”: “6cJuPmYp7lE”, “title”: “Gentle Morning Stretch”, “channel”: “SilverSneakers”}, {“id”: “8Oh3q4BC4y8”, “title”: “Seated Exercises”, “channel”: “More Life Health”}, {“id”: “sRZ4IqwvHH8”, “title”: “Balance Exercises”, “channel”: “Bob & Brad”}],
“Nutrition”: [{“id”: “fqhYBTg73fw”, “title”: “Healthy Eating Tips”, “channel”: “AARP”}, {“id”: “TRov4mMb_B4”, “title”: “Mediterranean Diet”, “channel”: “Cleveland Clinic”}, {“id”: “vBEI3JXxLJM”, “title”: “Anti-Inflammatory Foods”, “channel”: “Dr. Eric Berg DC”}],
“Sleep”: [{“id”: “t0kACis_dJE”, “title”: “Sleep Hygiene Tips”, “channel”: “Mayo Clinic”}, {“id”: “LFBjI3RA2JI”, “title”: “Fall Asleep Faster”, “channel”: “Cleveland Clinic”}],
“Heart Health”: [{“id”: “pBrEhtfrVsE”, “title”: “Heart Healthy Tips”, “channel”: “AHA”}, {“id”: “RQSl6Dnsf68”, “title”: “Understanding Blood Pressure”, “channel”: “Cleveland Clinic”}, {“id”: “LXb3EKWsInQ”, “title”: “Heart-Healthy Foods”, “channel”: “Mayo Clinic”}],
“Brain Health”: [{“id”: “LNHBMFCzznE”, “title”: “Keep Your Brain Sharp”, “channel”: “AARP”}, {“id”: “pIlTb6SjR_g”, “title”: “Memory Tips”, “channel”: “TED-Ed”}, {“id”: “f7Dl6a9i0wY”, “title”: “Brain Foods”, “channel”: “Cleveland Clinic”}],
“Safety”: [{“id”: “8Gq3D_YOYew”, “title”: “Fall Prevention”, “channel”: “Bob & Brad”}, {“id”: “TLWGn5HD_0I”, “title”: “Home Safety Checklist”, “channel”: “AARP”}],
“Wellness”: [{“id”: “inpok4MKVLM”, “title”: “Morning Meditation”, “channel”: “Goodful”}, {“id”: “6cJuPmYp7lE”, “title”: “Full Body Stretch”, “channel”: “SilverSneakers”}, {“id”: “SEfs5TJZ6Nk”, “title”: “Intro to Mindfulness”, “channel”: “Psych Hub”}],
}

STEADIDAY_FEATURES = {
“free”: [
“Emergency SOS button”, “Fall Detection”, “Trusted Contacts”,
“Medication reminders”, “Apple Health integration”,
“Food and water logging”, “Mind Breaks games”, “Calendar sync”,
“Magnifier tool”, “Find My Car”, “Flashlight”
]
}

def get_html_template():
return ‘’’<!DOCTYPE html>

<html lang="en">
<head>
<!-- GTAG_INJECTED -->
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-17929124014"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'AW-17929124014');
</script>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | SteadiDay Blog</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="SteadiDay Team">
    <meta name="robots" content="index, follow">
    <meta name="apple-itunes-app" content="app-id=6758526744">
    <link rel="canonical" href="{canonical_url}">
    <link rel="alternate" type="application/rss+xml" title="SteadiDay Blog RSS" href="https://www.steadiday.com/blog/rss.xml">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:image" content="{hero_image}">
    <meta property="og:site_name" content="SteadiDay">
    <meta property="article:published_time" content="{iso_date}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{meta_description}">
    <meta name="twitter:image" content="{hero_image}">
    <link rel="icon" type="image/jpeg" href="../assets/icon.jpeg">
    <link rel="apple-touch-icon" href="../assets/icon.jpeg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org", "@type": "Article",
        "headline": "{title}", "description": "{meta_description}", "image": "{hero_image}",
        "author": {{ "@type": "Organization", "name": "SteadiDay Team", "url": "{website_url}" }},
        "publisher": {{ "@type": "Organization", "name": "SteadiDay", "logo": {{ "@type": "ImageObject", "url": "{website_url}/assets/icon.jpeg" }} }},
        "datePublished": "{iso_date}", "dateModified": "{iso_date}",
        "mainEntityOfPage": {{ "@type": "WebPage", "@id": "{canonical_url}" }}
    }}
    </script>
    <style>
        :root {{ --cream: #FFFBF5; --teal: #1A8A7D; --teal-dark: #147568; --teal-light: #E8F5F3; --navy: #1E3A5F; --navy-light: #2D4A6F; --charcoal: #2D3436; --charcoal-light: #5A6266; --white: #FFFFFF; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Source Sans 3', -apple-system, sans-serif; font-size: 1.125rem; line-height: 1.8; color: var(--charcoal); background: var(--cream); }}
        h1, h2, h3 {{ font-family: 'Merriweather', Georgia, serif; color: var(--navy); line-height: 1.3; }}
        a {{ color: var(--teal); text-decoration: none; }} a:hover {{ color: var(--teal-dark); text-decoration: underline; }}
        .nav {{ background: var(--white); padding: 1rem 0; border-bottom: 1px solid rgba(30,58,95,0.1); position: sticky; top: 0; z-index: 100; }}
        .nav-container {{ max-width: 900px; margin: 0 auto; padding: 0 2rem; display: flex; justify-content: space-between; align-items: center; }}
        .nav a {{ font-weight: 600; }}
        .breadcrumbs {{ max-width: 900px; margin: 0 auto; padding: 1rem 2rem; font-size: 0.9rem; }}
        .breadcrumbs a {{ color: var(--charcoal-light); }} .breadcrumbs span {{ color: var(--charcoal-light); margin: 0 0.5rem; }}
        .breadcrumbs .current {{ color: var(--navy); font-weight: 500; }}
        .hero-image {{ width: 100%; max-height: 450px; object-fit: cover; }}
        .article-header {{ background: linear-gradient(135deg, var(--navy) 0%, var(--navy-light) 100%); color: var(--white); padding: 3rem 2rem; text-align: center; }}
        .article-header h1 {{ max-width: 800px; margin: 0 auto 1rem; font-size: 2.25rem; color: var(--white); }}
        .article-meta {{ font-size: 1rem; opacity: 0.9; }}
        .article-container {{ max-width: 750px; margin: 0 auto; padding: 3rem 2rem; background: var(--white); }}
        .article-content h2 {{ font-size: 1.6rem; margin: 2.5rem 0 1rem; }} .article-content p {{ margin-bottom: 1.5rem; }}
        .article-content ul, .article-content ol {{ margin: 1.5rem 0; padding-left: 2rem; }} .article-content li {{ margin-bottom: 0.75rem; }}
        .article-image {{ width: 100%; margin: 2rem 0; border-radius: 12px; overflow: hidden; }}
        .article-image img {{ width: 100%; height: auto; display: block; }}
        .article-image figcaption {{ font-size: 0.9rem; color: var(--charcoal-light); text-align: center; padding: 0.75rem 1rem; background: var(--cream); font-style: italic; }}
        .video-container {{ position: relative; width: 100%; padding-bottom: 56.25%; height: 0; margin: 2rem 0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
        .video-container iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; }}
        .video-caption {{ font-size: 0.9rem; color: var(--charcoal-light); text-align: center; padding: 0.75rem; font-style: italic; }}
        .cta-box {{ background: linear-gradient(135deg, var(--teal) 0%, var(--teal-dark) 100%); color: var(--white); padding: 2rem; border-radius: 12px; text-align: center; margin: 2.5rem 0; }}
        .cta-box h3 {{ margin-bottom: 0.75rem; font-size: 1.35rem; color: var(--white); }}
        .cta-box p {{ color: rgba(255,255,255,0.9) !important; margin-bottom: 1rem; }}
        .cta-button {{ display: inline-block; background: var(--white); color: var(--teal); padding: 0.875rem 2rem; border-radius: 8px; text-decoration: none; font-weight: 600; }}
        .cta-button:hover {{ opacity: 0.9; text-decoration: none; transform: translateY(-2px); }}
        .back-to-blog {{ max-width: 750px; margin: 0 auto; padding: 1.5rem 2rem; text-align: center; background: var(--white); }}
        .footer {{ text-align: center; padding: 2rem; color: var(--charcoal-light); font-size: 0.9rem; background: var(--white); border-top: 1px solid rgba(30,58,95,0.1); }}
        @media (max-width: 768px) {{ .article-header h1 {{ font-size: 1.75rem; }} .article-header {{ padding: 2rem 1.5rem; }} .article-container {{ padding: 2rem 1.5rem; }} .hero-image {{ max-height: 280px; }} }}
    </style>
</head>
<body>
    <nav class="nav"><div class="nav-container"><a href="index.html">&larr; Back to Blog</a><a href="{website_url}">SteadiDay Home</a></div></nav>
    <div class="breadcrumbs"><a href="../index.html">Home</a><span>&rsaquo;</span><a href="index.html">Blog</a><span>&rsaquo;</span><span class="current">{title}</span></div>
    <img src="{hero_image}" alt="{title}" class="hero-image" loading="eager">
    <header class="article-header"><h1>{title}</h1><div class="article-meta">{formatted_date} &bull; By SteadiDay Team &bull; {read_time} min read</div></header>
    <article class="article-container"><div class="article-content">
        {content}
        <div class="cta-box"><h3>Ready to Take Control of Your Daily Wellness?</h3><p>SteadiDay helps you manage medications, track your health, and stay connected with loved ones. Every feature is completely free.</p><a href="{app_store_url}" class="cta-button">Download Free on the App Store</a></div>
    </div></article>
    <div class="back-to-blog"><a href="index.html">&larr; See all blog posts</a></div>
    <footer class="footer"><p>&copy; {year} SCM Solutions LLC. | <a href="{website_url}">Home</a> | <a href="{website_url}/privacy.html">Privacy</a> | <a href="{website_url}/terms.html">Terms</a></p></footer>
<!-- GTAG_CONVERSION_INJECTED -->
<!-- Google Ads: App Store click conversion tracking -->
<script>
  document.addEventListener('DOMContentLoaded', function() {{
    var links = document.querySelectorAll('a[href*="apps.apple.com"]');
    links.forEach(function(link) {{
      link.addEventListener('click', function() {{
        gtag('event', 'conversion', {{
          'send_to': 'AW-17929124014/gDbcCLbkio4cEK7xouVC',
          'value': 1.0,
          'currency': 'USD'
        }});
      }});
    }});
  }});
</script>
</body>
</html>
'''

def get_images_for_category(category):
hero_options = HERO_IMAGES.get(category, HERO_IMAGES[‘Wellness’])
inline_options = INLINE_IMAGES.get(category, INLINE_IMAGES[‘Wellness’])
n = random.choice([4, 5])
return {
“hero”: random.choice(hero_options),
“inline”: random.sample(inline_options, min(n, len(inline_options)))
}

def get_video_for_category(category):
return random.choice(CATEGORY_VIDEOS.get(category, CATEGORY_VIDEOS[‘Wellness’]))

def verify_youtube_video(video_id):
“”“Check if a YouTube video is publicly available using the oEmbed API.
Returns True if available, False if unavailable/private/deleted.”””
url = f”https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json”
try:
req = urllib.request.Request(url, headers={“User-Agent”: “Mozilla/5.0”})
with urllib.request.urlopen(req, timeout=10) as resp:
return resp.status == 200
except urllib.error.HTTPError:
return False
except Exception as e:
print(f”  Video verification request failed: {e}”)
# If we can’t reach YouTube to verify, assume it’s okay rather than blocking
return True

def find_youtube_video(client, topic, category):
“”“Use Claude with web search to find a current, working YouTube video.”””
prompt = f””“Find ONE YouTube video that is relevant to this blog topic: “{topic}”
Category: {category}

The video should be:

- From a reputable health/wellness channel (e.g., Mayo Clinic, Cleveland Clinic, AARP, SilverSneakers, Bob & Brad, Harvard Health, WebMD, Physiotutors, HASfit)
- Educational and appropriate for adults 50+
- Currently available on YouTube (not removed or private)
- Under 15 minutes long

Search YouTube for a relevant video and return ONLY this format with no other text:
VIDEO_ID: [the 11-character YouTube video ID from the URL]
VIDEO_TITLE: [exact title of the video]
VIDEO_CHANNEL: [channel name]

If you cannot find a suitable video, return exactly:
VIDEO_ID: NONE”””

```
try:
    msg = call_with_retry(lambda: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    ))
    response_text = ""
    for block in msg.content:
        if hasattr(block, 'text'):
            response_text += block.text
    vid_match = re.search(r'VIDEO_ID:\s*(\S+)', response_text)
    title_match = re.search(r'VIDEO_TITLE:\s*(.+?)(?:\n|$)', response_text)
    channel_match = re.search(r'VIDEO_CHANNEL:\s*(.+?)(?:\n|$)', response_text)
    if vid_match and vid_match.group(1).strip() != "NONE":
        video_id = vid_match.group(1).strip()
        if 10 <= len(video_id) <= 12:
            # Verify the video is actually available before using it
            if verify_youtube_video(video_id):
                return {
                    "id": video_id,
                    "title": title_match.group(1).strip() if title_match else "Health & Wellness Tips",
                    "channel": channel_match.group(1).strip() if channel_match else "Health Channel"
                }
            else:
                print(f"  Dynamic video {video_id} is unavailable, using fallback")
    print("  Could not find a dynamic video, using fallback")
except Exception as e:
    print(f"  Video search failed: {e}, using fallback")
return None
```

def select_unique_topic(existing_posts):
“”“Select a topic from the pool that hasn’t been covered yet.”””
random.shuffle(TOPIC_CATEGORIES)
for td in TOPIC_CATEGORIES:
slug_words = re.sub(r’[^a-z0-9\s]’, ‘’, td[‘topic’].lower()).split()[:5]
test_slug = ‘-’.join(slug_words)
dup, reason, match = is_duplicate(td[‘topic’], test_slug, existing_posts)
if not dup:
return td
return None

def generate_blog_post(topic_data, existing_posts, client):
“”“Generate blog post content using Claude.”””
topic = topic_data[“topic”]
keyword = topic_data[“keyword”]
category = topic_data.get(“category”, “Wellness”)

```
images = get_images_for_category(category)
print("  Searching for relevant YouTube video...")
video = find_youtube_video(client, topic, category)
if video is None:
    # Try fallback videos, verifying each one is still available
    fallback_videos = CATEGORY_VIDEOS.get(category, CATEGORY_VIDEOS['Wellness'])[:]
    random.shuffle(fallback_videos)
    for fallback in fallback_videos:
        if verify_youtube_video(fallback["id"]):
            video = fallback
            print(f"  Using verified fallback video: {video['title']}")
            break
        else:
            print(f"  Fallback video '{fallback['title']}' ({fallback['id']}) is unavailable, skipping")
    if video is None:
        print("  No working video found. Blog will be published without a video.")
else:
    print(f"  Found video: {video['title']} by {video['channel']}")
num_images = len(images["inline"])
feature = random.choice(STEADIDAY_FEATURES["free"])

img_ph = "\n".join([f"After section {i+2}, insert exactly: [IMAGE_{i+1}]" for i in range(num_images)])

existing_titles = [p['title'] for p in existing_posts if p['title']]
avoid = "\n".join([f"- {t}" for t in existing_titles[:20]]) if existing_titles else "None."

angle_instruction = ""
if topic_data.get('angle'):
    angle_instruction = f"\nANGLE TO TAKE: {topic_data['angle']}"
if topic_data.get('source'):
    angle_instruction += f"\nREFERENCE SOURCE: {topic_data['source']}"

prompt = f"""You are a health and wellness content writer for SteadiDay, an app for adults 50+.
```

Write a blog post about: “{topic}”
{angle_instruction}
CRITICAL: Must be UNIQUE. Do NOT overlap with these existing posts:
{avoid}

REQUIREMENTS:

1. TITLE under 55 characters, clearly different from existing posts
1. 1000-1500 words, warm conversational tone, 6-7 sections with <h2> tags
1. Mention SteadiDay’s {feature} feature naturally (all features are free)
1. Include at least one specific statistic with its source
1. Write for adults 50+ – practical, respectful, empowering

MEDIA PLACEHOLDERS:
{img_ph}
After section 4: [VIDEO]

FORMAT:
TITLE: [under 55 chars]
META_DESCRIPTION: [150-160 chars]
KEYWORDS: keyword1, keyword2, {keyword}
READ_TIME: X
CONTENT:

<p>Opening paragraph...</p>
<h2>Section Title</h2>
<p>Content...</p>"""

```
msg = call_with_retry(lambda: client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4500,
    messages=[{"role": "user", "content": prompt}]
))
r = msg.content[0].text

title_match = re.search(r'TITLE:\s*(.+?)(?:\n|$)', r)
title = title_match.group(1).strip() if title_match else topic
meta_match = re.search(r'META_DESCRIPTION:\s*(.+?)(?:\n|$)', r)
meta = meta_match.group(1).strip() if meta_match else f"Tips about {topic} for adults 50+"
kws_match = re.search(r'KEYWORDS:\s*(.+?)(?:\n|$)', r)
kws = kws_match.group(1).strip() if kws_match else keyword
rt_match = re.search(r'READ_TIME:\s*(\d+)', r)
rt = rt_match.group(1) if rt_match else "7"
content_match = re.search(r'CONTENT:\s*(.+)', r, re.DOTALL)
content = content_match.group(1).strip() if content_match else r

if len(title) > 55:
    title = title[:52].rsplit(' ', 1)[0] + "..."

for i, img in enumerate(images["inline"]):
    content = content.replace(
        f"[IMAGE_{i+1}]",
        f'<figure class="article-image"><img src="{img["url"]}" alt="{img["alt"]}" loading="lazy"><figcaption>{img["alt"]}</figcaption></figure>'
    )

if video:
    content = content.replace(
        "[VIDEO]",
        f'<div class="video-container"><iframe src="https://www.youtube.com/embed/{video["id"]}" title="{video["title"]}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div><p class="video-caption">Video: {video["title"]} -- {video["channel"]}</p>'
    )

content = re.sub(r'\[IMAGE_\d+\]', '', content)
content = content.replace("[VIDEO]", '')

slug = '-'.join(re.sub(r'[^a-z0-9\s]', '', title.lower()).split()[:5])

return {
    "title": title,
    "meta_description": meta,
    "keywords": kws,
    "read_time": rt,
    "content": content,
    "slug": slug,
    "category": category,
    "hero_image": images["hero"],
    "video": video,
    "num_images": num_images,
    "date": datetime.now().strftime('%Y-%m-%d'),
}
```

def create_blog_html(post_data):
“”“Render the blog post HTML from template.”””
template = get_html_template()
fn = f”{post_data[‘date’]}-{post_data[‘slug’]}.html”
curl = f”{BLOG_BASE_URL}/{fn}”
d = datetime.strptime(post_data[‘date’], ‘%Y-%m-%d’)
html = template.format(
title=post_data[‘title’],
meta_description=post_data[‘meta_description’],
keywords=post_data[‘keywords’],
canonical_url=curl,
website_url=WEBSITE_URL,
app_store_url=APP_STORE_URL,
hero_image=post_data[‘hero_image’],
iso_date=d.isoformat(),
formatted_date=d.strftime(’%B %d, %Y’),
read_time=post_data[‘read_time’],
content=post_data[‘content’],
year=datetime.now().year,
)
return html, fn

def update_blog_index(post_data, filename):
“”“Add the new post to the blog index page.”””
path = “blog/index.html”
if not os.path.exists(path):
print(f”Warning: {path} not found”)
return False
with open(path, ‘r’, encoding=‘utf-8’) as f:
content = f.read()
cat = post_data.get(‘category’, ‘Wellness’)
img = CATEGORY_IMAGES.get(cat, CATEGORY_IMAGES[‘Wellness’])
d = datetime.strptime(post_data[‘date’], ‘%Y-%m-%d’).strftime(’%B %d, %Y’)
entry = f’’’<article class="blog-card">
<div class="blog-card-image" style="background-image: url('{img}');"><span class="blog-card-tag">{cat}</span></div>
<div class="blog-card-content">
<h2><a href="{filename}">{post_data[‘title’]}</a></h2>
<div class="blog-meta"><span>{d}</span><span>*</span><span>{post_data[‘read_time’]} min read</span></div>
<p class="blog-excerpt">{post_data[‘meta_description’]}</p>
<a href="{filename}" class="read-more">Read full article<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg></a>
</div></article>\n            ‘’’
marker = “<!--BLOG_ENTRIES_START-->”
if marker in content:
if ‘class=“blog-card featured”’ in content:
content = content.replace(‘class=“blog-card featured”’, ‘class=“blog-card”’, 1)
entry = entry.replace(‘class=“blog-card”’, ‘class=“blog-card featured”’)
content = content.replace(marker, marker + “\n            “ + entry)
with open(path, ‘w’, encoding=‘utf-8’) as f:
f.write(content)
print(f”Updated {path}”)
return True
print(f”Warning: marker not found in {path}”)
return False

def generate_rss_feed(blog_dir=“blog”):
“”“Generate/update blog/rss.xml from existing blog posts.”””
rss_path = os.path.join(blog_dir, “rss.xml”)
if not os.path.exists(blog_dir):
print(f”  Warning: {blog_dir} not found. Skipping RSS generation.”)
return
posts = []
for fname in sorted(os.listdir(blog_dir), reverse=True):
if fname.endswith(’.html’) and fname != ‘index.html’:
filepath = os.path.join(blog_dir, fname)
try:
if os.path.getsize(filepath) < 1024:
continue
except OSError:
continue
try:
with open(filepath, ‘r’, encoding=‘utf-8’) as f:
content = f.read(5000)
except Exception:
continue
title_match = re.search(r’<title>(.*?)\s*|’, content)
title = title_match.group(1).strip() if title_match else fname
desc_match = re.search(r’<meta\s+name=“description”\s+content=”(.*?)”’, content)
description = desc_match.group(1) if desc_match else “”
date_match = re.match(r’(\d{4}-\d{2}-\d{2})’, fname)
if date_match:
date_str = date_match.group(1)
date_obj = datetime.strptime(date_str, ‘%Y-%m-%d’)
pub_date = date_obj.strftime(’%a, %d %b %Y 00:00:00 GMT’)
else:
pub_date = “”
canonical_url = f”{BLOG_BASE_URL}/{fname}”
posts.append({‘title’: title, ‘description’: description, ‘url’: canonical_url, ‘pub_date’: pub_date})
posts = posts[:20]
now = datetime.utcnow().strftime(’%a, %d %b %Y %H:%M:%S GMT’)
items_xml = “”
for post in posts:
safe_title = post[‘title’].replace(’&’, ‘&’).replace(’<’, ‘<’).replace(’>’, ‘>’)
safe_desc = post[‘description’].replace(’&’, ‘&’).replace(’<’, ‘<’).replace(’>’, ‘>’)
items_xml += f”””
<item>
<title>{safe_title}</title>
<link>{post[‘url’]}</link>
<guid isPermaLink="true">{post[‘url’]}</guid>
<description>{safe_desc}</description>
<pubDate>{post[‘pub_date’]}</pubDate>
</item>”””
rss_xml = f”””<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>SteadiDay Blog – Health & Wellness for Adults 50+</title>
<link>{WEBSITE_URL}/blog/index.html</link>
<description>Health and wellness tips for adults 50+. Expert advice on medication management, heart health, sleep, exercise, nutrition and mental wellness from the SteadiDay team.</description>
<language>en-us</language>
<lastBuildDate>{now}</lastBuildDate>
<atom:link href=”{WEBSITE_URL}/blog/rss.xml” rel=“self” type=“application/rss+xml” />
<image>
<url>{WEBSITE_URL}/assets/icon.jpeg</url>
<title>SteadiDay Blog</title>
<link>{WEBSITE_URL}/blog/index.html</link>
</image>{items_xml}
</channel>
</rss>”””
with open(rss_path, ‘w’, encoding=‘utf-8’) as f:
f.write(rss_xml)
print(f”  RSS feed updated: {rss_path} ({len(posts)} posts)”)

def notify_buttondown(post_data, filename):
“”“Draft a Buttondown email notification for the new blog post.”””
api_key = os.environ.get(‘BUTTONDOWN_API_KEY’)
if not api_key:
print(”  BUTTONDOWN_API_KEY not set. Skipping email notification.”)
return
canonical_url = f”{BLOG_BASE_URL}/{filename}”
email_body = f”””# {post_data[‘title’]}

{post_data[‘meta_description’]}

**[Read the full article ->]({canonical_url})**

-----

*You’re receiving this because you subscribed to the SteadiDay Health & Wellness newsletter. New articles are published every Monday and Thursday.*

*[Download SteadiDay free on the App Store]({APP_STORE_URL})*
“””
payload = json.dumps({
“subject”: f”New on SteadiDay: {post_data[‘title’]}”,
“body”: email_body,
“status”: “draft”
}).encode(‘utf-8’)
req = urllib.request.Request(
“https://api.buttondown.com/v1/emails”,
data=payload,
headers={
“Authorization”: f”Token {api_key}”,
“Content-Type”: “application/json”
},
method=“POST”
)
try:
with urllib.request.urlopen(req) as response:
if response.status in (200, 201):
print(”  Buttondown draft created! Review and send at https://buttondown.com/emails”)
else:
print(f”  Buttondown returned status {response.status}”)
except urllib.error.HTTPError as e:
print(f”  Buttondown API error {e.code}: {e.reason}”)
except Exception as e:
print(f”  Buttondown notification failed: {e}”)

def save_blog_post(html, filename):
“”“Save blog post HTML file.”””
os.makedirs(“blog”, exist_ok=True)
fp = os.path.join(“blog”, filename)
with open(fp, ‘w’, encoding=‘utf-8’) as f:
f.write(html)
return fp

def set_github_env(key, value):
“”“Set GitHub Actions environment variable.”””
ef = os.environ.get(‘GITHUB_ENV’)
if ef:
with open(ef, ‘a’) as f:
f.write(f”{key}={value}\n”)
else:
print(f”[ENV] {key}={value}”)

def main():
topic_override = None
use_news = False
if len(sys.argv) > 1:
arg = sys.argv[1].strip()
if arg == “–news”:
use_news = True
elif arg:
topic_override = arg
if len(sys.argv) > 2 and sys.argv[2].strip() == “–news”:
use_news = True

```
print("=" * 60)
print("SteadiDay Blog Generator v3.5")
print("=" * 60)
print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
print(f"Mode: {'Custom topic' if topic_override else 'News-driven' if use_news else 'Topic pool'}")
print(f"URL: {WEBSITE_URL}\n")

print("Scanning existing posts...")
existing = get_existing_posts()
print(f"Found {len(existing)} existing posts")
for p in existing:
    print(f"  - {p['title'] or p['filename']}")
print()

client = anthropic.Anthropic()

if topic_override:
    print(f"Custom topic: {topic_override}")
    td = {"topic": topic_override, "keyword": topic_override.lower(), "category": "Wellness"}
elif use_news:
    print("Generating news-driven topic (with web search)...")
    td = generate_news_driven_topic(client, existing)
    print(f"  Topic: {td['topic']}")
    print(f"  Category: {td['category']}")
    if td.get('angle'):
        print(f"  Angle: {td['angle']}")
    if td.get('source'):
        print(f"  Source: {td['source']}")
else:
    print("Selecting unique topic from pool...")
    td = select_unique_topic(existing)
    if td is None:
        print("All pool topics used! Switching to news-driven...")
        td = generate_news_driven_topic(client, existing)
    else:
        print(f"  Selected: {td['topic']}")
        print(f"  Category: {td['category']}")

print("\nGenerating content...")
post = generate_blog_post(td, existing, client)

slug = '-'.join(re.sub(r'[^a-z0-9\s]', '', post['title'].lower()).split()[:5])
dup, reason, match = is_duplicate(post['title'], slug, existing)
if not dup:
    sem_dup, sem_reason = check_semantic_duplicate(client, post['title'], existing)
    if sem_dup:
        dup = True
        reason = sem_reason

if dup:
    print(f"  Duplicate detected: {reason}")
    print("  Retrying with news-driven topic...")
    td = generate_news_driven_topic(client, existing)
    post = generate_blog_post(td, existing, client)
    slug = '-'.join(re.sub(r'[^a-z0-9\s]', '', post['title'].lower()).split()[:5])
    dup2, r2, s2 = is_duplicate(post['title'], slug, existing)
    if not dup2:
        sem_dup2, sem_r2 = check_semantic_duplicate(client, post['title'], existing)
        if sem_dup2:
            dup2 = True
            r2 = sem_r2
    if dup2:
        print(f"  Still duplicate: {r2}")
        print("  Please provide a custom topic.")
        sys.exit(1)

print(f"\n  Title: {post['title']} ({len(post['title'])} chars)")
print(f"  Duplicate check: PASS")

html, fn = create_blog_html(post)
print(f"  File: {fn}")

fp = save_blog_post(html, fn)
print(f"  Saved: {fp}\n")

update_blog_index(post, fn)

print("\nGenerating RSS feed...")
generate_rss_feed()

print("\nCreating Buttondown email draft...")
notify_buttondown(post, fn)

set_github_env("BLOG_TITLE", post['title'])
set_github_env("BLOG_FILENAME", fn)
set_github_env("BLOG_DATE", post['date'])

print(f"\nDone! Published: {post['title']}")
print(f"\nUsage:")
print(f"  python generate_blog.py              # Random unique topic from pool")
print(f"  python generate_blog.py --news       # News-driven topic (uses web search)")
print(f'  python generate_blog.py "Your topic"  # Custom topic')
```

if **name** == “**main**”:
main()