#!/usr/bin/env python3
"""
SteadiDay Blog Generator v5.0
Major expansion from v4.2:
- 3 new categories: Technology, Chronic Conditions, Relationships (13 total)
- 120+ topics (up from ~60)
- 6 writing styles randomly assigned per post for structural variety
- Improved news-driven generation with better source specificity
- Evidence-based only — no political opinions
- Expanded image and video pools across all categories
- All v4.2 features retained
"""

import anthropic
from anthropic import APIStatusError
import random, re, os, sys, glob, json, time, urllib.request
from datetime import datetime, timedelta
from difflib import SequenceMatcher

CLAUDE_MODEL = "claude-sonnet-4-6"
WEBSITE_URL = "https://www.steadiday.com"
BLOG_BASE_URL = f"{WEBSITE_URL}/blog"
APP_STORE_URL = "https://apps.apple.com/app/steadiday/id6758526744"
CATEGORY_COOLDOWN_WINDOW = 4

VALID_CATEGORIES = [
    "Mental Wellness", "Medication Tips", "Healthy Aging", "Exercise",
    "Nutrition", "Sleep", "Heart Health", "Brain Health", "Safety",
    "Wellness", "Technology", "Chronic Conditions", "Relationships",
    "Women's Health", "Men's Health", "Preventive Care",
]

WRITING_STYLES = [
    {"name": "narrative", "instruction": """WRITING STYLE: Open with a short, vivid scene or anecdote (you can invent a composite character like "When Maria, 62, noticed..."). Weave practical advice into the story. Use transitions like "Here's the thing..." or "What surprised researchers was..." to move between sections. Close by returning to the opening character or scene. Do NOT use bullet points for the main advice — embed it in flowing paragraphs. This should read like a magazine feature, not a how-to list."""},
    {"name": "myth_busting", "instruction": """WRITING STYLE: Structure this as a myth-busting piece. Open with "You've probably heard that..." and then challenge 4-5 common misconceptions about the topic. Each section should be framed as a common belief followed by the evidence-based reality. Use a conversational, slightly surprising tone. Close with a clear "bottom line" takeaway."""},
    {"name": "qa_format", "instruction": """WRITING STYLE: Frame this as answering real questions people ask their doctors. Open with "These are the questions we hear most often about [topic]." Each section heading should be a specific question in natural language (e.g., "Is it normal to wake up at 3 AM every night?"). Answer each question directly in the first sentence, then expand with evidence and practical steps."""},
    {"name": "day_in_life", "instruction": """WRITING STYLE: Walk through a typical day showing where the topic fits into real life. Open with a morning scenario and move through the day chronologically. Each section is a time of day with practical, specific advice woven in. This should feel like a friend sharing their routine, not a lecture."""},
    {"name": "news_hook", "instruction": """WRITING STYLE: Open with a recent finding, guideline change, or health news item related to the topic (reference a real source if possible). Use the news as a hook to explain what changed, why it matters for adults 50+, and what to do about it. Sections should progress: what happened, why it matters, what the evidence says, what you can do today. This should read like health journalism, not a pamphlet."""},
    {"name": "lessons_learned", "instruction": """WRITING STYLE: Frame this as practical lessons — "5 things I wish I'd known about [topic] sooner." Use first-person plural ("we") to create warmth. Each section is a genuine insight, not obvious advice. Include at least one counterintuitive point. Use phrases like "What most people get wrong is..." This should feel like wisdom from someone who's been through it."""},
]


def call_with_retry(func, max_retries=7, base_delay=30):
    for attempt in range(max_retries + 1):
        try:
            return func()
        except APIStatusError as e:
            if e.status_code in (429, 529) or e.status_code >= 500:
                if attempt == max_retries:
                    raise
                delay = base_delay * (2 ** attempt)
                print(f"  API error {e.status_code} (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def get_existing_posts(blog_dir="blog"):
    existing = []
    if not os.path.exists(blog_dir):
        return existing
    for filepath in glob.glob(os.path.join(blog_dir, "*.html")):
        filename = os.path.basename(filepath)
        if filename == "index.html":
            continue
        try:
            if os.path.getsize(filepath) < 1024:
                continue
        except OSError:
            pass
        title = category = meta_desc = date_str = ""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(8000)
                m = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
                if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                cat_m = re.search(r'class="blog-card-tag">([^<]+)<', content)
                if cat_m: category = cat_m.group(1).strip()
                desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', content)
                if desc_m: meta_desc = desc_m.group(1).strip()
        except Exception:
            pass
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', filename)
        if date_match: date_str = date_match.group(1)
        slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', filename.replace('.html', ''))
        existing.append({"filename": filename, "title": title, "slug": slug, "category": category, "meta_desc": meta_desc, "date": date_str})
    existing.sort(key=lambda p: p.get('date', ''), reverse=True)
    return existing


def normalize_text(text):
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return re.sub(r'\s+', ' ', text)


def get_content_words(text):
    stop = {'the','a','an','for','and','or','to','of','in','your','how','that','with','after','from','is','are','was','were','be','been','being','have','has','had','do','does','did','will','would','could','should','may','might','can','this','these','those','it','its','you','we','they','them','our','my','me','what','which','who','whom','when','where','why','not','no','so','if','but','as','at','by','on','up','about','into','over','than','then','too','very','just','also','more','most','some','any','all','each','every','simple','easy','best','top','guide','tips','ways','adults','seniors','50','over','after','really','complete','natural','naturally','better','healthy','health','improve'}
    return set(normalize_text(text).split()) - stop


def is_duplicate(new_title, new_slug, existing_posts, threshold_title=0.55, threshold_slug=0.65):
    ntl, nsl = normalize_text(new_title), normalize_text(new_slug)
    for post in existing_posts:
        etl, esl = normalize_text(post['title']), normalize_text(post['slug'])
        if SequenceMatcher(None, ntl, etl).ratio() >= threshold_title:
            return (True, f"Title similarity {SequenceMatcher(None, ntl, etl).ratio():.2f}", post['filename'])
        if SequenceMatcher(None, nsl, esl).ratio() >= threshold_slug:
            return (True, f"Slug similarity {SequenceMatcher(None, nsl, esl).ratio():.2f}", post['filename'])
        new_words, existing_words = get_content_words(new_title), get_content_words(post['title'])
        if new_words and existing_words:
            overlap = new_words & existing_words
            min_len = min(len(new_words), len(existing_words))
            if min_len > 0 and len(overlap) >= 2 and len(overlap) / min_len >= 0.6:
                return (True, f"Keyword overlap ({overlap})", post['filename'])
    return (False, "", "")


def check_semantic_duplicate(client, new_title, existing_posts):
    if not existing_posts:
        return False, ""
    existing_info = [p['title'] + (f" — {p['meta_desc']}" if p.get('meta_desc') else "") for p in existing_posts if p['title']]
    if not existing_info:
        return False, ""
    posts_list = "\n".join([f"- {info}" for info in existing_info[:25]])
    prompt = f"""You are a blog content deduplication checker. Be STRICT about catching thematic overlap.

PROPOSED NEW POST TITLE: "{new_title}"

EXISTING POSTS (title + summary):
{posts_list}

Would the proposed post cover substantially the same ground as any existing post?
Reply with ONLY: UNIQUE or DUPLICATE OF: [existing title]"""

    msg = call_with_retry(lambda: client.messages.create(model=CLAUDE_MODEL, max_tokens=200, messages=[{"role": "user", "content": prompt}]))
    result = msg.content[0].text.strip()
    return (True, result) if result.startswith("DUPLICATE") else (False, "")


def get_recent_categories(existing_posts, window=CATEGORY_COOLDOWN_WINDOW):
    return [post.get('category', '') for post in existing_posts[:window] if post.get('category')]


def get_content_summaries(existing_posts, limit=15):
    summaries = [f"- [{p.get('category', 'Wellness')}] \"{p['title']}\"" + (f" — {p['meta_desc']}" if p.get('meta_desc') else "") for p in existing_posts[:limit] if p['title']]
    return "\n".join(summaries) if summaries else "None yet."


def generate_news_driven_topic(client, existing_posts, excluded_categories=None):
    content_summaries = get_content_summaries(existing_posts)
    month, year = datetime.now().strftime('%B'), datetime.now().strftime('%Y')
    category_note = f"\nDO NOT use these categories (used recently): {', '.join(excluded_categories)}" if excluded_categories else ""

    prompt = f"""Search for health news, medical studies, or updated clinical guidelines published
in the last 2 weeks (it is currently {month} {year}) that are relevant to adults over 50.

Good sources: NIH, CDC, Mayo Clinic, AARP, JAMA, The Lancet, NEJM, BMJ, Harvard Health,
Johns Hopkins, WHO, FDA, AHA, Alzheimer's Association.

Find a SPECIFIC, RECENT story — not evergreen advice. Good hooks include: new study findings,
updated treatment guidelines, seasonal health alerts, new FDA actions, public health trends.

EXISTING POSTS (do NOT duplicate):
{content_summaries}
{category_note}

Frame the topic through "what this means for your daily life." Present only evidence-based,
factual information — no political opinions or editorial commentary.

FORMAT:
TOPIC: [specific description referencing the actual study/guideline]
TITLE: [under 55 characters, compelling not clinical]
KEYWORD: [primary SEO keyword phrase]
CATEGORY: [exactly one of: {"|".join(VALID_CATEGORIES)}]
ANGLE: [what makes this timely — cite the specific source and date]
SOURCE: [the news source, journal, or organization]"""

    msg = call_with_retry(lambda: client.messages.create(model=CLAUDE_MODEL, max_tokens=1000, tools=[{"type": "web_search_20250305", "name": "web_search"}], messages=[{"role": "user", "content": prompt}]))
    response_text = "".join(block.text for block in msg.content if hasattr(block, 'text'))
    topic = re.search(r'TOPIC:\s*(.+?)(?:\n|$)', response_text)
    title = re.search(r'TITLE:\s*(.+?)(?:\n|$)', response_text)
    kw = re.search(r'KEYWORD:\s*(.+?)(?:\n|$)', response_text)
    cat = re.search(r'CATEGORY:\s*(.+?)(?:\n|$)', response_text)
    angle = re.search(r'ANGLE:\s*(.+?)(?:\n|$)', response_text)
    source = re.search(r'SOURCE:\s*(.+?)(?:\n|$)', response_text)
    c = cat.group(1).strip() if cat else "Wellness"
    if c not in VALID_CATEGORIES: c = "Wellness"
    result = {"topic": topic.group(1).strip() if topic else "Health tips for adults 50+", "keyword": kw.group(1).strip() if kw else "health tips seniors", "category": c, "suggested_title": title.group(1).strip() if title else "", "angle": angle.group(1).strip() if angle else "", "source": source.group(1).strip() if source else ""}
    print(f"  News source: {result.get('source', 'N/A')}")
    return result


# =============================================================================
# TOPIC POOL — 120+ topics across 13 categories
# =============================================================================
TOPIC_CATEGORIES = [
    # EXERCISE
    {"topic": "Chair exercises you can do while watching TV", "keyword": "chair exercises seniors", "category": "Exercise"},
    {"topic": "Balance exercises to prevent falls at home", "keyword": "balance exercises seniors", "category": "Exercise"},
    {"topic": "Gentle yoga poses for beginners over 50", "keyword": "yoga seniors beginners", "category": "Exercise"},
    {"topic": "Walking for health: getting started safely", "keyword": "walking exercise seniors", "category": "Exercise"},
    {"topic": "Swimming and water aerobics for low-impact fitness", "keyword": "water aerobics seniors", "category": "Exercise"},
    {"topic": "Resistance band workouts you can do at home", "keyword": "resistance band exercises seniors", "category": "Exercise"},
    {"topic": "Tai chi for balance, calm, and flexibility", "keyword": "tai chi seniors benefits", "category": "Exercise"},
    {"topic": "How to start strength training after 50", "keyword": "strength training over 50", "category": "Exercise"},
    {"topic": "Stretching routines to ease morning stiffness", "keyword": "morning stretching seniors", "category": "Exercise"},
    {"topic": "Pickleball: why it's booming with older adults", "keyword": "pickleball seniors health", "category": "Exercise"},
    {"topic": "How much exercise do you actually need each week", "keyword": "exercise guidelines seniors", "category": "Exercise"},
    # MEDICATION TIPS
    {"topic": "How to build a medication routine that sticks", "keyword": "medication routine tips", "category": "Medication Tips"},
    {"topic": "Understanding common medication side effects", "keyword": "medication side effects", "category": "Medication Tips"},
    {"topic": "Questions to ask your pharmacist at every visit", "keyword": "pharmacist questions seniors", "category": "Medication Tips"},
    {"topic": "How to safely store medications at home", "keyword": "medication storage tips", "category": "Medication Tips"},
    {"topic": "Traveling with medications: what you need to know", "keyword": "traveling with medications tips", "category": "Medication Tips"},
    {"topic": "Why medication reviews matter as you age", "keyword": "medication review seniors", "category": "Medication Tips"},
    {"topic": "Over-the-counter drugs that can interact with prescriptions", "keyword": "OTC drug interactions seniors", "category": "Medication Tips"},
    {"topic": "How to talk to your doctor about medication costs", "keyword": "medication cost savings seniors", "category": "Medication Tips"},
    {"topic": "Generic vs brand-name medications: what to know", "keyword": "generic medications seniors", "category": "Medication Tips"},
    # HEART HEALTH
    {"topic": "Foods that naturally lower cholesterol", "keyword": "lower cholesterol naturally", "category": "Heart Health"},
    {"topic": "Warning signs your heart needs attention", "keyword": "heart warning signs seniors", "category": "Heart Health"},
    {"topic": "Understanding atrial fibrillation after 50", "keyword": "atrial fibrillation seniors", "category": "Heart Health"},
    {"topic": "How stress affects your heart and what to do about it", "keyword": "stress heart health seniors", "category": "Heart Health"},
    {"topic": "The connection between sleep and heart health", "keyword": "sleep heart health connection", "category": "Heart Health"},
    {"topic": "Sodium and your heart: how much is too much", "keyword": "sodium intake heart health", "category": "Heart Health"},
    {"topic": "What your resting heart rate tells you", "keyword": "resting heart rate seniors", "category": "Heart Health"},
    # BRAIN HEALTH
    {"topic": "5 brain exercises to keep your mind sharp", "keyword": "brain exercises seniors", "category": "Brain Health"},
    {"topic": "How social connection protects your brain", "keyword": "social connection brain health", "category": "Brain Health"},
    {"topic": "Learning a new skill after 50 boosts brain health", "keyword": "learning new skill seniors brain", "category": "Brain Health"},
    {"topic": "Early signs of cognitive change vs normal aging", "keyword": "cognitive decline vs normal aging", "category": "Brain Health"},
    {"topic": "Music and the brain: why playing an instrument helps", "keyword": "music brain health seniors", "category": "Brain Health"},
    {"topic": "How bilingualism and language learning protect memory", "keyword": "language learning brain seniors", "category": "Brain Health"},
    {"topic": "The gut-brain connection: how digestion affects thinking", "keyword": "gut brain connection seniors", "category": "Brain Health"},
    {"topic": "Digital brain games: do they actually work", "keyword": "brain games effectiveness seniors", "category": "Brain Health"},
    # NUTRITION
    {"topic": "The importance of staying hydrated as we age", "keyword": "hydration tips elderly", "category": "Nutrition"},
    {"topic": "Healthy snacks for sustained energy after 50", "keyword": "healthy snacks seniors", "category": "Nutrition"},
    {"topic": "Meal planning made simple for one or two", "keyword": "meal planning seniors", "category": "Nutrition"},
    {"topic": "Calcium and vitamin D for strong bones", "keyword": "calcium vitamin D seniors", "category": "Nutrition"},
    {"topic": "How to read nutrition labels like a pro", "keyword": "reading nutrition labels seniors", "category": "Nutrition"},
    {"topic": "Protein needs after 50: how much you really need", "keyword": "protein requirements seniors", "category": "Nutrition"},
    {"topic": "Gut health and probiotics: what the science says", "keyword": "gut health probiotics seniors", "category": "Nutrition"},
    {"topic": "The Mediterranean diet: a beginner's guide", "keyword": "Mediterranean diet seniors guide", "category": "Nutrition"},
    {"topic": "Cooking for one without wasting food", "keyword": "cooking for one seniors", "category": "Nutrition"},
    {"topic": "Fiber: the nutrient most people over 50 are missing", "keyword": "fiber intake seniors", "category": "Nutrition"},
    {"topic": "Anti-inflammatory spices you probably already own", "keyword": "anti-inflammatory spices seniors", "category": "Nutrition"},
    {"topic": "How appetite changes as we age and what to do", "keyword": "appetite changes aging", "category": "Nutrition"},
    # SLEEP
    {"topic": "Why sleep patterns change as we age", "keyword": "sleep changes aging", "category": "Sleep"},
    {"topic": "Creating a bedtime routine that works", "keyword": "bedtime routine seniors", "category": "Sleep"},
    {"topic": "Sleep apnea: signs you should talk to your doctor", "keyword": "sleep apnea signs seniors", "category": "Sleep"},
    {"topic": "Napping: helpful habit or sleep saboteur", "keyword": "napping seniors pros cons", "category": "Sleep"},
    {"topic": "How medications can affect your sleep", "keyword": "medications sleep effects seniors", "category": "Sleep"},
    {"topic": "Restless legs at night: causes and relief", "keyword": "restless legs syndrome seniors", "category": "Sleep"},
    {"topic": "The link between sleep and fall risk", "keyword": "sleep deprivation fall risk seniors", "category": "Sleep"},
    # MENTAL WELLNESS
    {"topic": "Staying social: why connection matters after 60", "keyword": "social connection elderly", "category": "Mental Wellness"},
    {"topic": "Dealing with loneliness after retirement", "keyword": "loneliness retirement seniors", "category": "Mental Wellness"},
    {"topic": "Gratitude journaling for better mental health", "keyword": "gratitude journal seniors", "category": "Mental Wellness"},
    {"topic": "How volunteering boosts your wellbeing", "keyword": "volunteering seniors benefits", "category": "Mental Wellness"},
    {"topic": "Coping with grief and loss as we age", "keyword": "grief coping seniors", "category": "Mental Wellness"},
    {"topic": "Setting boundaries with family and friends", "keyword": "setting boundaries seniors", "category": "Mental Wellness"},
    {"topic": "Finding purpose after retirement", "keyword": "purpose after retirement", "category": "Mental Wellness"},
    {"topic": "Anxiety in older adults: it's more common than you think", "keyword": "anxiety older adults", "category": "Mental Wellness"},
    {"topic": "How nature and outdoor time improve your mood", "keyword": "nature mental health seniors", "category": "Mental Wellness"},
    {"topic": "When worry becomes a health problem", "keyword": "chronic worry seniors health", "category": "Mental Wellness"},
    # SAFETY
    {"topic": "How to prevent falls at home", "keyword": "fall prevention seniors", "category": "Safety"},
    {"topic": "Home safety checklist for aging in place", "keyword": "home safety seniors checklist", "category": "Safety"},
    {"topic": "Staying safe in extreme heat and cold", "keyword": "weather safety seniors", "category": "Safety"},
    {"topic": "Recognizing and avoiding common scams targeting seniors", "keyword": "scam prevention seniors", "category": "Safety"},
    {"topic": "Emergency preparedness for older adults", "keyword": "emergency preparedness seniors", "category": "Safety"},
    {"topic": "Driving safety: when to adjust and when to stop", "keyword": "driving safety seniors", "category": "Safety"},
    {"topic": "Fire safety tips every household needs", "keyword": "fire safety seniors home", "category": "Safety"},
    {"topic": "What to keep in a personal emergency kit", "keyword": "emergency kit seniors", "category": "Safety"},
    {"topic": "Bathroom safety modifications that prevent injuries", "keyword": "bathroom safety seniors", "category": "Safety"},
    # WELLNESS
    {"topic": "Eye health tips to protect your vision", "keyword": "eye health tips seniors", "category": "Wellness"},
    {"topic": "Hearing health and when to get tested", "keyword": "hearing health seniors", "category": "Wellness"},
    {"topic": "Skin care and sun protection after 50", "keyword": "skin care seniors sun protection", "category": "Wellness"},
    {"topic": "Digestive health tips for adults over 50", "keyword": "digestive health seniors", "category": "Wellness"},
    {"topic": "Dental health: protecting your teeth and gums", "keyword": "dental health seniors", "category": "Wellness"},
    {"topic": "Managing arthritis pain with daily habits", "keyword": "arthritis management seniors", "category": "Wellness"},
    {"topic": "Foot care tips for comfort and mobility", "keyword": "foot care seniors", "category": "Wellness"},
    {"topic": "The health benefits of gardening after 50", "keyword": "gardening health benefits seniors", "category": "Wellness"},
    {"topic": "How pets improve health and happiness", "keyword": "pets health benefits seniors", "category": "Wellness"},
    {"topic": "Downsizing and decluttering for peace of mind", "keyword": "downsizing decluttering seniors", "category": "Wellness"},
    {"topic": "Travel tips for healthy adventures after 50", "keyword": "travel health tips seniors", "category": "Wellness"},
    {"topic": "Dry mouth: causes, risks, and what helps", "keyword": "dry mouth seniors causes", "category": "Wellness"},
    {"topic": "Posture matters: simple fixes for back and neck pain", "keyword": "posture improvement seniors", "category": "Wellness"},
    {"topic": "Urinary health: breaking the silence on a common issue", "keyword": "urinary health seniors", "category": "Wellness"},
    # HEALTHY AGING
    {"topic": "What to expect at your annual wellness visit", "keyword": "annual checkup seniors", "category": "Healthy Aging"},
    {"topic": "Navigating Medicare: a beginner-friendly overview", "keyword": "medicare basics seniors", "category": "Healthy Aging"},
    {"topic": "Staying independent: tools and tech that help", "keyword": "independence technology seniors", "category": "Healthy Aging"},
    {"topic": "Caregiving for a loved one: taking care of yourself too", "keyword": "caregiver self care tips", "category": "Healthy Aging"},
    {"topic": "Financial wellness: budgeting in retirement", "keyword": "retirement budget tips seniors", "category": "Healthy Aging"},
    {"topic": "Building a healthcare team you trust", "keyword": "healthcare team seniors", "category": "Healthy Aging"},
    {"topic": "How to talk to your doctor about sensitive topics", "keyword": "doctor communication seniors", "category": "Healthy Aging"},
    {"topic": "Preparing advance directives and health proxies", "keyword": "advance directives planning", "category": "Healthy Aging"},
    {"topic": "Health screenings you shouldn't skip after 50", "keyword": "health screenings over 50", "category": "Healthy Aging"},
    {"topic": "How to choose an assisted living community", "keyword": "assisted living guide seniors", "category": "Healthy Aging"},
    {"topic": "Understanding your blood work results", "keyword": "blood test results explained seniors", "category": "Healthy Aging"},
    # TECHNOLOGY (new)
    {"topic": "Video calling made easy: staying close from far away", "keyword": "video calling seniors guide", "category": "Technology"},
    {"topic": "Telehealth visits: getting the most from virtual appointments", "keyword": "telehealth tips seniors", "category": "Technology"},
    {"topic": "Smartphone accessibility features you should turn on now", "keyword": "smartphone accessibility seniors", "category": "Technology"},
    {"topic": "Smart home devices that support independent living", "keyword": "smart home seniors", "category": "Technology"},
    {"topic": "Protecting yourself from phishing emails and text scams", "keyword": "phishing scam protection seniors", "category": "Technology"},
    {"topic": "Getting started with patient portals and health apps", "keyword": "patient portal guide seniors", "category": "Technology"},
    {"topic": "Wearable health trackers: what's worth monitoring", "keyword": "health tracker seniors", "category": "Technology"},
    {"topic": "How to share photos and stay connected with grandchildren", "keyword": "photo sharing grandparents", "category": "Technology"},
    {"topic": "Voice assistants for reminders, safety, and convenience", "keyword": "voice assistant seniors", "category": "Technology"},
    {"topic": "Online grocery shopping and meal delivery options", "keyword": "online grocery seniors", "category": "Technology"},
    # CHRONIC CONDITIONS (new)
    {"topic": "Living well with type 2 diabetes after 50", "keyword": "type 2 diabetes management seniors", "category": "Chronic Conditions"},
    {"topic": "Managing COPD: breathing easier every day", "keyword": "COPD management seniors", "category": "Chronic Conditions"},
    {"topic": "Osteoporosis: building and keeping bone strength", "keyword": "osteoporosis prevention seniors", "category": "Chronic Conditions"},
    {"topic": "Understanding and managing chronic pain", "keyword": "chronic pain management seniors", "category": "Chronic Conditions"},
    {"topic": "Thyroid health: signs your levels may be off", "keyword": "thyroid health seniors", "category": "Chronic Conditions"},
    {"topic": "Kidney health: what your numbers mean", "keyword": "kidney health seniors", "category": "Chronic Conditions"},
    {"topic": "Living with hearing loss: strategies that help", "keyword": "hearing loss strategies seniors", "category": "Chronic Conditions"},
    {"topic": "Peripheral neuropathy: managing tingling and numbness", "keyword": "neuropathy management seniors", "category": "Chronic Conditions"},
    {"topic": "Acid reflux after 50: beyond antacids", "keyword": "acid reflux management seniors", "category": "Chronic Conditions"},
    {"topic": "Shingles prevention and what to do if you get it", "keyword": "shingles prevention seniors", "category": "Chronic Conditions"},
    # RELATIONSHIPS (new)
    {"topic": "Grandparenting across the miles: staying connected", "keyword": "long distance grandparenting", "category": "Relationships"},
    {"topic": "Dating and companionship after loss", "keyword": "dating after loss seniors", "category": "Relationships"},
    {"topic": "Strengthening your marriage in retirement", "keyword": "marriage retirement relationship", "category": "Relationships"},
    {"topic": "Navigating boundaries with adult children", "keyword": "boundaries adult children seniors", "category": "Relationships"},
    {"topic": "Building new friendships after 60", "keyword": "making friends after 60", "category": "Relationships"},
    {"topic": "Supporting a spouse through illness", "keyword": "spouse caregiver support", "category": "Relationships"},
    {"topic": "The joy and challenge of multigenerational living", "keyword": "multigenerational living seniors", "category": "Relationships"},
    {"topic": "Reconnecting with old friends: it's never too late", "keyword": "reconnecting friends seniors", "category": "Relationships"},
    {"topic": "How to ask for help without feeling like a burden", "keyword": "asking for help seniors", "category": "Relationships"},
    {"topic": "Loneliness vs being alone: knowing the difference", "keyword": "loneliness vs solitude seniors", "category": "Relationships"},
    # WOMEN'S HEALTH (new)
    {"topic": "Bone density after menopause: what every woman should know", "keyword": "bone density menopause", "category": "Women's Health"},
    {"topic": "Heart disease in women: the symptoms doctors miss", "keyword": "heart disease symptoms women", "category": "Women's Health"},
    {"topic": "Pelvic floor health: the conversation we need to have", "keyword": "pelvic floor health women 50", "category": "Women's Health"},
    {"topic": "Hormone changes after 50: what's normal, what's not", "keyword": "hormone changes women 50", "category": "Women's Health"},
    {"topic": "Breast health screening: updated guidelines for women 50+", "keyword": "breast screening guidelines 50", "category": "Women's Health"},
    {"topic": "Autoimmune conditions: why they affect more women", "keyword": "autoimmune disease women over 50", "category": "Women's Health"},
    {"topic": "Iron, calcium, and the nutrients women over 50 need most", "keyword": "nutrients women over 50", "category": "Women's Health"},
    {"topic": "Vaginal health after menopause: what your doctor may not mention", "keyword": "vaginal health menopause", "category": "Women's Health"},
    {"topic": "UTIs after 50: why they're more common and how to prevent them", "keyword": "UTI prevention women 50", "category": "Women's Health"},
    # MEN'S HEALTH (new)
    {"topic": "Prostate health: what the PSA test really tells you", "keyword": "prostate health PSA test", "category": "Men's Health"},
    {"topic": "Heart attack warning signs men ignore", "keyword": "heart attack signs men", "category": "Men's Health"},
    {"topic": "Testosterone and aging: separating fact from marketing", "keyword": "testosterone aging men", "category": "Men's Health"},
    {"topic": "Colon cancer screening: the test that saves lives", "keyword": "colon cancer screening men 50", "category": "Men's Health"},
    {"topic": "Men and mental health: why asking for help matters", "keyword": "men mental health stigma", "category": "Men's Health"},
    {"topic": "Strength and muscle loss after 50: the science of sarcopenia", "keyword": "sarcopenia muscle loss men", "category": "Men's Health"},
    {"topic": "Sleep apnea in men: the risks beyond snoring", "keyword": "sleep apnea risks men", "category": "Men's Health"},
    {"topic": "Bone health isn't just for women: osteoporosis in men", "keyword": "osteoporosis men over 50", "category": "Men's Health"},
    # PREVENTIVE CARE (new)
    {"topic": "The 7 health screenings that can save your life after 50", "keyword": "health screenings after 50", "category": "Preventive Care"},
    {"topic": "Vaccines you need in your 50s, 60s, and beyond", "keyword": "vaccines adults over 50", "category": "Preventive Care"},
    {"topic": "What your annual blood work actually means", "keyword": "blood work results explained", "category": "Preventive Care"},
    {"topic": "Skin cancer checks: what to look for between dermatologist visits", "keyword": "skin cancer self check", "category": "Preventive Care"},
    {"topic": "Hearing and vision tests: how often is enough", "keyword": "hearing vision tests seniors", "category": "Preventive Care"},
    {"topic": "The dental visit that could catch more than cavities", "keyword": "dental health screening seniors", "category": "Preventive Care"},
    {"topic": "Pre-diabetes: catching it before it becomes diabetes", "keyword": "pre-diabetes prevention seniors", "category": "Preventive Care"},
    {"topic": "Why your pharmacist deserves a seat at your health table", "keyword": "pharmacist health role seniors", "category": "Preventive Care"},
    # TRAVEL & ADVENTURE (fits under Wellness and Healthy Aging)
    {"topic": "Traveling with medications: a packing and planning guide", "keyword": "travel medications seniors guide", "category": "Wellness"},
    {"topic": "Solo travel after 50: how to start", "keyword": "solo travel over 50", "category": "Wellness"},
    {"topic": "Active vacations that are actually fun after 50", "keyword": "active travel seniors", "category": "Exercise"},
    {"topic": "Travel insurance after 50: what to look for", "keyword": "travel insurance seniors guide", "category": "Healthy Aging"},
    # FINANCES & WELLNESS
    {"topic": "How financial stress affects your physical health", "keyword": "financial stress health effects", "category": "Healthy Aging"},
    {"topic": "Prescription savings programs most people don't know about", "keyword": "prescription savings programs seniors", "category": "Medication Tips"},
    {"topic": "Planning for healthcare costs in retirement", "keyword": "healthcare costs retirement planning", "category": "Healthy Aging"},
    # HOBBIES & PURPOSE
    {"topic": "Why picking up a musical instrument is great for your brain", "keyword": "learn instrument brain health", "category": "Brain Health"},
    {"topic": "Bird watching: the hobby that boosts mental and physical health", "keyword": "bird watching health benefits", "category": "Wellness"},
    {"topic": "Pottery, painting, and the health benefits of creative hobbies", "keyword": "creative hobbies health seniors", "category": "Mental Wellness"},
    {"topic": "Book clubs: social connection meets brain exercise", "keyword": "book clubs seniors benefits", "category": "Brain Health"},
    {"topic": "Community gardens: growing food, growing friendships", "keyword": "community garden seniors", "category": "Relationships"},
    # FUN & CURRENT TRENDS
    {"topic": "Cold plunges, saunas, and recovery: what the evidence says for 50+", "keyword": "cold plunge sauna seniors", "category": "Wellness"},
    {"topic": "Walking pads and under-desk movement: worth the hype?", "keyword": "walking pad review seniors", "category": "Exercise"},
    {"topic": "Intermittent fasting after 50: what doctors actually recommend", "keyword": "intermittent fasting over 50", "category": "Nutrition"},
    {"topic": "Puzzle games, Wordle, and your brain: does daily gaming help?", "keyword": "puzzle games brain health seniors", "category": "Brain Health"},
    {"topic": "Blue zones: what the world's longest-lived people actually eat", "keyword": "blue zones diet longevity", "category": "Nutrition"},
    {"topic": "Wearable health tech: what's useful vs what's noise", "keyword": "health wearables seniors review", "category": "Technology"},
    {"topic": "Forest bathing: the Japanese practice backed by science", "keyword": "forest bathing health benefits", "category": "Wellness"},
    {"topic": "Gut health trends: kombucha, kefir, and what works", "keyword": "gut health trends seniors", "category": "Nutrition"},
]

# Load image/video data from external JSON to keep this file manageable
# Falls back to inline defaults if file not found
def _load_media_data():
    """Return dicts for CATEGORY_IMAGES, HERO_IMAGES, INLINE_IMAGES, CATEGORY_VIDEOS, _RELATED_CATEGORIES."""
    # All media data is defined inline below
    pass

CATEGORY_IMAGES = {
    "Mental Wellness": ["https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80","https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80","https://images.unsplash.com/photo-1474418397713-7ede21d49118?w=800&q=80"],
    "Medication Tips": ["https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&q=80","https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=800&q=80","https://images.unsplash.com/photo-1631549916768-4119b2e5f926?w=800&q=80"],
    "Healthy Aging": ["https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=800&q=80","https://images.unsplash.com/photo-1516307365426-bea591f05011?w=800&q=80","https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=800&q=80"],
    "Exercise": ["https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","https://images.unsplash.com/photo-1486218119243-13883505764c?w=800&q=80","https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=800&q=80"],
    "Nutrition": ["https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80","https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=800&q=80","https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=800&q=80"],
    "Sleep": ["https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=800&q=80","https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=800&q=80","https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=800&q=80"],
    "Heart Health": ["https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80","https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80","https://images.unsplash.com/photo-1628348070889-cb656235b4eb?w=800&q=80"],
    "Brain Health": ["https://images.unsplash.com/photo-1559757175-5700dde675bc?w=800&q=80","https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=800&q=80","https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=800&q=80"],
    "Safety": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=800&q=80","https://images.unsplash.com/photo-1584515933487-779824d29309?w=800&q=80"],
    "Wellness": ["https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80","https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80"],
    "Technology": ["https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&q=80","https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80","https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&q=80"],
    "Chronic Conditions": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80","https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&q=80"],
    "Relationships": ["https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=800&q=80","https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800&q=80","https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=800&q=80"],
    "Women's Health": ["https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80","https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&q=80","https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80"],
    "Men's Health": ["https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=800&q=80","https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=800&q=80"],
    "Preventive Care": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800&q=80","https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&q=80"],
}

# Hero and inline images use dynamic Unsplash search as primary source.
# These hardcoded pools are the fallback — kept intentionally lean since
# the dynamic search handles variety. 10 hero + 12 inline per category.
HERO_IMAGES = {cat: urls[:10] if len(urls) > 10 else urls for cat, urls in {
    "Mental Wellness": ["https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=1200&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=1200&q=80","https://images.unsplash.com/photo-1474418397713-7ede21d49118?w=1200&q=80","https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1200&q=80","https://images.unsplash.com/photo-1529693662653-9d480530a697?w=1200&q=80","https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?w=1200&q=80","https://images.unsplash.com/photo-1501854140801-50d01698950b?w=1200&q=80","https://images.unsplash.com/photo-1475924156734-496f6cac6ec1?w=1200&q=80","https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1200&q=80","https://images.unsplash.com/photo-1502082553048-f009c37129b9?w=1200&q=80","https://images.unsplash.com/photo-1433086966358-54859d0ed716?w=1200&q=80"],
    "Medication Tips": ["https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1200&q=80","https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=1200&q=80","https://images.unsplash.com/photo-1631549916768-4119b2e5f926?w=1200&q=80","https://images.unsplash.com/photo-1585435557343-3b092031a831?w=1200&q=80","https://images.unsplash.com/photo-1471864190281-a93a3070b6de?w=1200&q=80","https://images.unsplash.com/photo-1576602976047-174e57a47881?w=1200&q=80","https://images.unsplash.com/photo-1550831107-1553da8c8464?w=1200&q=80","https://images.unsplash.com/photo-1607619056574-7b8d3ee536b2?w=1200&q=80","https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=1200&q=80","https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200&q=80"],
    "Healthy Aging": ["https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=1200&q=80","https://images.unsplash.com/photo-1516307365426-bea591f05011?w=1200&q=80","https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=1200&q=80","https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=1200&q=80","https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=1200&q=80","https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=1200&q=80","https://images.unsplash.com/photo-1559234938-b60fff04894d?w=1200&q=80","https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=1200&q=80","https://images.unsplash.com/photo-1581579438747-104c53d7fbc4?w=1200&q=80","https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=1200&q=80"],
    "Exercise": ["https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80","https://images.unsplash.com/photo-1486218119243-13883505764c?w=1200&q=80","https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=1200&q=80","https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=1200&q=80","https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80","https://images.unsplash.com/photo-1518611012118-696072aa579a?w=1200&q=80","https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=1200&q=80","https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=1200&q=80","https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=1200&q=80","https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=1200&q=80"],
    "Nutrition": ["https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80","https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=1200&q=80","https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=1200&q=80","https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=1200&q=80","https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80","https://images.unsplash.com/photo-1490818387583-1baba5e638af?w=1200&q=80","https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=1200&q=80","https://images.unsplash.com/photo-1543362906-acfc16c67564?w=1200&q=80","https://images.unsplash.com/photo-1547592180-85f173990554?w=1200&q=80","https://images.unsplash.com/photo-1505253716362-afaea1d3d1af?w=1200&q=80"],
    "Sleep": ["https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=1200&q=80","https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=1200&q=80","https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=1200&q=80","https://images.unsplash.com/photo-1455642305367-68834a1da7ab?w=1200&q=80","https://images.unsplash.com/photo-1520206183501-b80df61043c2?w=1200&q=80","https://images.unsplash.com/photo-1495197359483-d092478c170a?w=1200&q=80","https://images.unsplash.com/photo-1507652313519-d4e9174996dd?w=1200&q=80","https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=1200&q=80","https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=1200&q=80","https://images.unsplash.com/photo-1540518614846-7eded433c457?w=1200&q=80"],
    "Heart Health": ["https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=1200&q=80","https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=1200&q=80","https://images.unsplash.com/photo-1628348070889-cb656235b4eb?w=1200&q=80","https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=1200&q=80","https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=1200&q=80","https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=1200&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80","https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80","https://images.unsplash.com/photo-1547592180-85f173990554?w=1200&q=80"],
    "Brain Health": ["https://images.unsplash.com/photo-1559757175-5700dde675bc?w=1200&q=80","https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=1200&q=80","https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&q=80","https://images.unsplash.com/photo-1456406644174-8ddd4cd52a06?w=1200&q=80","https://images.unsplash.com/photo-1507413245164-6160d8298b31?w=1200&q=80","https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1200&q=80","https://images.unsplash.com/photo-1513475382585-d06e58bcb0e0?w=1200&q=80","https://images.unsplash.com/photo-1488190211105-8b0e65b80b4e?w=1200&q=80","https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=1200&q=80","https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=1200&q=80"],
    "Safety": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80","https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=1200&q=80","https://images.unsplash.com/photo-1584515933487-779824d29309?w=1200&q=80","https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200&q=80","https://images.unsplash.com/photo-1550831107-1553da8c8464?w=1200&q=80","https://images.unsplash.com/photo-1584432810601-6c7f27d2362b?w=1200&q=80","https://images.unsplash.com/photo-1612531386530-97286d97c2d2?w=1200&q=80","https://images.unsplash.com/photo-1530497610245-94d3c16cda28?w=1200&q=80","https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=1200&q=80","https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1200&q=80"],
    "Wellness": ["https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=1200&q=80","https://images.unsplash.com/photo-1501854140801-50d01698950b?w=1200&q=80","https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?w=1200&q=80","https://images.unsplash.com/photo-1475924156734-496f6cac6ec1?w=1200&q=80","https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1200&q=80","https://images.unsplash.com/photo-1529693662653-9d480530a697?w=1200&q=80","https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1200&q=80","https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1200&q=80"],
    "Technology": ["https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1200&q=80","https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=1200&q=80","https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200&q=80","https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=1200&q=80","https://images.unsplash.com/photo-1488590528505-98d2b5aba04b?w=1200&q=80","https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1200&q=80","https://images.unsplash.com/photo-1531297484001-80022131f5a1?w=1200&q=80","https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=1200&q=80","https://images.unsplash.com/photo-1483058712412-4245e9b90334?w=1200&q=80","https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=1200&q=80"],
    "Chronic Conditions": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80","https://images.unsplash.com/photo-1559234938-b60fff04894d?w=1200&q=80","https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1200&q=80","https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200&q=80","https://images.unsplash.com/photo-1550831107-1553da8c8464?w=1200&q=80","https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80","https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=1200&q=80","https://images.unsplash.com/photo-1607619056574-7b8d3ee536b2?w=1200&q=80"],
    "Relationships": ["https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=1200&q=80","https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=1200&q=80","https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=1200&q=80","https://images.unsplash.com/photo-1516307365426-bea591f05011?w=1200&q=80","https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=1200&q=80","https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=1200&q=80","https://images.unsplash.com/photo-1530268729831-4b0b9e170218?w=1200&q=80","https://images.unsplash.com/photo-1474418397713-7ede21d49118?w=1200&q=80","https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=1200&q=80","https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=1200&q=80"],
    "Women's Health": ["https://images.unsplash.com/photo-1559234938-b60fff04894d?w=1200&q=80","https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=1200&q=80","https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=1200&q=80","https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=1200&q=80","https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80","https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80","https://images.unsplash.com/photo-1474418397713-7ede21d49118?w=1200&q=80","https://images.unsplash.com/photo-1581579438747-104c53d7fbc4?w=1200&q=80"],
    "Men's Health": ["https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80","https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=1200&q=80","https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=1200&q=80","https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=1200&q=80","https://images.unsplash.com/photo-1486218119243-13883505764c?w=1200&q=80","https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=1200&q=80","https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1200&q=80","https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=1200&q=80","https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1200&q=80","https://images.unsplash.com/photo-1518611012118-696072aa579a?w=1200&q=80"],
    "Preventive Care": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80","https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200&q=80","https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=1200&q=80","https://images.unsplash.com/photo-1550831107-1553da8c8464?w=1200&q=80","https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=1200&q=80","https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=1200&q=80","https://images.unsplash.com/photo-1559234938-b60fff04894d?w=1200&q=80","https://images.unsplash.com/photo-1584515933487-779824d29309?w=1200&q=80","https://images.unsplash.com/photo-1530497610245-94d3c16cda28?w=1200&q=80","https://images.unsplash.com/photo-1607619056574-7b8d3ee536b2?w=1200&q=80"],
}.items()}

# Inline images: dynamic search is primary; these are fallback only
# Using 8 per category as fallback — dynamic search provides the real variety
INLINE_IMAGES = {cat: imgs for cat, imgs in {
    "Mental Wellness": [{"url":"https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80","alt":"Person relaxing"},{"url":"https://images.unsplash.com/photo-1508672019048-805c876b67e2?w=800&q=80","alt":"Peaceful scene"},{"url":"https://images.unsplash.com/photo-1515377905703-c4788e51af15?w=800&q=80","alt":"Sunlight through trees"},{"url":"https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=800&q=80","alt":"Journaling"},{"url":"https://images.unsplash.com/photo-1506252374453-ef5237291d83?w=800&q=80","alt":"Garden path"},{"url":"https://images.unsplash.com/photo-1500904156668-a21764a29575?w=800&q=80","alt":"Cozy reading"},{"url":"https://images.unsplash.com/photo-1446511437394-d789541e7f95?w=800&q=80","alt":"Walking in nature"},{"url":"https://images.unsplash.com/photo-1502082553048-f009c37129b9?w=800&q=80","alt":"Sunlit forest"}],
    "Medication Tips": [{"url":"https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=800&q=80","alt":"Pill organizer"},{"url":"https://images.unsplash.com/photo-1576602976047-174e57a47881?w=800&q=80","alt":"Healthcare professional"},{"url":"https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","alt":"Doctor consultation"},{"url":"https://images.unsplash.com/photo-1550831107-1553da8c8464?w=800&q=80","alt":"Pharmacy"},{"url":"https://images.unsplash.com/photo-1585435557343-3b092031a831?w=800&q=80","alt":"Medication and water"},{"url":"https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80","alt":"Health app"},{"url":"https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&q=80","alt":"Patient care"},{"url":"https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=800&q=80","alt":"Health checklist"}],
    "Healthy Aging": [{"url":"https://images.unsplash.com/photo-1516307365426-bea591f05011?w=800&q=80","alt":"Active senior"},{"url":"https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&q=80","alt":"Couple walking"},{"url":"https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=800&q=80","alt":"Laughing together"},{"url":"https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=800&q=80","alt":"Conversation"},{"url":"https://images.unsplash.com/photo-1581579438747-104c53d7fbc4?w=800&q=80","alt":"Morning stretch"},{"url":"https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800&q=80","alt":"Friends outdoors"},{"url":"https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=800&q=80","alt":"Group discussion"},{"url":"https://images.unsplash.com/photo-1530268729831-4b0b9e170218?w=800&q=80","alt":"Community"}],
    "Exercise": [{"url":"https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80","alt":"Stretching"},{"url":"https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=800&q=80","alt":"Walking"},{"url":"https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","alt":"Yoga"},{"url":"https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=800&q=80","alt":"Jogging"},{"url":"https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80","alt":"Swimming"},{"url":"https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80","alt":"Balance"},{"url":"https://images.unsplash.com/photo-1599058945522-28d584b6f0ff?w=800&q=80","alt":"Tai chi"},{"url":"https://images.unsplash.com/photo-1545389336-cf090694435e?w=800&q=80","alt":"Gentle stretching"}],
    "Nutrition": [{"url":"https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=800&q=80","alt":"Meal prep"},{"url":"https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=800&q=80","alt":"Fresh produce"},{"url":"https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&q=80","alt":"Home cooking"},{"url":"https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=800&q=80","alt":"Salmon"},{"url":"https://images.unsplash.com/photo-1547592180-85f173990554?w=800&q=80","alt":"Spices"},{"url":"https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=800&q=80","alt":"Healthy toast"},{"url":"https://images.unsplash.com/photo-1484980972926-edee96e0960d?w=800&q=80","alt":"Berry bowl"},{"url":"https://images.unsplash.com/photo-1455619452474-d2be8b1e70cd?w=800&q=80","alt":"Warm soup"}],
    "Sleep": [{"url":"https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=800&q=80","alt":"Peaceful bedroom"},{"url":"https://images.unsplash.com/photo-1495197359483-d092478c170a?w=800&q=80","alt":"Comfortable bed"},{"url":"https://images.unsplash.com/photo-1520206183501-b80df61043c2?w=800&q=80","alt":"Moonlit scene"},{"url":"https://images.unsplash.com/photo-1507652313519-d4e9174996dd?w=800&q=80","alt":"Evening reading"},{"url":"https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800&q=80","alt":"Herbal tea"},{"url":"https://images.unsplash.com/photo-1540518614846-7eded433c457?w=800&q=80","alt":"Soft pillows"},{"url":"https://images.unsplash.com/photo-1445991842772-097fea258e7b?w=800&q=80","alt":"Sunset"},{"url":"https://images.unsplash.com/photo-1513694203232-719a280e022f?w=800&q=80","alt":"Relaxing bath"}],
    "Heart Health": [{"url":"https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80","alt":"Healthy lifestyle"},{"url":"https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","alt":"Cardio"},{"url":"https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80","alt":"Heart-healthy meal"},{"url":"https://images.unsplash.com/photo-1490818387583-1baba5e638af?w=800&q=80","alt":"Green smoothie"},{"url":"https://images.unsplash.com/photo-1547592180-85f173990554?w=800&q=80","alt":"Herbs"},{"url":"https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=800&q=80","alt":"Active walk"},{"url":"https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&q=80","alt":"Nutritious food"},{"url":"https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=800&q=80","alt":"Omega-3 foods"}],
    "Brain Health": [{"url":"https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=800&q=80","alt":"Learning"},{"url":"https://images.unsplash.com/photo-1456406644174-8ddd4cd52a06?w=800&q=80","alt":"Reading"},{"url":"https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=800&q=80","alt":"Puzzles"},{"url":"https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=800&q=80","alt":"Focus"},{"url":"https://images.unsplash.com/photo-1488190211105-8b0e65b80b4e?w=800&q=80","alt":"Notes"},{"url":"https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=800&q=80","alt":"Group learning"},{"url":"https://images.unsplash.com/photo-1453928582365-b6ad33cbcf64?w=800&q=80","alt":"Thinking"},{"url":"https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=800&q=80","alt":"Book and coffee"}],
    "Safety": [{"url":"https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=800&q=80","alt":"Home safety"},{"url":"https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80","alt":"Well-lit home"},{"url":"https://images.unsplash.com/photo-1584515933487-779824d29309?w=800&q=80","alt":"Emergency kit"},{"url":"https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800&q=80","alt":"Checkup"},{"url":"https://images.unsplash.com/photo-1584432810601-6c7f27d2362b?w=800&q=80","alt":"Protection"},{"url":"https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&q=80","alt":"Doctor"},{"url":"https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80","alt":"Health app"},{"url":"https://images.unsplash.com/photo-1612531386530-97286d97c2d2?w=800&q=80","alt":"Safety equipment"}],
    "Wellness": [{"url":"https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80","alt":"Mindfulness"},{"url":"https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","alt":"Yoga"},{"url":"https://images.unsplash.com/photo-1501854140801-50d01698950b?w=800&q=80","alt":"Nature"},{"url":"https://images.unsplash.com/photo-1475924156734-496f6cac6ec1?w=800&q=80","alt":"Morning mist"},{"url":"https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&q=80","alt":"Forest"},{"url":"https://images.unsplash.com/photo-1518459031867-a89b944bffe4?w=800&q=80","alt":"Outdoor wellness"},{"url":"https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=800&q=80","alt":"Journaling"},{"url":"https://images.unsplash.com/photo-1502082553048-f009c37129b9?w=800&q=80","alt":"Sunlit trees"}],
    "Technology": [{"url":"https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&q=80","alt":"Laptop"},{"url":"https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80","alt":"Health app"},{"url":"https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=800&q=80","alt":"Workspace"},{"url":"https://images.unsplash.com/photo-1488590528505-98d2b5aba04b?w=800&q=80","alt":"Screen"},{"url":"https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=800&q=80","alt":"Digital security"},{"url":"https://images.unsplash.com/photo-1517430816045-df4b7de11d1d?w=800&q=80","alt":"Smartphone"},{"url":"https://images.unsplash.com/photo-1498049794561-7780e7231661?w=800&q=80","alt":"Connected devices"},{"url":"https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=800&q=80","alt":"Monitor"}],
    "Chronic Conditions": [{"url":"https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","alt":"Medical consultation"},{"url":"https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80","alt":"Healthy choices"},{"url":"https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","alt":"Exercise"},{"url":"https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80","alt":"Anti-inflammatory foods"},{"url":"https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=800&q=80","alt":"Tracking"},{"url":"https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80","alt":"Health monitoring"},{"url":"https://images.unsplash.com/photo-1607619056574-7b8d3ee536b2?w=800&q=80","alt":"Daily routine"},{"url":"https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","alt":"Gentle yoga"}],
    "Relationships": [{"url":"https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=800&q=80","alt":"Family"},{"url":"https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800&q=80","alt":"Friends outdoors"},{"url":"https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=800&q=80","alt":"Conversation"},{"url":"https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&q=80","alt":"Walking together"},{"url":"https://images.unsplash.com/photo-1530268729831-4b0b9e170218?w=800&q=80","alt":"Community"},{"url":"https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=800&q=80","alt":"Heartfelt talk"},{"url":"https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&q=80","alt":"Video call"},{"url":"https://images.unsplash.com/photo-1474418397713-7ede21d49118?w=800&q=80","alt":"Togetherness"}],
    "Women's Health": [{"url":"https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80","alt":"Healthy choices"},{"url":"https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","alt":"Yoga practice"},{"url":"https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&q=80","alt":"Confident woman"},{"url":"https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80","alt":"Nutritious meal"},{"url":"https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","alt":"Active lifestyle"},{"url":"https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80","alt":"Morning wellness"},{"url":"https://images.unsplash.com/photo-1581579438747-104c53d7fbc4?w=800&q=80","alt":"Stretching"},{"url":"https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80","alt":"Self-care moment"}],
    "Men's Health": [{"url":"https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=800&q=80","alt":"Outdoor run"},{"url":"https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","alt":"Strength training"},{"url":"https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=800&q=80","alt":"Trail walk"},{"url":"https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80","alt":"Heart-healthy food"},{"url":"https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80","alt":"Swimming"},{"url":"https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","alt":"Doctor visit"},{"url":"https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=800&q=80","alt":"Morning walk"},{"url":"https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&q=80","alt":"Beach fitness"}],
    "Preventive Care": [{"url":"https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","alt":"Medical visit"},{"url":"https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800&q=80","alt":"Health checkup"},{"url":"https://images.unsplash.com/photo-1505751172876-fa1923c5c528?w=800&q=80","alt":"Patient care"},{"url":"https://images.unsplash.com/photo-1583912267550-d974311a9a6e?w=800&q=80","alt":"Health tracking"},{"url":"https://images.unsplash.com/photo-1573883431205-98b5f10aaedb?w=800&q=80","alt":"Health app"},{"url":"https://images.unsplash.com/photo-1550831107-1553da8c8464?w=800&q=80","alt":"Pharmacy consultation"},{"url":"https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80","alt":"Wellness choices"},{"url":"https://images.unsplash.com/photo-1584515933487-779824d29309?w=800&q=80","alt":"Preparedness"}],
}.items()}

CATEGORY_VIDEOS = {
    "Mental Wellness": [{"id":"inpok4MKVLM","title":"5-Minute Meditation","channel":"Goodful"},{"id":"ZToicYcHIOU","title":"Breathing for Stress Relief","channel":"Therapy in a Nutshell"},{"id":"SEfs5TJZ6Nk","title":"How to Practice Mindfulness","channel":"Psych Hub"},{"id":"O-6f5wQXSu8","title":"Managing Anxiety","channel":"Therapy in a Nutshell"}],
    "Medication Tips": [{"id":"xLUaVeKhbK8","title":"Managing Multiple Medications","channel":"AARP"},{"id":"Ry_bVsdcYvM","title":"Organize Your Medications","channel":"Walgreens"},{"id":"QB1kk0p_E0I","title":"Understanding Prescriptions","channel":"Cleveland Clinic"}],
    "Healthy Aging": [{"id":"3PycZtfns_U","title":"Secrets to Healthy Aging","channel":"Mayo Clinic"},{"id":"TUqEu0mBMr8","title":"Staying Active as You Age","channel":"AARP"},{"id":"dVHMj6Fy_04","title":"Aging Well","channel":"TED"}],
    "Exercise": [{"id":"6cJuPmYp7lE","title":"Gentle Morning Stretch","channel":"SilverSneakers"},{"id":"8Oh3q4BC4y8","title":"Seated Exercises","channel":"More Life Health"},{"id":"sRZ4IqwvHH8","title":"Balance Exercises","channel":"Bob & Brad"},{"id":"3YStJaRSeg0","title":"Full Body Workout","channel":"HASfit"}],
    "Nutrition": [{"id":"fqhYBTg73fw","title":"Healthy Eating Tips","channel":"AARP"},{"id":"TRov4mMb_B4","title":"Mediterranean Diet","channel":"Cleveland Clinic"},{"id":"vBEI3JXxLJM","title":"Anti-Inflammatory Foods","channel":"Dr. Eric Berg DC"},{"id":"BSnsLGJzmGE","title":"Protein for Older Adults","channel":"Cleveland Clinic"}],
    "Sleep": [{"id":"t0kACis_dJE","title":"Sleep Hygiene Tips","channel":"Mayo Clinic"},{"id":"LFBjI3RA2JI","title":"Fall Asleep Faster","channel":"Cleveland Clinic"},{"id":"nm1TxQj9IsQ","title":"Why We Sleep","channel":"TED"}],
    "Heart Health": [{"id":"pBrEhtfrVsE","title":"Heart Healthy Tips","channel":"AHA"},{"id":"RQSl6Dnsf68","title":"Understanding Blood Pressure","channel":"Cleveland Clinic"},{"id":"LXb3EKWsInQ","title":"Heart-Healthy Foods","channel":"Mayo Clinic"},{"id":"dBnniua6-oM","title":"Signs of Heart Disease","channel":"Cleveland Clinic"}],
    "Brain Health": [{"id":"LNHBMFCzznE","title":"Keep Your Brain Sharp","channel":"AARP"},{"id":"pIlTb6SjR_g","title":"Memory Tips","channel":"TED-Ed"},{"id":"f7Dl6a9i0wY","title":"Brain Foods","channel":"Cleveland Clinic"},{"id":"teVE3VGrBhM","title":"Neuroplasticity","channel":"TED-Ed"}],
    "Safety": [{"id":"8Gq3D_YOYew","title":"Fall Prevention","channel":"Bob & Brad"},{"id":"TLWGn5HD_0I","title":"Home Safety Checklist","channel":"AARP"},{"id":"7TXEZ_dUQqE","title":"Emergency Preparedness","channel":"FEMA"}],
    "Wellness": [{"id":"inpok4MKVLM","title":"Morning Meditation","channel":"Goodful"},{"id":"6cJuPmYp7lE","title":"Full Body Stretch","channel":"SilverSneakers"},{"id":"SEfs5TJZ6Nk","title":"Intro to Mindfulness","channel":"Psych Hub"}],
    "Technology": [{"id":"xLUaVeKhbK8","title":"Staying Connected","channel":"AARP"},{"id":"TLWGn5HD_0I","title":"Online Safety Tips","channel":"AARP"},{"id":"3PycZtfns_U","title":"Digital Health Tools","channel":"Mayo Clinic"}],
    "Chronic Conditions": [{"id":"QB1kk0p_E0I","title":"Managing Chronic Conditions","channel":"Cleveland Clinic"},{"id":"TRov4mMb_B4","title":"Nutrition for Chronic Health","channel":"Cleveland Clinic"},{"id":"sRZ4IqwvHH8","title":"Exercise with Chronic Pain","channel":"Bob & Brad"}],
    "Relationships": [{"id":"inpok4MKVLM","title":"Mindful Communication","channel":"Goodful"},{"id":"TUqEu0mBMr8","title":"Staying Active Together","channel":"AARP"},{"id":"3PycZtfns_U","title":"Connection and Health","channel":"Mayo Clinic"}],
    "Women's Health": [{"id":"3PycZtfns_U","title":"Women's Wellness","channel":"Mayo Clinic"},{"id":"TRov4mMb_B4","title":"Nutrition After 50","channel":"Cleveland Clinic"},{"id":"t0kACis_dJE","title":"Sleep and Hormones","channel":"Mayo Clinic"}],
    "Men's Health": [{"id":"pBrEhtfrVsE","title":"Heart Health for Men","channel":"AHA"},{"id":"sRZ4IqwvHH8","title":"Strength and Balance","channel":"Bob & Brad"},{"id":"RQSl6Dnsf68","title":"Blood Pressure Basics","channel":"Cleveland Clinic"}],
    "Preventive Care": [{"id":"QB1kk0p_E0I","title":"Health Screenings Guide","channel":"Cleveland Clinic"},{"id":"3PycZtfns_U","title":"Preventive Wellness","channel":"Mayo Clinic"},{"id":"TLWGn5HD_0I","title":"Health Checklist","channel":"AARP"}],
}

STEADIDAY_FEATURES = {"free": ["Emergency SOS button","Fall Detection","Trusted Contacts","Medication reminders","Apple Health integration","Food and water logging","Mind Breaks games","Calendar sync","Magnifier tool","Find My Car","Flashlight"]}

_RELATED_CATEGORIES = {
    "Mental Wellness": ["Wellness","Sleep","Brain Health","Relationships"],
    "Medication Tips": ["Safety","Wellness","Healthy Aging","Chronic Conditions"],
    "Healthy Aging": ["Exercise","Wellness","Nutrition","Technology"],
    "Exercise": ["Healthy Aging","Heart Health","Wellness","Chronic Conditions"],
    "Nutrition": ["Heart Health","Healthy Aging","Wellness","Chronic Conditions"],
    "Sleep": ["Mental Wellness","Wellness","Brain Health"],
    "Heart Health": ["Exercise","Nutrition","Wellness"],
    "Brain Health": ["Mental Wellness","Healthy Aging","Exercise"],
    "Safety": ["Medication Tips","Healthy Aging","Technology"],
    "Wellness": ["Mental Wellness","Exercise","Nutrition","Relationships"],
    "Technology": ["Safety","Healthy Aging","Relationships"],
    "Chronic Conditions": ["Medication Tips","Exercise","Nutrition","Wellness"],
    "Relationships": ["Mental Wellness","Wellness","Healthy Aging"],
    "Women's Health": ["Nutrition","Exercise","Preventive Care","Wellness"],
    "Men's Health": ["Exercise","Heart Health","Preventive Care","Wellness"],
    "Preventive Care": ["Healthy Aging","Medication Tips","Women's Health","Men's Health"],
}

_used_hero_images = set()
_used_inline_images = set()

def find_unsplash_images(client, topic, category, count=6):
    prompt = f"""Find {count} different Unsplash photo URLs relevant to: "{topic}" (Category: {category})
Requirements: from images.unsplash.com, varied, warm/positive, for adults 50+.
URL format: https://images.unsplash.com/photo-XXXXX?w=800&q=80
Return ONLY a JSON array: [{{"url":"...","alt":"..."}}] or NONE if no results."""
    try:
        msg = call_with_retry(lambda: client.messages.create(model=CLAUDE_MODEL, max_tokens=1000, tools=[{"type":"web_search_20250305","name":"web_search"}], messages=[{"role":"user","content":prompt}]))
        response_text = "".join(block.text for block in msg.content if hasattr(block,'text'))
        if "NONE" in response_text: return None
        json_match = re.search(r'\[[\s\S]*?\]', response_text)
        if json_match:
            valid = [img for img in json.loads(json_match.group()) if isinstance(img,dict) and "url" in img and "alt" in img and "unsplash.com" in img["url"]]
            if len(valid) >= 3: return valid
        return None
    except Exception as e:
        print(f"  ⚠ Dynamic image search failed: {e}")
        return None

def get_images_for_category(category, topic=None, client=None):
    global _used_hero_images, _used_inline_images
    hero_options = HERO_IMAGES.get(category, HERO_IMAGES["Wellness"])
    available_heroes = [h for h in hero_options if h not in _used_hero_images]
    if not available_heroes:
        all_heroes = [h for v in HERO_IMAGES.values() for h in v]
        available_heroes = [h for h in all_heroes if h not in _used_hero_images]
    if not available_heroes:
        _used_hero_images.clear(); available_heroes = hero_options
    hero = random.choice(available_heroes); _used_hero_images.add(hero)
    n = random.choice([4,5])
    dynamic_images = None
    if client and topic:
        print(f"  🔍 Searching for topic-specific images...")
        dynamic_images = find_unsplash_images(client, topic, category, count=n+2)
        if dynamic_images: print(f"  ✅ Found {len(dynamic_images)} topic-specific images")
    if dynamic_images:
        inline = random.sample(dynamic_images, min(n, len(dynamic_images)))
    else:
        if client and topic: print(f"  📚 Using expanded image library (fallback)")
        inline_options = INLINE_IMAGES.get(category, INLINE_IMAGES["Wellness"])
        available_inline = [img for img in inline_options if img["url"] not in _used_inline_images]
        if len(available_inline) < n:
            for rel_cat in _RELATED_CATEGORIES.get(category, ["Wellness"]):
                for img in INLINE_IMAGES.get(rel_cat, []):
                    if img["url"] not in _used_inline_images and img not in available_inline: available_inline.append(img)
                    if len(available_inline) >= n+3: break
                if len(available_inline) >= n+3: break
        if len(available_inline) < n: _used_inline_images.clear(); available_inline = inline_options
        inline = random.sample(available_inline, min(n, len(available_inline)))
    for img in inline: _used_inline_images.add(img["url"])
    return {"hero": hero, "inline": inline}

def get_category_thumbnail(category):
    options = CATEGORY_IMAGES.get(category, CATEGORY_IMAGES["Wellness"])
    return random.choice(options) if isinstance(options, list) else options

def verify_youtube_video(video_id):
    try:
        req = urllib.request.Request(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp: return resp.status == 200
    except urllib.error.HTTPError: return False
    except: return True

def find_youtube_video(client, topic, category):
    prompt = f"""Find ONE YouTube video relevant to: "{topic}" (Category: {category})
From reputable health channels (Mayo Clinic, Cleveland Clinic, AARP, etc.), under 15 min.
Return ONLY: VIDEO_ID: [id]\nVIDEO_TITLE: [title]\nVIDEO_CHANNEL: [channel]\nOr: VIDEO_ID: NONE"""
    try:
        msg = call_with_retry(lambda: client.messages.create(model=CLAUDE_MODEL, max_tokens=500, tools=[{"type":"web_search_20250305","name":"web_search"}], messages=[{"role":"user","content":prompt}]))
        response_text = "".join(block.text for block in msg.content if hasattr(block,'text'))
        vid_match = re.search(r'VIDEO_ID:\s*(\S+)', response_text)
        title_match = re.search(r'VIDEO_TITLE:\s*(.+?)(?:\n|$)', response_text)
        channel_match = re.search(r'VIDEO_CHANNEL:\s*(.+?)(?:\n|$)', response_text)
        if vid_match and vid_match.group(1).strip() != "NONE":
            video_id = vid_match.group(1).strip()
            if 10 <= len(video_id) <= 12 and verify_youtube_video(video_id):
                return {"id":video_id,"title":title_match.group(1).strip() if title_match else "Health Tips","channel":channel_match.group(1).strip() if channel_match else "Health Channel"}
            else: print(f"  Dynamic video {video_id} unavailable, using fallback")
        print("  Could not find dynamic video, using fallback")
    except Exception as e: print(f"  Video search failed: {e}, using fallback")
    return None

def select_unique_topic(existing_posts):
    recent_cats = get_recent_categories(existing_posts)
    print(f"  Recent categories (last {CATEGORY_COOLDOWN_WINDOW}): {recent_cats}")
    shuffled = TOPIC_CATEGORIES[:]; random.shuffle(shuffled)
    for td in shuffled:
        if td['category'] in recent_cats: continue
        slug_words = re.sub(r'[^a-z0-9\s]','',td['topic'].lower()).split()[:5]
        dup,_,_ = is_duplicate(td['topic'],'-'.join(slug_words),existing_posts)
        if not dup: return td
    print("  All non-recent categories exhausted, relaxing cooldown...")
    for td in shuffled:
        slug_words = re.sub(r'[^a-z0-9\s]','',td['topic'].lower()).split()[:5]
        dup,_,_ = is_duplicate(td['topic'],'-'.join(slug_words),existing_posts)
        if not dup: return td
    return None


def find_relevant_studies(client, topic, category):
    """Search for 2-3 real, linkable studies/sources relevant to the topic.
    Returns a list of dicts: [{"title": "...", "url": "...", "finding": "..."}]
    """
    prompt = f"""Find 2-3 recent, reputable medical studies, clinical guidelines, or health organization
publications relevant to this topic: "{topic}" (Category: {category})

Good sources: PubMed (pubmed.ncbi.nlm.nih.gov), NIH, CDC, Mayo Clinic, Cleveland Clinic,
JAMA, The Lancet, NEJM, BMJ, Harvard Health, Johns Hopkins, WHO, AHA, Alzheimer's Association,
AARP, WebMD research pages.

Requirements:
- Each must have a REAL, working URL that goes directly to the source
- Published within the last 3 years
- Relevant to adults 50+
- Include the key finding or recommendation

Return ONLY a JSON array with no other text:
[{{"title": "Study or article title", "url": "https://...", "finding": "Key finding in one sentence"}}]

If you cannot find suitable sources, return: NONE"""

    try:
        msg = call_with_retry(lambda: client.messages.create(
            model=CLAUDE_MODEL, max_tokens=800,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        ))
        response_text = "".join(block.text for block in msg.content if hasattr(block, 'text'))
        if "NONE" in response_text:
            return []
        json_match = re.search(r'\[[\s\S]*?\]', response_text)
        if json_match:
            studies = json.loads(json_match.group())
            valid = [s for s in studies if isinstance(s, dict) and "url" in s and "title" in s and s["url"].startswith("http")]
            if valid:
                print(f"  📚 Found {len(valid)} relevant studies/sources")
                return valid[:3]
        return []
    except Exception as e:
        print(f"  ⚠ Study search failed: {e}")
        return []


# Layout class patterns for inline images (varied per post)
IMAGE_LAYOUT_PATTERNS = [
    ["full", "float-right", "full", "float-left", "full"],
    ["float-right", "full", "float-left", "full", "float-right"],
    ["float-left", "float-right", "full", "float-left", "full"],
    ["full", "float-left", "float-right", "full", "float-left"],
    ["float-right", "float-left", "full", "float-right", "full"],
]


def generate_blog_post(topic_data, existing_posts, client):
    topic, keyword, category = topic_data["topic"], topic_data["keyword"], topic_data.get("category","Wellness")
    images = get_images_for_category(category, topic=topic, client=client)
    print("  Searching for relevant YouTube video...")
    video = find_youtube_video(client, topic, category)
    if video is None:
        fallback_videos = CATEGORY_VIDEOS.get(category, CATEGORY_VIDEOS['Wellness'])[:]
        random.shuffle(fallback_videos)
        for fb in fallback_videos:
            if verify_youtube_video(fb["id"]): video = fb; print(f"  Using fallback video: {video['title']}"); break
            else: print(f"  Fallback '{fb['title']}' unavailable")
        if video is None: print("  No working video. Publishing without video.")
    else: print(f"  Found video: {video['title']} by {video['channel']}")

    # Search for relevant studies to link in the article
    print("  Searching for relevant studies and sources...")
    studies = find_relevant_studies(client, topic, category)
    studies_instruction = ""
    if studies:
        studies_list = "\n".join([f"  - \"{s['title']}\" — {s.get('finding','')} — URL: {s['url']}" for s in studies])
        studies_instruction = f"""
STUDIES TO REFERENCE (link to these with <a href="URL" target="_blank" rel="noopener">text</a>):
{studies_list}
Weave these naturally into the text as evidence. Use the actual URL in hyperlinks.
Do NOT just list sources at the end — embed them where the evidence supports your point."""
    else:
        studies_instruction = """
Include at least 2 hyperlinks to reputable sources (NIH, Mayo Clinic, CDC, AHA, etc.) using
<a href="URL" target="_blank" rel="noopener">descriptive link text</a> format.
Reference specific studies, guidelines, or data where relevant."""

    num_images = len(images["inline"])
    feature = random.choice(STEADIDAY_FEATURES["free"])
    style = random.choice(WRITING_STYLES)
    print(f"  Writing style: {style['name']}")
    img_ph = "\n".join([f"After section {i+2}, insert exactly: [IMAGE_{i+1}]" for i in range(num_images)])
    content_summaries = get_content_summaries(existing_posts)
    angle_instruction = ""
    if topic_data.get('angle'): angle_instruction = f"\nANGLE: {topic_data['angle']}"
    if topic_data.get('source'): angle_instruction += f"\nSOURCE: {topic_data['source']}"
    prompt = f"""You are a health and wellness writer for SteadiDay, an app for adults 50+.
Write a blog post about: "{topic}"
{angle_instruction}

{style['instruction']}

TONE GUIDELINES:
- Write like a knowledgeable friend, not a textbook
- Vary sentence length — mix short punchy with longer flowing
- Use contractions naturally (you'll, it's, don't)
- Include specific, concrete details and real numbers
- Avoid clichés like "in today's world" or "it's no secret"
- DO NOT start paragraphs with "In fact," "Additionally," "Furthermore," "Moreover"
- Use conversational transitions, not formal connectors
- Evidence-based only — no political opinions
{studies_instruction}

EXISTING POSTS (do NOT duplicate):
{content_summaries}

SEO REQUIREMENTS:
- TITLE should include the primary keyword naturally (under 55 chars)
- META_DESCRIPTION must include the keyword and a compelling reason to click (150-160 chars)
- Use the primary keyword in the first paragraph and at least 2 section headings
- Include 2-3 internal links to related posts on steadiday.com/blog/ if relevant topics exist
- Primary keyword for SEO: "{keyword}"

CONTENT REQUIREMENTS:
1. TITLE under 55 characters, specific and compelling
2. 1000-1500 words, 6-7 sections with <h2> tags
3. Mention SteadiDay's {feature} feature naturally (it's free)
4. Include at least 2 specific statistics with their sources
5. Advice must be DISTINCT from existing posts

MEDIA PLACEHOLDERS:
{img_ph}
After section 4: [VIDEO]

FORMAT:
TITLE: [under 55 chars]
META_DESCRIPTION: [150-160 chars, include keyword]
KEYWORDS: keyword1, keyword2, {keyword}
READ_TIME: X
CONTENT:
<p>Opening...</p>
<h2>Section Title</h2>
<p>Content...</p>"""
    msg = call_with_retry(lambda: client.messages.create(model=CLAUDE_MODEL, max_tokens=4500, messages=[{"role":"user","content":prompt}]))
    r = msg.content[0].text
    title_match = re.search(r'TITLE:\s*(.+?)(?:\n|$)', r)
    title = title_match.group(1).strip() if title_match else topic
    meta = (re.search(r'META_DESCRIPTION:\s*(.+?)(?:\n|$)', r) or type('',(),{'group':lambda s,n:f"Tips about {topic} for adults 50+"})).group(1).strip()
    kws = (re.search(r'KEYWORDS:\s*(.+?)(?:\n|$)', r) or type('',(),{'group':lambda s,n:keyword})).group(1).strip()
    rt = (re.search(r'READ_TIME:\s*(\d+)', r) or type('',(),{'group':lambda s,n:"7"})).group(1)
    content_match = re.search(r'CONTENT:\s*(.+)', r, re.DOTALL)
    content = content_match.group(1).strip() if content_match else r
    if len(title) > 55: title = title[:52].rsplit(' ',1)[0] + "..."
    layout = random.choice(IMAGE_LAYOUT_PATTERNS)
    for i, img in enumerate(images["inline"]):
        layout_class = layout[i % len(layout)]
        css_class = "article-image" if layout_class == "full" else f"article-image {layout_class}"
        content = content.replace(f"[IMAGE_{i+1}]", f'<figure class="{css_class}"><img src="{img["url"]}" alt="{img["alt"]}" loading="lazy"><figcaption>{img["alt"]}</figcaption></figure>')
    if video:
        content = content.replace("[VIDEO]", f'<div class="video-container"><iframe src="https://www.youtube-nocookie.com/embed/{video["id"]}" title="{video["title"]}" frameborder="0" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe></div><p class="video-caption">Video: {video["title"]} -- {video["channel"]}</p>')
    content = re.sub(r'\[IMAGE_\d+\]','',content).replace("[VIDEO]",'')
    slug = '-'.join(re.sub(r'[^a-z0-9\s]','',title.lower()).split()[:5])
    return {"title":title,"meta_description":meta,"keywords":kws,"read_time":rt,"content":content,"slug":slug,"category":category,"hero_image":images["hero"],"video":video,"num_images":num_images,"date":datetime.now().strftime('%Y-%m-%d')}


def get_html_template():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<!-- GTAG_INJECTED -->
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-17929124014"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','AW-17929124014');</script>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | SteadiDay Blog</title>
    <meta name="description" content="{meta_description}"><meta name="keywords" content="{keywords}">
    <meta name="author" content="SteadiDay Team"><meta name="robots" content="index, follow">
    <meta name="apple-itunes-app" content="app-id=6758526744">
    <link rel="canonical" href="{canonical_url}">
    <link rel="alternate" type="application/rss+xml" title="SteadiDay Blog RSS" href="https://www.steadiday.com/blog/rss.xml">
    <meta property="og:title" content="{title}"><meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="article"><meta property="og:url" content="{canonical_url}">
    <meta property="og:image" content="{hero_image}"><meta property="og:site_name" content="SteadiDay">
    <meta property="article:published_time" content="{iso_date}">
    <meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{meta_description}"><meta name="twitter:image" content="{hero_image}">
    <link rel="icon" type="image/jpeg" href="../assets/icon.jpeg"><link rel="apple-touch-icon" href="../assets/icon.jpeg">
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script type="application/ld+json">
    {{"@context":"https://schema.org","@type":"Article","headline":"{title}","description":"{meta_description}","image":"{hero_image}","author":{{"@type":"Organization","name":"SteadiDay Team","url":"{website_url}"}},"publisher":{{"@type":"Organization","name":"SteadiDay","logo":{{"@type":"ImageObject","url":"{website_url}/assets/icon.jpeg"}}}},"datePublished":"{iso_date}","dateModified":"{iso_date}","mainEntityOfPage":{{"@type":"WebPage","@id":"{canonical_url}"}}}}
    </script>
    <style>
        :root{{--cream:#FFFBF5;--teal:#1A8A7D;--teal-dark:#147568;--teal-light:#E8F5F3;--navy:#1E3A5F;--navy-light:#2D4A6F;--charcoal:#2D3436;--charcoal-light:#5A6266;--white:#FFFFFF;}}
        *{{margin:0;padding:0;box-sizing:border-box;}}
        body{{font-family:'Source Sans 3',-apple-system,sans-serif;font-size:1.125rem;line-height:1.8;color:var(--charcoal);background:var(--cream);}}
        h1,h2,h3{{font-family:'Merriweather',Georgia,serif;color:var(--navy);line-height:1.3;}}
        a{{color:var(--teal);text-decoration:none;}}a:hover{{color:var(--teal-dark);text-decoration:underline;}}
        .nav{{background:var(--white);padding:1rem 0;border-bottom:1px solid rgba(30,58,95,0.1);position:sticky;top:0;z-index:100;}}
        .nav-container{{max-width:900px;margin:0 auto;padding:0 2rem;display:flex;justify-content:space-between;align-items:center;}}.nav a{{font-weight:600;}}
        .breadcrumbs{{max-width:900px;margin:0 auto;padding:1rem 2rem;font-size:0.9rem;}}
        .breadcrumbs a{{color:var(--charcoal-light);}}.breadcrumbs span{{color:var(--charcoal-light);margin:0 0.5rem;}}.breadcrumbs .current{{color:var(--navy);font-weight:500;}}
        .hero-image{{width:100%;max-height:450px;object-fit:cover;}}
        .article-header{{background:linear-gradient(135deg,var(--navy) 0%,var(--navy-light) 100%);color:var(--white);padding:3rem 2rem;text-align:center;}}
        .article-header h1{{max-width:800px;margin:0 auto 1rem;font-size:2.25rem;color:var(--white);}}.article-meta{{font-size:1rem;opacity:0.9;}}
        .article-container{{max-width:750px;margin:0 auto;padding:3rem 2rem;background:var(--white);}}
        .article-content h2{{font-size:1.6rem;margin:2.5rem 0 1rem;}}.article-content p{{margin-bottom:1.5rem;}}
        .article-content ul,.article-content ol{{margin:1.5rem 0;padding-left:2rem;}}.article-content li{{margin-bottom:0.75rem;}}
        .article-image{{width:100%;margin:2rem 0;border-radius:12px;overflow:hidden;}}
        .article-image img{{width:100%;height:auto;display:block;}}
        .article-image figcaption{{font-size:0.9rem;color:var(--charcoal-light);text-align:center;padding:0.75rem 1rem;background:var(--cream);font-style:italic;}}
        .article-image.float-left{{float:left;width:45%;margin:0.5rem 1.5rem 1rem 0;}}.article-image.float-right{{float:right;width:45%;margin:0.5rem 0 1rem 1.5rem;}}.article-image.full{{width:100%;float:none;clear:both;}}.article-content h2{{clear:both;}}
        .video-container{{position:relative;width:100%;padding-bottom:56.25%;height:0;margin:2rem 0;border-radius:12px;overflow:hidden;box-shadow:0 4px 15px rgba(0,0,0,0.1);}}
        .video-container iframe{{position:absolute;top:0;left:0;width:100%;height:100%;border:0;}}
        .video-caption{{font-size:0.9rem;color:var(--charcoal-light);text-align:center;padding:0.75rem;font-style:italic;}}
        .cta-box{{background:linear-gradient(135deg,var(--teal) 0%,var(--teal-dark) 100%);color:var(--white);padding:2rem;border-radius:12px;text-align:center;margin:2.5rem 0;}}
        .cta-box h3{{margin-bottom:0.75rem;font-size:1.35rem;color:var(--white);}}.cta-box p{{color:rgba(255,255,255,0.9)!important;margin-bottom:1rem;}}
        .cta-button{{display:inline-block;background:var(--white);color:var(--teal);padding:0.875rem 2rem;border-radius:8px;text-decoration:none;font-weight:600;}}
        .cta-button:hover{{opacity:0.9;text-decoration:none;transform:translateY(-2px);}}
        .back-to-blog{{max-width:750px;margin:0 auto;padding:1.5rem 2rem;text-align:center;background:var(--white);}}
        .footer{{text-align:center;padding:2rem;color:var(--charcoal-light);font-size:0.9rem;background:var(--white);border-top:1px solid rgba(30,58,95,0.1);}}
        @media(max-width:768px){{.article-header h1{{font-size:1.75rem;}}.article-header{{padding:2rem 1.5rem;}}.article-container{{padding:2rem 1.5rem;}}.hero-image{{max-height:280px;}}.article-image.float-left,.article-image.float-right{{float:none;width:100%;margin:2rem 0;}}}}
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
<script>document.addEventListener('DOMContentLoaded',function(){{document.querySelectorAll('a[href*="apps.apple.com"]').forEach(function(link){{link.addEventListener('click',function(){{gtag('event','conversion',{{'send_to':'AW-17929124014/gDbcCLbkio4cEK7xouVC','value':1.0,'currency':'USD'}});}});}});}});</script>
</body></html>'''


def create_blog_html(post_data):
    fn = f"{post_data['date']}-{post_data['slug']}.html"
    d = datetime.strptime(post_data['date'], '%Y-%m-%d')
    html = get_html_template().format(title=post_data['title'],meta_description=post_data['meta_description'],keywords=post_data['keywords'],canonical_url=f"{BLOG_BASE_URL}/{fn}",website_url=WEBSITE_URL,app_store_url=APP_STORE_URL,hero_image=post_data['hero_image'],iso_date=d.isoformat(),formatted_date=d.strftime('%B %d, %Y'),read_time=post_data['read_time'],content=post_data['content'],year=datetime.now().year)
    return html, fn

def update_blog_index(post_data, filename):
    path = "blog/index.html"
    if not os.path.exists(path): print(f"Warning: {path} not found"); return False
    with open(path,'r',encoding='utf-8') as f: content = f.read()
    cat = post_data.get('category','Wellness')
    img = get_category_thumbnail(cat)
    d = datetime.strptime(post_data['date'],'%Y-%m-%d').strftime('%B %d, %Y')
    entry = f'''<article class="blog-card"><div class="blog-card-image" style="background-image: url('{img}');"><span class="blog-card-tag">{cat}</span></div><div class="blog-card-content"><h2><a href="{filename}">{post_data['title']}</a></h2><div class="blog-meta"><span>{d}</span><span>*</span><span>{post_data['read_time']} min read</span></div><p class="blog-excerpt">{post_data['meta_description']}</p><a href="{filename}" class="read-more">Read full article<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg></a></div></article>\n            '''
    marker = "<!--BLOG_ENTRIES_START-->"
    if marker in content:
        if 'class="blog-card featured"' in content: content = content.replace('class="blog-card featured"','class="blog-card"',1)
        entry = entry.replace('class="blog-card"','class="blog-card featured"')
        content = content.replace(marker, marker + "\n            " + entry)
        with open(path,'w',encoding='utf-8') as f: f.write(content)
        print(f"Updated {path}"); return True
    print(f"Warning: marker not found in {path}"); return False

def generate_rss_feed(blog_dir="blog"):
    rss_path = os.path.join(blog_dir,"rss.xml")
    if not os.path.exists(blog_dir): print(f"  Warning: {blog_dir} not found."); return
    posts = []
    for fname in sorted(os.listdir(blog_dir),reverse=True):
        if fname.endswith('.html') and fname != 'index.html':
            filepath = os.path.join(blog_dir,fname)
            try:
                if os.path.getsize(filepath) < 1024: continue
            except OSError: continue
            try:
                with open(filepath,'r',encoding='utf-8') as f: content = f.read(5000)
            except: continue
            title_match = re.search(r'<title>(.*?)\s*\|', content)
            title = title_match.group(1).strip() if title_match else fname
            desc_match = re.search(r'<meta\s+name="description"\s+content="(.*?)"', content)
            description = desc_match.group(1) if desc_match else ""
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', fname)
            pub_date = datetime.strptime(date_match.group(1),'%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 GMT') if date_match else ""
            posts.append({'title':title,'description':description,'url':f"{BLOG_BASE_URL}/{fname}",'pub_date':pub_date})
    posts = posts[:20]
    now = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    items = "".join(f"\n        <item><title>{p['title'].replace('&','&amp;').replace('<','&lt;')}</title><link>{p['url']}</link><guid isPermaLink=\"true\">{p['url']}</guid><description>{p['description'].replace('&','&amp;').replace('<','&lt;')}</description><pubDate>{p['pub_date']}</pubDate></item>" for p in posts)
    with open(rss_path,'w',encoding='utf-8') as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n    <channel>\n        <title>SteadiDay Blog - Health &amp; Wellness for Adults 50+</title>\n        <link>{WEBSITE_URL}/blog/index.html</link>\n        <description>Health and wellness tips for adults 50+.</description>\n        <language>en-us</language>\n        <lastBuildDate>{now}</lastBuildDate>\n        <atom:link href="{WEBSITE_URL}/blog/rss.xml" rel="self" type="application/rss+xml" />{items}\n    </channel>\n</rss>')
    print(f"  RSS feed updated: {rss_path} ({len(posts)} posts)")

def notify_buttondown(post_data, filename):
    api_key = os.environ.get('BUTTONDOWN_API_KEY')
    if not api_key: print("  BUTTONDOWN_API_KEY not set."); return
    url = f"{BLOG_BASE_URL}/{filename}"
    payload = json.dumps({"subject":f"New on SteadiDay: {post_data['title']}","body":f"# {post_data['title']}\n\n{post_data['meta_description']}\n\n**[Read the full article ->]({url})**\n\n---\n\n*[Download SteadiDay free]({APP_STORE_URL})*","status":"draft"}).encode('utf-8')
    req = urllib.request.Request("https://api.buttondown.com/v1/emails",data=payload,headers={"Authorization":f"Token {api_key}","Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            print("  Buttondown draft created!" if resp.status in (200,201) else f"  Buttondown status {resp.status}")
    except urllib.error.HTTPError as e: print(f"  Buttondown error {e.code}: {e.reason}")
    except Exception as e: print(f"  Buttondown failed: {e}")

def save_blog_post(html, filename):
    os.makedirs("blog",exist_ok=True)
    fp = os.path.join("blog",filename)
    with open(fp,'w',encoding='utf-8') as f: f.write(html)
    return fp

def set_github_env(key, value):
    ef = os.environ.get('GITHUB_ENV')
    if ef:
        with open(ef,'a') as f: f.write(f"{key}={value}\n")
    else: print(f"[ENV] {key}={value}")

def _check_duplicate(client, title, slug, existing_posts):
    dup,reason,_ = is_duplicate(title,slug,existing_posts)
    if dup: return True,reason
    sem_dup,sem_reason = check_semantic_duplicate(client,title,existing_posts)
    return (True,sem_reason) if sem_dup else (False,"")

def main():
    topic_override = None; use_news = False
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg == "--news": use_news = True
        elif arg: topic_override = arg
    if len(sys.argv) > 2 and sys.argv[2].strip() == "--news": use_news = True

    print("="*60); print("SteadiDay Blog Generator v5.1"); print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"Mode: {'Custom' if topic_override else 'News' if use_news else 'Pool'}")
    print(f"Model: {CLAUDE_MODEL} | Topics: {len(TOPIC_CATEGORIES)} | Categories: {len(VALID_CATEGORIES)}\n")

    print("Scanning existing posts...")
    existing = get_existing_posts()
    print(f"Found {len(existing)} existing posts")
    for p in existing[:10]: print(f"  - {p['title'] or p['filename']}" + (f" [{p['category']}]" if p.get('category') else ""))
    if len(existing) > 10: print(f"  ... and {len(existing)-10} more")
    print()

    client = anthropic.Anthropic()
    excluded_cats = list(set(get_recent_categories(existing)))

    if topic_override:
        print(f"Custom topic: {topic_override}")
        td = {"topic":topic_override,"keyword":topic_override.lower(),"category":"Wellness"}
    elif use_news:
        print("Generating news-driven topic...")
        td = generate_news_driven_topic(client,existing,excluded_categories=excluded_cats)
        print(f"  Topic: {td['topic']}\n  Category: {td['category']}")
    else:
        print("Selecting from topic pool...")
        td = select_unique_topic(existing)
        if td is None:
            print("All pool topics used! Switching to news-driven...")
            td = generate_news_driven_topic(client,existing,excluded_categories=excluded_cats)
        else: print(f"  Selected: {td['topic']}\n  Category: {td['category']}")

    print("\nGenerating content...")
    post = generate_blog_post(td,existing,client)
    slug = '-'.join(re.sub(r'[^a-z0-9\s]','',post['title'].lower()).split()[:5])
    dup,reason = _check_duplicate(client,post['title'],slug,existing)

    if dup:
        print(f"  Duplicate (attempt 1): {reason}\n  Retrying news-driven...")
        td = generate_news_driven_topic(client,existing,excluded_categories=excluded_cats)
        post = generate_blog_post(td,existing,client)
        slug = '-'.join(re.sub(r'[^a-z0-9\s]','',post['title'].lower()).split()[:5])
        dup,reason = _check_duplicate(client,post['title'],slug,existing)
    if dup:
        print(f"  Duplicate (attempt 2): {reason}\n  Forcing different category...")
        td = generate_news_driven_topic(client,existing,excluded_categories=list(set(excluded_cats+[td.get('category','')])))
        post = generate_blog_post(td,existing,client)
        slug = '-'.join(re.sub(r'[^a-z0-9\s]','',post['title'].lower()).split()[:5])
        dup,reason = _check_duplicate(client,post['title'],slug,existing)
    if dup: print(f"  Still duplicate after 3 attempts: {reason}"); sys.exit(1)

    print(f"\n  Title: {post['title']} ({len(post['title'])} chars)\n  Category: {post['category']}\n  Duplicate check: PASS")
    html, fn = create_blog_html(post)
    fp = save_blog_post(html, fn)
    print(f"  Saved: {fp}\n")
    update_blog_index(post, fn)
    print("\nGenerating RSS feed..."); generate_rss_feed()
    print("\nCreating Buttondown draft..."); notify_buttondown(post, fn)
    set_github_env("BLOG_TITLE",post['title']); set_github_env("BLOG_FILENAME",fn); set_github_env("BLOG_DATE",post['date'])
    print(f"\nDone! Published: {post['title']}")

if __name__ == "__main__":
    main()
