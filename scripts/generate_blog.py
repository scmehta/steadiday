#!/usr/bin/env python3
"""
SteadiDay Blog Generator v2.0
- Duplicate detection: scans existing posts, refuses overlapping content
- News-driven topics: Claude generates fresh angles when pool is exhausted
- 40+ unique topics in expanded pool
- All waitlist references replaced with App Store links
"""

import anthropic
import random
import re
import os
import sys
import glob
from datetime import datetime
from difflib import SequenceMatcher

WEBSITE_URL = "https://www.steadiday.com"
BLOG_BASE_URL = f"{WEBSITE_URL}/blog"
APP_STORE_URL = "https://apps.apple.com/app/steadiday/id6758526744"

def get_existing_posts(blog_dir="blog"):
    existing = []
    if not os.path.exists(blog_dir):
        return existing
    for filepath in glob.glob(os.path.join(blog_dir, "*.html")):
        filename = os.path.basename(filepath)
        if filename == "index.html":
            continue
        title = ""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read(5000)
                m = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
                if m:
                    title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        except Exception:
            pass
        slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', filename.replace('.html', ''))
        existing.append({"filename": filename, "title": title, "slug": slug})
    return existing

def is_duplicate(new_title, new_slug, existing_posts, threshold=0.65):
    ntl = new_title.lower().strip()
    nsl = new_slug.lower().strip()
    for post in existing_posts:
        if SequenceMatcher(None, ntl, post['title'].lower()).ratio() >= threshold:
            return (True, f"Title too similar", post['filename'])
        if SequenceMatcher(None, nsl, post['slug'].lower()).ratio() >= 0.75:
            return (True, f"Slug too similar", post['filename'])
        stop = {'the','a','an','for','and','or','to','of','in','your','how','that','with','after','from'}
        nw = set(ntl.split()) - stop
        ew = set(post['title'].lower().split()) - stop
        if nw and ew:
            overlap = nw & ew
            if len(overlap) >= 3 and len(overlap)/min(len(nw),len(ew)) >= 0.7:
                return (True, f"Keyword overlap: {overlap}", post['filename'])
    return (False, "", "")

def generate_news_driven_topic(client, existing_posts):
    existing_titles = [p['title'] for p in existing_posts if p['title']]
    avoid = "\n".join([f"- {t}" for t in existing_titles]) if existing_titles else "None yet."
    prompt = f"""You are a blog strategist for SteadiDay, a wellness app for adults 50+.
Suggest ONE fresh blog topic based on recent health news/research for adults 50+.

EXISTING POSTS (do NOT duplicate):
{avoid}

Consider: seasonal health, new studies, eye/dental/hearing health, arthritis, digestive health, skin care, gardening, pets, caregiver wellness, financial wellness, travel health, music therapy.

FORMAT:
TOPIC: [description]
TITLE: [under 55 chars]
KEYWORD: [SEO phrase]
CATEGORY: [Mental Wellness|Medication Tips|Healthy Aging|Exercise|Nutrition|Sleep|Heart Health|Brain Health|Safety|Wellness]
ANGLE: [what makes this fresh]"""
    msg = client.messages.create(model="claude-sonnet-4-20250514", max_tokens=500, messages=[{"role":"user","content":prompt}])
    r = msg.content[0].text
    topic = re.search(r'TOPIC:\s*(.+?)(?:\n|$)', r)
    title = re.search(r'TITLE:\s*(.+?)(?:\n|$)', r)
    kw = re.search(r'KEYWORD:\s*(.+?)(?:\n|$)', r)
    cat = re.search(r'CATEGORY:\s*(.+?)(?:\n|$)', r)
    angle = re.search(r'ANGLE:\s*(.+?)(?:\n|$)', r)
    valid = ["Mental Wellness","Medication Tips","Healthy Aging","Exercise","Nutrition","Sleep","Heart Health","Brain Health","Safety","Wellness"]
    c = cat.group(1).strip() if cat else "Wellness"
    if c not in valid: c = "Wellness"
    return {
        "topic": topic.group(1).strip() if topic else "Health tips for adults 50+",
        "keyword": kw.group(1).strip() if kw else "health tips seniors",
        "category": c,
        "suggested_title": title.group(1).strip() if title else "",
        "angle": angle.group(1).strip() if angle else ""
    }

TOPIC_CATEGORIES = [
    {"topic": "Simple morning stretches for better mobility", "keyword": "morning stretches seniors", "category": "Exercise"},
    {"topic": "Walking for health: Getting started safely", "keyword": "walking exercise seniors", "category": "Exercise"},
    {"topic": "Chair exercises you can do while watching TV", "keyword": "chair exercises seniors", "category": "Exercise"},
    {"topic": "Balance exercises to prevent falls at home", "keyword": "balance exercises seniors", "category": "Exercise"},
    {"topic": "Gentle yoga poses for beginners over 50", "keyword": "yoga seniors beginners", "category": "Exercise"},
    {"topic": "How to build a medication routine that sticks", "keyword": "medication routine tips", "category": "Medication Tips"},
    {"topic": "Understanding common medication side effects", "keyword": "medication side effects", "category": "Medication Tips"},
    {"topic": "Questions to ask your pharmacist at every visit", "keyword": "pharmacist questions seniors", "category": "Medication Tips"},
    {"topic": "How to safely store medications at home", "keyword": "medication storage tips", "category": "Medication Tips"},
    {"topic": "Understanding your blood pressure numbers", "keyword": "blood pressure explained", "category": "Heart Health"},
    {"topic": "Foods that naturally lower cholesterol", "keyword": "lower cholesterol naturally", "category": "Heart Health"},
    {"topic": "Warning signs your heart needs attention", "keyword": "heart warning signs seniors", "category": "Heart Health"},
    {"topic": "5 brain exercises to keep your mind sharp", "keyword": "brain exercises seniors", "category": "Brain Health"},
    {"topic": "Simple memory improvement techniques", "keyword": "memory improvement seniors", "category": "Brain Health"},
    {"topic": "How social connection protects your brain", "keyword": "social connection brain health", "category": "Brain Health"},
    {"topic": "Crosswords puzzles and games for cognitive health", "keyword": "brain games seniors", "category": "Brain Health"},
    {"topic": "The importance of staying hydrated as we age", "keyword": "hydration tips elderly", "category": "Nutrition"},
    {"topic": "Heart-healthy recipes that are easy to make", "keyword": "heart healthy recipes seniors", "category": "Nutrition"},
    {"topic": "Healthy snacks for sustained energy", "keyword": "healthy snacks seniors", "category": "Nutrition"},
    {"topic": "Anti-inflammatory foods for joint pain relief", "keyword": "anti inflammatory foods seniors", "category": "Nutrition"},
    {"topic": "Meal planning made simple for one or two", "keyword": "meal planning seniors", "category": "Nutrition"},
    {"topic": "Calcium and vitamin D for strong bones", "keyword": "calcium vitamin D seniors", "category": "Nutrition"},
    {"topic": "Sleep tips for a more restful night", "keyword": "sleep tips older adults", "category": "Sleep"},
    {"topic": "Why sleep patterns change as we age", "keyword": "sleep changes aging", "category": "Sleep"},
    {"topic": "Creating a bedtime routine that works", "keyword": "bedtime routine seniors", "category": "Sleep"},
    {"topic": "Managing stress through breathing exercises", "keyword": "breathing exercises stress", "category": "Mental Wellness"},
    {"topic": "Staying social: Why connection matters", "keyword": "social connection elderly", "category": "Mental Wellness"},
    {"topic": "Dealing with loneliness after retirement", "keyword": "loneliness retirement seniors", "category": "Mental Wellness"},
    {"topic": "Gratitude journaling for better mental health", "keyword": "gratitude journal seniors", "category": "Mental Wellness"},
    {"topic": "How volunteering boosts your wellbeing", "keyword": "volunteering seniors benefits", "category": "Mental Wellness"},
    {"topic": "How to prevent falls at home", "keyword": "fall prevention seniors", "category": "Safety"},
    {"topic": "Home safety checklist for aging in place", "keyword": "home safety seniors checklist", "category": "Safety"},
    {"topic": "Staying safe in extreme heat and cold", "keyword": "weather safety seniors", "category": "Safety"},
    {"topic": "Managing chronic pain naturally", "keyword": "chronic pain management seniors", "category": "Wellness"},
    {"topic": "The health benefits of gardening after 50", "keyword": "gardening health benefits seniors", "category": "Wellness"},
    {"topic": "How pets improve health and happiness", "keyword": "pets health benefits seniors", "category": "Wellness"},
    {"topic": "Eye health tips to protect your vision", "keyword": "eye health tips seniors", "category": "Wellness"},
    {"topic": "Hearing health and when to get tested", "keyword": "hearing health seniors", "category": "Wellness"},
    {"topic": "Skin care and sun protection after 50", "keyword": "skin care seniors sun protection", "category": "Wellness"},
    {"topic": "Managing arthritis pain with daily habits", "keyword": "arthritis management seniors", "category": "Wellness"},
    {"topic": "Digestive health tips for adults over 50", "keyword": "digestive health seniors", "category": "Wellness"},
]

CATEGORY_IMAGES = {
    "Mental Wellness": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80",
    "Medication Tips": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&q=80",
    "Healthy Aging": "https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=800&q=80",
    "Exercise": "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80",
    "Nutrition": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80",
    "Sleep": "https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=800&q=80",
    "Heart Health": "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80",
    "Brain Health": "https://images.unsplash.com/photo-1559757175-5700dde675bc?w=800&q=80",
    "Safety": "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80",
    "Wellness": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80",
}

HERO_IMAGES = {
    "Mental Wellness": ["https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=1200&q=80","https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=1200&q=80"],
    "Medication Tips": ["https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1200&q=80","https://images.unsplash.com/photo-1471864190281-a93a3070b6de?w=1200&q=80","https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=1200&q=80"],
    "Healthy Aging": ["https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=1200&q=80","https://images.unsplash.com/photo-1516307365426-bea591f05011?w=1200&q=80","https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=1200&q=80"],
    "Exercise": ["https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80","https://images.unsplash.com/photo-1486218119243-13883505764c?w=1200&q=80","https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=1200&q=80"],
    "Nutrition": ["https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80","https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=1200&q=80","https://images.unsplash.com/photo-1606923829579-0cb981a83e2e?w=1200&q=80"],
    "Sleep": ["https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=1200&q=80","https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=1200&q=80","https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=1200&q=80"],
    "Heart Health": ["https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=1200&q=80","https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=1200&q=80","https://images.unsplash.com/photo-1628348070889-cb656235b4eb?w=1200&q=80"],
    "Brain Health": ["https://images.unsplash.com/photo-1559757175-5700dde675bc?w=1200&q=80","https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=1200&q=80","https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&q=80"],
    "Safety": ["https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80","https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=1200&q=80"],
    "Wellness": ["https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80","https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80","https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=1200&q=80"],
}

INLINE_IMAGES = {
    "Mental Wellness": [{"url":"https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80","alt":"Person relaxing peacefully"},{"url":"https://images.unsplash.com/photo-1508672019048-805c876b67e2?w=800&q=80","alt":"Peaceful beach scene"},{"url":"https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80","alt":"Meditation hands"},{"url":"https://images.unsplash.com/photo-1515377905703-c4788e51af15?w=800&q=80","alt":"Sunlight through trees"},{"url":"https://images.unsplash.com/photo-1528715471579-d1bcf0ba5e83?w=800&q=80","alt":"Calm space with plants"}],
    "Medication Tips": [{"url":"https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=800&q=80","alt":"Pill organizer"},{"url":"https://images.unsplash.com/photo-1576602976047-174e57a47881?w=800&q=80","alt":"Healthcare professional"},{"url":"https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80","alt":"Healthy lifestyle"},{"url":"https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800&q=80","alt":"Morning routine"},{"url":"https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","alt":"Doctor consultation"}],
    "Healthy Aging": [{"url":"https://images.unsplash.com/photo-1516307365426-bea591f05011?w=800&q=80","alt":"Active senior outdoors"},{"url":"https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80","alt":"Healthy choices"},{"url":"https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&q=80","alt":"Couple walking"},{"url":"https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=800&q=80","alt":"Family moment"},{"url":"https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=800&q=80","alt":"Active aging"}],
    "Exercise": [{"url":"https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80","alt":"Stretching at home"},{"url":"https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=800&q=80","alt":"Resistance training"},{"url":"https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=800&q=80","alt":"Walking outdoors"},{"url":"https://images.unsplash.com/photo-1518611012118-696072aa579a?w=800&q=80","alt":"Group fitness"},{"url":"https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","alt":"Yoga exercises"}],
    "Nutrition": [{"url":"https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=800&q=80","alt":"Meal preparation"},{"url":"https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=800&q=80","alt":"Fresh produce"},{"url":"https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=800&q=80","alt":"Balanced meal"},{"url":"https://images.unsplash.com/photo-1606923829579-0cb981a83e2e?w=800&q=80","alt":"Salmon dish"},{"url":"https://images.unsplash.com/photo-1544025162-d76694265947?w=800&q=80","alt":"Cooking at home"}],
    "Sleep": [{"url":"https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=800&q=80","alt":"Peaceful bedroom"},{"url":"https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=800&q=80","alt":"Bedtime routine"},{"url":"https://images.unsplash.com/photo-1495197359483-d092478c170a?w=800&q=80","alt":"Comfortable bed"},{"url":"https://images.unsplash.com/photo-1544027993-37dbfe43562a?w=800&q=80","alt":"Herbal tea"},{"url":"https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80","alt":"Morning light"}],
    "Heart Health": [{"url":"https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80","alt":"Healthy lifestyle"},{"url":"https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80","alt":"Fresh vegetables"},{"url":"https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80","alt":"Cardio exercise"},{"url":"https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=800&q=80","alt":"Jogging outdoors"},{"url":"https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=80","alt":"Heart-healthy meal"}],
    "Brain Health": [{"url":"https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=800&q=80","alt":"Learning and education"},{"url":"https://images.unsplash.com/photo-1456406644174-8ddd4cd52a06?w=800&q=80","alt":"Reading"},{"url":"https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=800&q=80","alt":"Puzzles and games"},{"url":"https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&q=80","alt":"Social connection"},{"url":"https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80","alt":"Relaxation"}],
    "Safety": [{"url":"https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=800&q=80","alt":"Home safety"},{"url":"https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=800&q=80","alt":"Medical guidance"},{"url":"https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80","alt":"Well-lit home"},{"url":"https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&q=80","alt":"Accessible design"},{"url":"https://images.unsplash.com/photo-1494438639946-1ebd1d20bf85?w=800&q=80","alt":"Clear pathways"}],
    "Wellness": [{"url":"https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80","alt":"Mindfulness"},{"url":"https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80","alt":"Yoga"},{"url":"https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80","alt":"Morning wellness"},{"url":"https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80","alt":"Self-care"},{"url":"https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=800&q=80","alt":"Nature walk"}],
}

CATEGORY_VIDEOS = {
    "Mental Wellness": [{"id":"inpok4MKVLM","title":"5-Minute Meditation","channel":"Goodful"},{"id":"ZToicYcHIOU","title":"Breathing for Stress Relief","channel":"Therapy in a Nutshell"},{"id":"SEfs5TJZ6Nk","title":"How to Practice Mindfulness","channel":"Psych Hub"}],
    "Medication Tips": [{"id":"xLUaVeKhbK8","title":"Managing Multiple Medications","channel":"AARP"},{"id":"Ry_bVsdcYvM","title":"Organize Your Medications","channel":"Walgreens"},{"id":"QB1kk0p_E0I","title":"Understanding Prescriptions","channel":"Cleveland Clinic"}],
    "Healthy Aging": [{"id":"3PycZtfns_U","title":"Secrets to Healthy Aging","channel":"Mayo Clinic"},{"id":"TUqEu0mBMr8","title":"Staying Active as You Age","channel":"AARP"}],
    "Exercise": [{"id":"6cJuPmYp7lE","title":"Gentle Morning Stretch","channel":"SilverSneakers"},{"id":"8Oh3q4BC4y8","title":"Seated Exercises","channel":"More Life Health"},{"id":"sRZ4IqwvHH8","title":"Balance Exercises","channel":"Bob & Brad"}],
    "Nutrition": [{"id":"fqhYBTg73fw","title":"Healthy Eating Tips","channel":"AARP"},{"id":"TRov4mMb_B4","title":"Mediterranean Diet","channel":"Cleveland Clinic"},{"id":"vBEI3JXxLJM","title":"Anti-Inflammatory Foods","channel":"Dr. Eric Berg DC"}],
    "Sleep": [{"id":"t0kACis_dJE","title":"Sleep Hygiene Tips","channel":"Mayo Clinic"},{"id":"LFBjI3RA2JI","title":"Fall Asleep Faster","channel":"Cleveland Clinic"}],
    "Heart Health": [{"id":"pBrEhtfrVsE","title":"Heart Healthy Tips","channel":"AHA"},{"id":"RQSl6Dnsf68","title":"Understanding Blood Pressure","channel":"Cleveland Clinic"},{"id":"LXb3EKWsInQ","title":"Heart-Healthy Foods","channel":"Mayo Clinic"}],
    "Brain Health": [{"id":"LNHBMFCzznE","title":"Keep Your Brain Sharp","channel":"AARP"},{"id":"pIlTb6SjR_g","title":"Memory Tips","channel":"TED-Ed"},{"id":"f7Dl6a9i0wY","title":"Brain Foods","channel":"Cleveland Clinic"}],
    "Safety": [{"id":"8Gq3D_YOYew","title":"Fall Prevention","channel":"Bob & Brad"},{"id":"TLWGn5HD_0I","title":"Home Safety Checklist","channel":"AARP"}],
    "Wellness": [{"id":"inpok4MKVLM","title":"Morning Meditation","channel":"Goodful"},{"id":"6cJuPmYp7lE","title":"Full Body Stretch","channel":"SilverSneakers"},{"id":"SEfs5TJZ6Nk","title":"Intro to Mindfulness","channel":"Psych Hub"}],
}

STEADIDAY_FEATURES = {"free":["Emergency SOS button","Fall Detection","Trusted Contacts","Medication reminders","Apple Health integration","Food and water logging","Mind Breaks games","Calendar sync","Magnifier tool","Find My Car","Flashlight"]}

def get_html_template():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | SteadiDay Blog</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="SteadiDay Team">
    <meta name="robots" content="index, follow">
    <meta name="apple-itunes-app" content="app-id=6758526744">
    <link rel="canonical" href="{canonical_url}">
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
</body>
</html>
'''

def get_images_for_category(category):
    hero_options = HERO_IMAGES.get(category, HERO_IMAGES['Wellness'])
    inline_options = INLINE_IMAGES.get(category, INLINE_IMAGES['Wellness'])
    n = random.choice([4, 5])
    return {"hero": random.choice(hero_options), "inline": random.sample(inline_options, min(n, len(inline_options)))}

def get_video_for_category(category):
    return random.choice(CATEGORY_VIDEOS.get(category, CATEGORY_VIDEOS['Wellness']))

def select_unique_topic(existing_posts):
    random.shuffle(TOPIC_CATEGORIES)
    for td in TOPIC_CATEGORIES:
        sw = re.sub(r'[^a-z0-9\s]', '', td['topic'].lower()).split()[:5]
        ts = '-'.join(sw)
        dup, _, _ = is_duplicate(td['topic'], ts, existing_posts)
        if not dup:
            return td
    return None

def generate_blog_post(topic_data, existing_posts):
    client = anthropic.Anthropic()
    topic = topic_data["topic"]
    keyword = topic_data["keyword"]
    category = topic_data.get("category", "Wellness")
    images = get_images_for_category(category)
    video = get_video_for_category(category)
    num_images = len(images["inline"])
    feature = random.choice(STEADIDAY_FEATURES["free"])
    img_ph = "\n".join([f"After section {i+2}, insert exactly: [IMAGE_{i+1}]" for i in range(num_images)])
    existing_titles = [p['title'] for p in existing_posts if p['title']]
    avoid = "\n".join([f"- {t}" for t in existing_titles[:20]]) if existing_titles else "None."

    prompt = f"""You are a health and wellness content writer for SteadiDay, an app for adults 50+.
Write a blog post about: "{topic}"
CRITICAL: Must be UNIQUE. Do NOT overlap with:
{avoid}
REQUIREMENTS:
1. TITLE under 55 characters, clearly different from existing posts
2. 1000-1500 words, warm tone, 6-7 sections with <h2> tags
3. Mention SteadiDay's {feature} naturally (all features are free)
4. Include at least one statistic with source
MEDIA PLACEHOLDERS:
{img_ph}
After section 4: [VIDEO]
FORMAT:
TITLE: [under 55 chars]
META_DESCRIPTION: [150-160 chars]
KEYWORDS: keyword1, keyword2, {keyword}
READ_TIME: X
CONTENT:
<p>Opening...</p>
<h2>Section</h2>
<p>Content...</p>"""

    msg = client.messages.create(model="claude-sonnet-4-20250514", max_tokens=4500, messages=[{"role":"user","content":prompt}])
    r = msg.content[0].text
    title = (re.search(r'TITLE:\s*(.+?)(?:\n|$)', r) or type('',(),{'group':lambda s,i:topic})()).group(1).strip()
    meta = (re.search(r'META_DESCRIPTION:\s*(.+?)(?:\n|$)', r) or type('',(),{'group':lambda s,i:f"Tips about {topic} for adults 50+"})()).group(1).strip()
    kws = (re.search(r'KEYWORDS:\s*(.+?)(?:\n|$)', r) or type('',(),{'group':lambda s,i:keyword})()).group(1).strip()
    rt = (re.search(r'READ_TIME:\s*(\d+)', r) or type('',(),{'group':lambda s,i:"7"})()).group(1)
    content = (re.search(r'CONTENT:\s*(.+)', r, re.DOTALL) or type('',(),{'group':lambda s,i:r})()).group(1).strip()
    if len(title) > 55: title = title[:52].rsplit(' ',1)[0] + "..."
    for i, img in enumerate(images["inline"]):
        content = content.replace(f"[IMAGE_{i+1}]", f'<figure class="article-image"><img src="{img["url"]}" alt="{img["alt"]}" loading="lazy"><figcaption>{img["alt"]}</figcaption></figure>')
    content = content.replace("[VIDEO]", f'<div class="video-container"><iframe src="https://www.youtube-nocookie.com/embed/{video["id"]}" title="{video["title"]}" frameborder="0" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div><p class="video-caption">Video: {video["title"]} — {video["channel"]}</p>')
    content = re.sub(r'\[IMAGE_\d+\]', '', content)
    content = content.replace("[VIDEO]", '')
    slug = '-'.join(re.sub(r'[^a-z0-9\s]', '', title.lower()).split()[:5])
    return {"title":title,"meta_description":meta,"keywords":kws,"read_time":rt,"content":content,"slug":slug,"category":category,"hero_image":images["hero"],"video":video,"num_images":num_images,"date":datetime.now().strftime('%Y-%m-%d')}

def create_blog_html(post_data):
    template = get_html_template()
    fn = f"{post_data['date']}-{post_data['slug']}.html"
    curl = f"{BLOG_BASE_URL}/{fn}"
    d = datetime.strptime(post_data['date'], '%Y-%m-%d')
    html = template.format(title=post_data['title'], meta_description=post_data['meta_description'], keywords=post_data['keywords'], canonical_url=curl, website_url=WEBSITE_URL, app_store_url=APP_STORE_URL, hero_image=post_data['hero_image'], iso_date=d.isoformat(), formatted_date=d.strftime('%B %d, %Y'), read_time=post_data['read_time'], content=post_data['content'], year=datetime.now().year)
    return html, fn

def update_blog_index(post_data, filename):
    path = "blog/index.html"
    if not os.path.exists(path): print(f"Warning: {path} not found"); return False
    with open(path,'r',encoding='utf-8') as f: content = f.read()
    cat = post_data.get('category','Wellness')
    img = CATEGORY_IMAGES.get(cat, CATEGORY_IMAGES['Wellness'])
    d = datetime.strptime(post_data['date'],'%Y-%m-%d').strftime('%B %d, %Y')
    entry = f'''<article class="blog-card">
                <div class="blog-card-image" style="background-image: url('{img}');"><span class="blog-card-tag">{cat}</span></div>
                <div class="blog-card-content">
                    <h2><a href="{filename}">{post_data['title']}</a></h2>
                    <div class="blog-meta"><span>{d}</span><span>•</span><span>{post_data['read_time']} min read</span></div>
                    <p class="blog-excerpt">{post_data['meta_description']}</p>
                    <a href="{filename}" class="read-more">Read full article<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg></a>
                </div></article>\n            '''
    marker = "<!--BLOG_ENTRIES_START-->"
    if marker in content:
        if 'class="blog-card featured"' in content: content = content.replace('class="blog-card featured"','class="blog-card"',1)
        entry = entry.replace('class="blog-card"','class="blog-card featured"')
        content = content.replace(marker, marker+"\n            "+entry)
        with open(path,'w',encoding='utf-8') as f: f.write(content)
        print(f"Updated {path}"); return True
    print(f"Warning: marker not found"); return False

def save_blog_post(html, filename):
    os.makedirs("blog", exist_ok=True)
    fp = os.path.join("blog", filename)
    with open(fp,'w',encoding='utf-8') as f: f.write(html)
    return fp

def set_github_env(k,v):
    ef = os.environ.get('GITHUB_ENV')
    if ef:
        with open(ef,'a') as f: f.write(f"{k}={v}\n")
    else: print(f"[ENV] {k}={v}")

def main():
    topic_override = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "--news" else None
    use_news = "--news" in sys.argv
    print("="*60); print("SteadiDay Blog Generator v2.0"); print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"URL: {WEBSITE_URL}\n")
    print("Scanning existing posts...")
    existing = get_existing_posts()
    print(f"Found {len(existing)} existing posts\n")
    client = anthropic.Anthropic()
    if topic_override:
        print(f"Custom topic: {topic_override}")
        td = {"topic":topic_override,"keyword":topic_override.lower(),"category":"Wellness"}
    elif use_news:
        print("Generating news-driven topic...")
        td = generate_news_driven_topic(client, existing)
        print(f"Topic: {td['topic']}\nCategory: {td['category']}")
        if td.get('angle'): print(f"Angle: {td['angle']}")
    else:
        print("Selecting unique topic from pool...")
        td = select_unique_topic(existing)
        if td is None:
            print("All pool topics used! Switching to news-driven...")
            td = generate_news_driven_topic(client, existing)
        print(f"Selected: {td['topic']}\nCategory: {td['category']}")
    print("\nGenerating content...")
    post = generate_blog_post(td, existing)
    slug = '-'.join(re.sub(r'[^a-z0-9\s]','',post['title'].lower()).split()[:5])
    dup, reason, sim = is_duplicate(post['title'], slug, existing)
    if dup:
        print(f"Duplicate detected ({reason}), retrying with news topic...")
        td = generate_news_driven_topic(client, existing)
        post = generate_blog_post(td, existing)
        slug = '-'.join(re.sub(r'[^a-z0-9\s]','',post['title'].lower()).split()[:5])
        dup2, r2, s2 = is_duplicate(post['title'], slug, existing)
        if dup2: print(f"Still duplicate. Use custom topic."); sys.exit(1)
    print(f"Title: {post['title']} ({len(post['title'])} chars)")
    print(f"Duplicate check: PASS")
    html, fn = create_blog_html(post)
    print(f"File: {fn}")
    fp = save_blog_post(html, fn)
    print(f"Saved: {fp}\n")
    update_blog_index(post, fn)
    set_github_env("BLOG_TITLE", post['title'])
    set_github_env("BLOG_FILENAME", fn)
    print(f"\nDone! {post['title']}")
    print(f"\nUsage:")
    print(f"  python generate_blog.py              # Random unique topic")
    print(f"  python generate_blog.py --news       # News-driven fresh topic")
    print(f'  python generate_blog.py "Your topic"  # Custom topic')

if __name__ == "__main__":
    main()
