#!/usr/bin/env python3
"""
SteadiDay Blog Generator
Generates weekly HTML blog posts targeted at adults 50+ focused on health, wellness, and better living.
Designed for a plain HTML website hosted on GitHub Pages.
"""

import os
import sys
import random
from datetime import datetime
import anthropic
import re

# Blog topics optimized for SEO - targeting searches your 50+ audience actually makes
TOPIC_CATEGORIES = [
    {"topic": "How to remember to take medication every day", "keyword": "how to remember to take medication"},
    {"topic": "Best pill reminder apps for seniors", "keyword": "pill reminder app for seniors"},
    {"topic": "What to do when you forget to take your medication", "keyword": "forgot to take medication"},
    {"topic": "How to keep track of multiple medications", "keyword": "how to keep track of medications"},
    {"topic": "Managing medications for elderly parents", "keyword": "managing medications for elderly parents"},
    {"topic": "How to create a medication schedule that works", "keyword": "medication schedule"},
    {"topic": "Best health apps for seniors in 2026", "keyword": "best health apps for seniors"},
    {"topic": "How to track your health at home", "keyword": "how to track health at home"},
    {"topic": "Simple ways to monitor blood pressure daily", "keyword": "monitor blood pressure at home"},
    {"topic": "Health metrics everyone over 50 should track", "keyword": "health metrics to track"},
    {"topic": "Morning routine for healthy aging", "keyword": "morning routine for seniors"},
    {"topic": "How to stay healthy after 50", "keyword": "how to stay healthy after 50"},
    {"topic": "Daily habits that improve longevity", "keyword": "daily habits for longevity"},
    {"topic": "How to have more energy after 60", "keyword": "how to have more energy after 60"},
    {"topic": "Best exercises for adults over 50", "keyword": "exercises for over 50"},
    {"topic": "How to improve sleep quality after 50", "keyword": "sleep tips for seniors"},
    {"topic": "How to reduce stress and anxiety naturally", "keyword": "reduce stress naturally"},
    {"topic": "Mindfulness exercises for beginners over 50", "keyword": "mindfulness for seniors"},
    {"topic": "How to stay mentally sharp as you age", "keyword": "stay mentally sharp"},
    {"topic": "Daily brain exercises for seniors", "keyword": "brain exercises for seniors"},
    {"topic": "How to help aging parents manage their health", "keyword": "help aging parents health"},
    {"topic": "Tools to help seniors live independently", "keyword": "tools for senior independence"},
    {"topic": "How to prepare for a doctor's appointment", "keyword": "prepare for doctor appointment"},
    {"topic": "Questions to ask your doctor after 50", "keyword": "questions to ask doctor"},
    {"topic": "Why do I keep forgetting things and what to do about it", "keyword": "why do i keep forgetting things"},
    {"topic": "How to stop feeling overwhelmed by health tasks", "keyword": "overwhelmed by health management"},
    {"topic": "Simple ways to organize your daily health routine", "keyword": "organize health routine"},
]

STEADIDAY_FEATURES = {
    "free": [
        "medication reminders",
        "daily task management", 
        "simple health tracking",
        "mindful break exercises",
    ],
    "premium": [
        "advanced health insights and trends",
        "Apple Health integration for automatic tracking",
        "unlimited medication tracking",
        "personalized wellness recommendations",
        "detailed progress reports",
    ]
}

# UPDATE THESE with your actual links
APP_LINKS = {
    "website": "https://www.steadiday.com",
    "base_url": "https://scm-solutions-llc.github.io/steadiday",
}

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - SteadiDay Blog</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical_url}">
    
    <link rel="canonical" href="{canonical_url}">
    
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.7;
            color: #333;
            background-color: #f8f9fa;
        }}
        
        .nav {{
            background: white;
            padding: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .nav-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .nav a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }}
        
        .nav a:hover {{ text-decoration: underline; }}
        
        .article-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 60px 20px;
            text-align: center;
        }}
        
        .article-header h1 {{
            max-width: 800px;
            margin: 0 auto 15px;
            font-size: 2.2rem;
            line-height: 1.3;
        }}
        
        .article-meta {{
            font-size: 1rem;
            opacity: 0.9;
        }}
        
        .article-container {{
            max-width: 700px;
            margin: 0 auto;
            padding: 40px 20px;
            background: white;
            margin-top: -30px;
            border-radius: 12px 12px 0 0;
            position: relative;
        }}
        
        .article-content h2 {{
            font-size: 1.5rem;
            margin: 35px 0 15px;
            color: #333;
        }}
        
        .article-content p {{
            margin-bottom: 20px;
            font-size: 1.1rem;
            color: #444;
        }}
        
        .article-content a {{ color: #667eea; }}
        .article-content a:hover {{ text-decoration: none; }}
        
        .cta-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin: 40px 0;
        }}
        
        .cta-box h3 {{
            margin-bottom: 10px;
            font-size: 1.3rem;
        }}
        
        .cta-box p {{
            color: white !important;
            margin-bottom: 15px;
        }}
        
        .cta-button {{
            display: inline-block;
            background: white;
            color: #667eea;
            padding: 12px 30px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
        }}
        
        .cta-button:hover {{ opacity: 0.9; }}
        
        .back-to-blog {{
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            text-align: center;
            background: white;
        }}
        
        .back-to-blog a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: #666;
            font-size: 0.9rem;
            background: white;
        }}
        
        .footer a {{ color: #667eea; }}
    </style>
</head>
<body>
    <nav class="nav">
        <div class="nav-container">
            <a href="index.html">← Back to Blog</a>
            <a href="{website_url}">Download SteadiDay</a>
        </div>
    </nav>
    
    <header class="article-header">
        <h1>{title}</h1>
        <div class="article-meta">{formatted_date} • By SteadiDay Team • {read_time} min read</div>
    </header>
    
    <article class="article-container">
        <div class="article-content">
            {content}
            
            <div class="cta-box">
                <h3>Ready to Take Control of Your Health?</h3>
                <p>SteadiDay helps you manage medications, track your wellness, and build healthy habits—all designed for adults 50+.</p>
                <a href="{website_url}" class="cta-button">Download SteadiDay Free</a>
            </div>
        </div>
    </article>
    
    <div class="back-to-blog">
        <a href="index.html">← See all blog posts</a>
    </div>
    
    <footer class="footer">
        <p>&copy; {year} SteadiDay. All rights reserved. | <a href="../index.html">Home</a> | <a href="../liability.html">Terms</a></p>
    </footer>
</body>
</html>
'''


def generate_blog_post(topic: str = None) -> dict:
    """Generate a blog post using Claude API."""
    
    client = anthropic.Anthropic()
    
    if not topic:
        selected = random.choice(TOPIC_CATEGORIES)
        topic = selected["topic"]
        target_keyword = selected["keyword"]
    else:
        target_keyword = topic.lower()
    
    free_feature = random.choice(STEADIDAY_FEATURES["free"])
    premium_feature = random.choice(STEADIDAY_FEATURES["premium"])
    
    prompt = f"""You are a health and wellness content writer for SteadiDay, a mobile app for adults 50+.

Write a blog post about: "{topic}"

TARGET KEYWORD FOR SEO: "{target_keyword}"
Include this keyword phrase naturally 3-5 times throughout the article.

WRITING STYLE:
Write like a real person, not an AI:
- NEVER use bullet points, dashes, or numbered lists
- Write everything in flowing paragraphs
- Use conversational transitions ("Here's the thing...", "Speaking of which...")
- Use "I" and "you" to create connection
- No formulaic structures like "Tip 1:", "Step 2:"

SOURCING:
Include 2-3 hyperlinks to credible sources (Mayo Clinic, CDC, NIH, Harvard Health, etc.)
Format: <a href="URL" target="_blank" rel="noopener">anchor text</a>

STEADIDAY MENTIONS:
1. Mid-article: Mention how SteadiDay's {free_feature} helps (1-2 sentences, natural)
2. Later: Mention premium features include {premium_feature}
3. End with clear CTA to download at steadiday.com

Keep ratio: 85% helpful content, 15% SteadiDay mentions.

OUTPUT FORMAT:
Return ONLY a JSON object with these exact keys:
{{
    "title": "SEO-optimized title with keyword",
    "meta_description": "150-160 char description with keyword",
    "keywords": "comma, separated, keywords",
    "content": "Full HTML content with <h2>, <p>, and <a> tags. NO <html>, <head>, <body>, or <article> tags - just the inner content.",
    "excerpt": "2-3 sentence summary for blog listing page"
}}

For the content field, use only these HTML tags:
- <h2> for section headings
- <p> for paragraphs  
- <a href="..." target="_blank" rel="noopener"> for external links
- <a href="https://www.steadiday.com"> for SteadiDay links (no target="_blank")

Do not include any markdown, code fences, or explanation. Return only the JSON object."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    response_text = message.content[0].text
    
    # Clean up response - remove code fences if present
    response_text = response_text.strip()
    if response_text.startswith("```"):
        response_text = re.sub(r'^```json?\n?', '', response_text)
        response_text = re.sub(r'\n?```$', '', response_text)
    
    import json
    post_data = json.loads(response_text)
    
    # Generate slug and filename
    slug = re.sub(r'[^a-z0-9]+', '-', post_data['title'].lower()).strip('-')
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{date_str}-{slug[:50]}.html"
    
    # Estimate read time (roughly 200 words per minute)
    word_count = len(post_data['content'].split())
    read_time = max(1, round(word_count / 200))
    
    post_data['slug'] = slug
    post_data['filename'] = filename
    post_data['date'] = date_str
    post_data['formatted_date'] = datetime.now().strftime('%B %d, %Y')
    post_data['read_time'] = read_time
    post_data['year'] = datetime.now().year
    
    return post_data


def create_html_file(post_data: dict) -> str:
    """Create the full HTML file for the blog post."""
    
    canonical_url = f"{APP_LINKS['base_url']}/blog/{post_data['filename']}"
    
    html = HTML_TEMPLATE.format(
        title=post_data['title'],
        meta_description=post_data['meta_description'],
        keywords=post_data['keywords'],
        canonical_url=canonical_url,
        website_url=APP_LINKS['website'],
        formatted_date=post_data['formatted_date'],
        read_time=post_data['read_time'],
        content=post_data['content'],
        year=post_data['year']
    )
    
    return html


def update_blog_index(post_data: dict, blog_dir: str):
    """Add the new blog post to the blog index page."""
    
    index_path = os.path.join(blog_dir, 'index.html')
    
    if not os.path.exists(index_path):
        print(f"Warning: Blog index not found at {index_path}")
        return
    
    with open(index_path, 'r', encoding='utf-8') as f:
        index_html = f.read()
    
    # Create new blog entry
    new_entry = f'''<article class="blog-card">
                <h2><a href="{post_data['filename']}">{post_data['title']}</a></h2>
                <div class="blog-meta">{post_data['formatted_date']} • {post_data['read_time']} min read</div>
                <p class="blog-excerpt">{post_data['excerpt']}</p>
                <a href="{post_data['filename']}" class="read-more">Read more →</a>
            </article>
            '''
    
    # Insert after the BLOG_ENTRIES_START marker
    marker = '<!--BLOG_ENTRIES_START-->'
    if marker in index_html:
        index_html = index_html.replace(
            marker,
            marker + '\n            ' + new_entry
        )
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_html)
        
        print(f"✅ Updated blog index with new entry")
    else:
        print("Warning: Could not find BLOG_ENTRIES_START marker in index.html")


def save_blog_post(post_data: dict, html_content: str) -> str:
    """Save the blog post HTML file."""
    
    blog_dir = "blog"
    os.makedirs(blog_dir, exist_ok=True)
    
    filepath = os.path.join(blog_dir, post_data['filename'])
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Update the blog index
    update_blog_index(post_data, blog_dir)
    
    return filepath


def set_github_env(key: str, value: str):
    """Set environment variable for GitHub Actions."""
    env_file = os.environ.get('GITHUB_ENV')
    if env_file:
        with open(env_file, 'a') as f:
            # Handle multiline values
            if '\n' in value:
                value = value.replace('\n', ' ')
            f.write(f"{key}={value}\n")
    else:
        print(f"Would set {key}={value[:50]}...")


def main():
    topic_override = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    
    print("🚀 Starting SteadiDay Blog Generator...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}")
    
    if topic_override:
        print(f"📝 Using custom topic: {topic_override}")
    else:
        print("🎲 Selecting random topic from pool...")
    
    print("✨ Generating blog content with Claude...")
    post_data = generate_blog_post(topic_override)
    
    print(f"📰 Title: {post_data['title']}")
    
    html_content = create_html_file(post_data)
    
    filepath = save_blog_post(post_data, html_content)
    print(f"💾 Saved to: {filepath}")
    
    # Set GitHub Actions environment variables
    set_github_env("BLOG_TITLE", post_data['title'])
    set_github_env("BLOG_SLUG", post_data['slug'][:50])
    set_github_env("BLOG_DATE", post_data['date'])
    
    print("✅ Blog draft generated successfully!")


if __name__ == "__main__":
    main()
