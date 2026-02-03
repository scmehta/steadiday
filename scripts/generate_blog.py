#!/usr/bin/env python3
"""
SteadiDay Blog Generator
Generates SEO-optimized blog posts with stock photos and automatically updates blog/index.html

Features:
- Correct canonical URLs (uses custom domain)
- Titles under 60 characters
- Short, SEO-friendly filenames
- Stock photos in blog posts (hero image + inline images)
- Auto-updates blog/index.html with new entry
"""

import anthropic
import random
import re
import os
import sys
from datetime import datetime

# IMPORTANT: Always use the custom domain, not the GitHub Pages URL
WEBSITE_URL = "https://www.steadiday.com"
BLOG_BASE_URL = f"{WEBSITE_URL}/blog"

# Stock images for blog index cards (thumbnails)
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

# Hero images for the top of blog posts (larger, more impactful)
HERO_IMAGES = {
    "Mental Wellness": [
        "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80",
        "https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=1200&q=80",
        "https://images.unsplash.com/photo-1518241353330-0f7941c2d9b5?w=1200&q=80",
    ],
    "Medication Tips": [
        "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1200&q=80",
        "https://images.unsplash.com/photo-1471864190281-a93a3070b6de?w=1200&q=80",
        "https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=1200&q=80",
    ],
    "Healthy Aging": [
        "https://images.unsplash.com/photo-1447452001602-7090c7ab2db3?w=1200&q=80",
        "https://images.unsplash.com/photo-1516307365426-bea591f05011?w=1200&q=80",
        "https://images.unsplash.com/photo-1454418747937-bd95bb945625?w=1200&q=80",
    ],
    "Exercise": [
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200&q=80",
        "https://images.unsplash.com/photo-1486218119243-13883505764c?w=1200&q=80",
        "https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=1200&q=80",
        "https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=1200&q=80",
    ],
    "Nutrition": [
        "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&q=80",
        "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=1200&q=80",
        "https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=1200&q=80",
        "https://images.unsplash.com/photo-1606923829579-0cb981a83e2e?w=1200&q=80",
    ],
    "Sleep": [
        "https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=1200&q=80",
        "https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=1200&q=80",
        "https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=1200&q=80",
    ],
    "Heart Health": [
        "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=1200&q=80",
        "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=1200&q=80",
        "https://images.unsplash.com/photo-1628348070889-cb656235b4eb?w=1200&q=80",
    ],
    "Brain Health": [
        "https://images.unsplash.com/photo-1559757175-5700dde675bc?w=1200&q=80",
        "https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=1200&q=80",
        "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&q=80",
    ],
    "Safety": [
        "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80",
        "https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=1200&q=80",
    ],
    "Wellness": [
        "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200&q=80",
        "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=1200&q=80",
        "https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=1200&q=80",
    ],
}

# Inline/secondary images to use within blog content
INLINE_IMAGES = {
    "Mental Wellness": [
        {"url": "https://images.unsplash.com/photo-1499209974431-9dddcece7f88?w=800&q=80", "alt": "Person practicing mindfulness in a peaceful setting"},
        {"url": "https://images.unsplash.com/photo-1508672019048-805c876b67e2?w=800&q=80", "alt": "Peaceful nature scene for relaxation"},
        {"url": "https://images.unsplash.com/photo-1528715471579-d1bcf0ba5e83?w=800&q=80", "alt": "Calm meditation space"},
    ],
    "Medication Tips": [
        {"url": "https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=800&q=80", "alt": "Organized pill organizer for daily medications"},
        {"url": "https://images.unsplash.com/photo-1576602976047-174e57a47881?w=800&q=80", "alt": "Healthcare and medication management"},
    ],
    "Healthy Aging": [
        {"url": "https://images.unsplash.com/photo-1516307365426-bea591f05011?w=800&q=80", "alt": "Active senior enjoying life"},
        {"url": "https://images.unsplash.com/photo-1559234938-b60fff04894d?w=800&q=80", "alt": "Healthy lifestyle choices"},
    ],
    "Exercise": [
        {"url": "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80", "alt": "Gentle stretching exercises"},
        {"url": "https://images.unsplash.com/photo-1607962837359-5e7e89f86776?w=800&q=80", "alt": "Senior doing light exercise"},
        {"url": "https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=800&q=80", "alt": "Walking for fitness"},
    ],
    "Nutrition": [
        {"url": "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=800&q=80", "alt": "Healthy meal preparation"},
        {"url": "https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=800&q=80", "alt": "Fresh fruits and vegetables"},
        {"url": "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=800&q=80", "alt": "Nutritious balanced meal"},
    ],
    "Sleep": [
        {"url": "https://images.unsplash.com/photo-1515894203077-9cd36032142f?w=800&q=80", "alt": "Peaceful bedroom for better sleep"},
        {"url": "https://images.unsplash.com/photo-1531353826977-0941b4779a1c?w=800&q=80", "alt": "Relaxing bedtime routine"},
    ],
    "Heart Health": [
        {"url": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80", "alt": "Heart-healthy lifestyle"},
        {"url": "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=800&q=80", "alt": "Cardiovascular health"},
    ],
    "Brain Health": [
        {"url": "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=800&q=80", "alt": "Brain exercises and puzzles"},
        {"url": "https://images.unsplash.com/photo-1456406644174-8ddd4cd52a06?w=800&q=80", "alt": "Staying mentally active"},
    ],
    "Safety": [
        {"url": "https://images.unsplash.com/photo-1581093458791-9d42e3c7e117?w=800&q=80", "alt": "Home safety measures"},
    ],
    "Wellness": [
        {"url": "https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80", "alt": "Overall wellness and self-care"},
        {"url": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80", "alt": "Holistic health approach"},
    ],
}

TOPIC_CATEGORIES = [
    {"topic": "Simple morning stretches for better mobility", "keyword": "morning stretches seniors", "category": "Exercise"},
    {"topic": "How to build a medication routine that sticks", "keyword": "medication routine tips", "category": "Medication Tips"},
    {"topic": "Understanding your blood pressure numbers", "keyword": "blood pressure explained", "category": "Heart Health"},
    {"topic": "5 brain exercises to keep your mind sharp", "keyword": "brain exercises seniors", "category": "Brain Health"},
    {"topic": "The importance of staying hydrated as we age", "keyword": "hydration tips elderly", "category": "Nutrition"},
    {"topic": "How to prevent falls at home", "keyword": "fall prevention seniors", "category": "Safety"},
    {"topic": "Managing stress through breathing exercises", "keyword": "breathing exercises stress", "category": "Mental Wellness"},
    {"topic": "Heart-healthy recipes that are easy to make", "keyword": "heart healthy recipes seniors", "category": "Nutrition"},
    {"topic": "Sleep tips for a more restful night", "keyword": "sleep tips older adults", "category": "Sleep"},
    {"topic": "Walking for health: Getting started safely", "keyword": "walking exercise seniors", "category": "Exercise"},
    {"topic": "Understanding common medication side effects", "keyword": "medication side effects", "category": "Medication Tips"},
    {"topic": "Staying social: Why connection matters", "keyword": "social connection elderly", "category": "Mental Wellness"},
    {"topic": "Managing chronic pain naturally", "keyword": "chronic pain management seniors", "category": "Wellness"},
    {"topic": "Simple memory improvement techniques", "keyword": "memory improvement seniors", "category": "Brain Health"},
    {"topic": "Healthy snacks for sustained energy", "keyword": "healthy snacks seniors", "category": "Nutrition"},
]

STEADIDAY_FEATURES = {
    "free": [
        "Emergency SOS button",
        "Fall Detection",
        "Trusted Contacts management",
        "Basic medication reminders (up to 5)",
    ],
    "premium": [
        "Unlimited medication tracking",
        "Apple Health integration",
        "Food and water logging",
        "Mind Breaks games",
        "Calendar sync",
        "Magnifier tool",
    ]
}


def get_html_template():
    """Returns the HTML template with correct canonical URL and image support."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Primary Meta Tags - TITLE MUST BE UNDER 60 CHARS -->
    <title>{title} - SteadiDay Blog</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="SteadiDay Team">
    <meta name="robots" content="index, follow">
    
    <!-- CRITICAL: Canonical URL must use custom domain -->
    <link rel="canonical" href="{canonical_url}">
    
    <!-- Open Graph - ALL URLs must use custom domain -->
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:image" content="{hero_image}">
    <meta property="og:site_name" content="SteadiDay">
    <meta property="article:published_time" content="{iso_date}">
    <meta property="article:author" content="SteadiDay Team">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{canonical_url}">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{meta_description}">
    <meta name="twitter:image" content="{hero_image}">
    
    <!-- Favicon -->
    <link rel="icon" type="image/jpeg" href="../assets/icon.jpeg">
    <link rel="apple-touch-icon" href="../assets/icon.jpeg">
    
    <!-- Schema.org Article Markup -->
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "{title}",
        "description": "{meta_description}",
        "image": "{hero_image}",
        "author": {{
            "@type": "Organization",
            "name": "SteadiDay Team",
            "url": "{website_url}"
        }},
        "publisher": {{
            "@type": "Organization",
            "name": "SteadiDay",
            "logo": {{
                "@type": "ImageObject",
                "url": "{website_url}/assets/icon.jpeg"
            }}
        }},
        "datePublished": "{iso_date}",
        "dateModified": "{iso_date}",
        "mainEntityOfPage": {{
            "@type": "WebPage",
            "@id": "{canonical_url}"
        }}
    }}
    </script>
    
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
            color: #1A8A7D;
            text-decoration: none;
            font-weight: 500;
        }}
        
        .nav a:hover {{ text-decoration: underline; }}
        
        /* Hero Image */
        .hero-image {{
            width: 100%;
            max-height: 400px;
            object-fit: cover;
        }}
        
        .article-header {{
            background: linear-gradient(135deg, #1E3A5F 0%, #2D4A6F 100%);
            color: white;
            padding: 40px 20px;
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
        }}
        
        .article-content h2 {{
            font-size: 1.5rem;
            margin: 35px 0 15px;
            color: #1E3A5F;
        }}
        
        .article-content p {{
            margin-bottom: 20px;
            font-size: 1.1rem;
            color: #444;
        }}
        
        .article-content a {{ color: #1A8A7D; }}
        .article-content a:hover {{ text-decoration: none; }}
        
        .article-content ul, .article-content ol {{
            margin: 20px 0;
            padding-left: 30px;
        }}
        
        .article-content li {{
            margin-bottom: 10px;
        }}
        
        /* Inline images in article */
        .article-image {{
            margin: 30px 0;
            text-align: center;
        }}
        
        .article-image img {{
            width: 100%;
            max-width: 600px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        
        .article-image figcaption {{
            margin-top: 10px;
            font-size: 0.9rem;
            color: #666;
            font-style: italic;
        }}
        
        .cta-box {{
            background: linear-gradient(135deg, #1A8A7D 0%, #147568 100%);
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
            color: rgba(255,255,255,0.9) !important;
            margin-bottom: 15px;
        }}
        
        .cta-button {{
            display: inline-block;
            background: white;
            color: #1A8A7D;
            padding: 12px 30px;
            border-radius: 8px;
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
            color: #1A8A7D;
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
        
        .footer a {{ color: #1A8A7D; }}
        
        @media (max-width: 768px) {{
            .article-header h1 {{ font-size: 1.75rem; }}
            .article-container {{ padding: 30px 15px; }}
            .hero-image {{ max-height: 250px; }}
        }}
    </style>
</head>
<body>
    <nav class="nav">
        <div class="nav-container">
            <a href="index.html">← Back to Blog</a>
            <a href="{website_url}">SteadiDay Home</a>
        </div>
    </nav>
    
    <!-- Hero Image -->
    <img src="{hero_image}" alt="{title}" class="hero-image">
    
    <header class="article-header">
        <h1>{title}</h1>
        <div class="article-meta">{formatted_date} • By SteadiDay Team • {read_time} min read</div>
    </header>
    
    <article class="article-container">
        <div class="article-content">
            {content}
            
            <div class="cta-box">
                <h3>Ready to Take Control of Your Daily Wellness?</h3>
                <p>SteadiDay helps you manage medications, track your health, and stay connected with loved ones—all designed for adults 50+.</p>
                <a href="{website_url}/#waitlist" class="cta-button">Join the Waitlist</a>
            </div>
        </div>
    </article>
    
    <div class="back-to-blog">
        <a href="index.html">← See all blog posts</a>
    </div>
    
    <footer class="footer">
        <p>&copy; {year} SCM Solutions LLC. All rights reserved. | <a href="{website_url}">Home</a> | <a href="{website_url}/privacy.html">Privacy</a> | <a href="{website_url}/terms.html">Terms</a></p>
    </footer>
</body>
</html>
'''


def get_images_for_category(category: str) -> dict:
    """Get hero and inline images for a category."""
    hero_options = HERO_IMAGES.get(category, HERO_IMAGES['Wellness'])
    inline_options = INLINE_IMAGES.get(category, INLINE_IMAGES['Wellness'])
    
    return {
        "hero": random.choice(hero_options),
        "inline": random.sample(inline_options, min(2, len(inline_options)))
    }


def generate_blog_post(topic_data: dict = None) -> dict:
    """Generate a blog post using Claude API."""
    
    client = anthropic.Anthropic()
    
    if not topic_data:
        topic_data = random.choice(TOPIC_CATEGORIES)
    
    topic = topic_data["topic"]
    target_keyword = topic_data["keyword"]
    category = topic_data.get("category", "Wellness")
    
    # Get images for this category
    images = get_images_for_category(category)
    
    free_feature = random.choice(STEADIDAY_FEATURES["free"])
    premium_feature = random.choice(STEADIDAY_FEATURES["premium"])
    
    # Build image insertion instructions
    inline_img_instructions = ""
    if images["inline"]:
        inline_img_instructions = f"""
IMPORTANT - IMAGE PLACEHOLDERS:
Insert these image placeholders in your content at appropriate points (after relevant sections):

After the 2nd section, insert exactly: [IMAGE_1]
After the 4th section, insert exactly: [IMAGE_2]

These will be replaced with relevant stock photos automatically."""

    prompt = f"""You are a health and wellness content writer for SteadiDay, a mobile app for adults 50+.

Write a blog post about: "{topic}"

TARGET AUDIENCE:
- Adults aged 50 and older
- People interested in maintaining health and independence
- Those who may be managing medications or health conditions
- People who appreciate practical, actionable advice

BLOG REQUIREMENTS:
1. **TITLE: MUST be under 55 characters** (this is critical for SEO - count carefully!)
2. Length: 900-1300 words
3. Tone: Warm, encouraging, respectful (never condescending)
4. Structure: 
   - Compelling introduction paragraph
   - 5-6 main sections with clear subheadings (use <h2> tags)
   - Practical, actionable tips
   - Natural mention of how SteadiDay's {free_feature} or {premium_feature} can help
   - Encouraging conclusion
{inline_img_instructions}

5. Include:
   - At least one relevant statistic with source
   - Real-world examples readers can relate to
   - Simple, clear language

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
TITLE: Your Title Here (MUST be under 55 characters - count them!)
META_DESCRIPTION: 150-160 character description for SEO
KEYWORDS: keyword1, keyword2, keyword3, {target_keyword}
READ_TIME: X

CONTENT:
<p>Opening paragraph that hooks the reader...</p>

<h2>First Section Title</h2>
<p>Paragraph text here...</p>
<p>Another paragraph...</p>

<h2>Second Section Title</h2>
<p>More content...</p>

[IMAGE_1]

<h2>Third Section Title</h2>
<p>Content continues...</p>

<h2>Fourth Section Title</h2>
<p>More helpful information...</p>

[IMAGE_2]

<h2>Fifth Section Title</h2>
<p>Wrapping up...</p>

<h2>Conclusion</h2>
<p>Final thoughts and encouragement...</p>

Remember: Help the reader genuinely, position SteadiDay as a helpful tool—not the focus."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    response_text = message.content[0].text
    
    # Parse the response
    title_match = re.search(r'TITLE:\s*(.+?)(?:\n|$)', response_text)
    meta_match = re.search(r'META_DESCRIPTION:\s*(.+?)(?:\n|$)', response_text)
    keywords_match = re.search(r'KEYWORDS:\s*(.+?)(?:\n|$)', response_text)
    read_time_match = re.search(r'READ_TIME:\s*(\d+)', response_text)
    content_match = re.search(r'CONTENT:\s*(.+)', response_text, re.DOTALL)
    
    title = title_match.group(1).strip() if title_match else topic
    meta_description = meta_match.group(1).strip() if meta_match else f"Learn about {topic} - tips for adults 50+"
    keywords = keywords_match.group(1).strip() if keywords_match else target_keyword
    read_time = read_time_match.group(1) if read_time_match else "6"
    content = content_match.group(1).strip() if content_match else response_text
    
    # Ensure title is under 55 characters
    if len(title) > 55:
        title = title[:52].rsplit(' ', 1)[0] + "..."
    
    # Replace image placeholders with actual images
    if images["inline"]:
        for i, img_data in enumerate(images["inline"]):
            placeholder = f"[IMAGE_{i+1}]"
            img_html = f'''
            <figure class="article-image">
                <img src="{img_data['url']}" alt="{img_data['alt']}" loading="lazy">
                <figcaption>{img_data['alt']}</figcaption>
            </figure>
            '''
            content = content.replace(placeholder, img_html)
    
    # Remove any remaining placeholders that weren't replaced
    content = re.sub(r'\[IMAGE_\d+\]', '', content)
    
    # Create SHORT slug from title (max 5-6 words)
    slug_words = re.sub(r'[^a-z0-9\s]', '', title.lower()).split()[:5]
    slug = '-'.join(slug_words)
    
    return {
        "title": title,
        "meta_description": meta_description,
        "keywords": keywords,
        "read_time": read_time,
        "content": content,
        "slug": slug,
        "category": category,
        "hero_image": images["hero"],
        "date": datetime.now().strftime('%Y-%m-%d')
    }


def create_blog_html(post_data: dict) -> tuple:
    """Create the final HTML file with correct canonical URL and images."""
    
    template = get_html_template()
    
    # Generate the filename and canonical URL
    filename = f"{post_data['date']}-{post_data['slug']}.html"
    canonical_url = f"{BLOG_BASE_URL}/{filename}"
    
    # Format the date nicely
    date_obj = datetime.strptime(post_data['date'], '%Y-%m-%d')
    formatted_date = date_obj.strftime('%B %d, %Y')
    iso_date = date_obj.isoformat()
    
    # Fill in the template
    html = template.format(
        title=post_data['title'],
        meta_description=post_data['meta_description'],
        keywords=post_data['keywords'],
        canonical_url=canonical_url,
        website_url=WEBSITE_URL,
        hero_image=post_data['hero_image'],
        iso_date=iso_date,
        formatted_date=formatted_date,
        read_time=post_data['read_time'],
        content=post_data['content'],
        year=datetime.now().year
    )
    
    return html, filename


def update_blog_index(post_data: dict, filename: str):
    """Update blog/index.html with the new blog entry."""
    
    index_path = "blog/index.html"
    
    if not os.path.exists(index_path):
        print(f"⚠️  Warning: {index_path} not found. Skipping index update.")
        return False
    
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Get image URL for category (thumbnail version)
    category = post_data.get('category', 'Wellness')
    image_url = CATEGORY_IMAGES.get(category, CATEGORY_IMAGES['Wellness'])
    
    # Format the date
    date_obj = datetime.strptime(post_data['date'], '%Y-%m-%d')
    formatted_date = date_obj.strftime('%B %d, %Y')
    
    # Create the new blog card entry
    new_entry = f'''<article class="blog-card">
                <div class="blog-card-image" style="background-image: url('{image_url}');">
                    <span class="blog-card-tag">{category}</span>
                </div>
                <div class="blog-card-content">
                    <h2><a href="{filename}">{post_data['title']}</a></h2>
                    <div class="blog-meta">
                        <span>{formatted_date}</span>
                        <span>•</span>
                        <span>{post_data['read_time']} min read</span>
                    </div>
                    <p class="blog-excerpt">{post_data['meta_description']}</p>
                    <a href="{filename}" class="read-more">
                        Read full article
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                        </svg>
                    </a>
                </div>
            </article>
            
            '''
    
    # Find the marker and insert the new entry
    marker = "<!--BLOG_ENTRIES_START-->"
    if marker in content:
        # Check if there's already a featured post
        if 'class="blog-card featured"' in content:
            # Remove 'featured' from the current featured post
            content = content.replace('class="blog-card featured"', 'class="blog-card"', 1)
        
        # Make the new post the featured one
        new_entry_featured = new_entry.replace('class="blog-card"', 'class="blog-card featured"')
        
        # Insert after the marker
        content = content.replace(marker, marker + "\n            " + new_entry_featured)
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated {index_path} with new entry")
        return True
    else:
        print(f"⚠️  Warning: Marker '{marker}' not found in {index_path}")
        return False


def save_blog_post(html: str, filename: str) -> str:
    """Save the blog post to the blog directory."""
    
    blog_dir = "blog"
    os.makedirs(blog_dir, exist_ok=True)
    
    filepath = os.path.join(blog_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return filepath


def set_github_env(key: str, value: str):
    """Set environment variable for GitHub Actions."""
    env_file = os.environ.get('GITHUB_ENV')
    if env_file:
        with open(env_file, 'a') as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"[ENV] {key}={value}")


def main():
    topic_override = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    
    print("=" * 60)
    print("🚀 SteadiDay Blog Generator")
    print("=" * 60)
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"🌐 Website URL: {WEBSITE_URL}")
    print()
    
    # Find topic
    if topic_override:
        print(f"📝 Using custom topic: {topic_override}")
        topic_data = {"topic": topic_override, "keyword": topic_override.lower(), "category": "Wellness"}
    else:
        print("🎲 Selecting random topic from pool...")
        topic_data = random.choice(TOPIC_CATEGORIES)
        print(f"📝 Selected: {topic_data['topic']}")
        print(f"🏷️  Category: {topic_data['category']}")
    
    # Generate the blog post
    print()
    print("✨ Generating blog content with Claude...")
    post_data = generate_blog_post(topic_data)
    
    print(f"📰 Title: {post_data['title']}")
    print(f"   Length: {len(post_data['title'])} characters {'✅' if len(post_data['title']) <= 55 else '⚠️ TOO LONG'}")
    print(f"🖼️  Hero image: {post_data['hero_image'][:50]}...")
    
    # Create HTML with correct canonical URL
    html, filename = create_blog_html(post_data)
    canonical_url = f"{BLOG_BASE_URL}/{filename}"
    print(f"📄 Filename: {filename}")
    print(f"🔗 Canonical URL: {canonical_url}")
    
    # Save the post
    filepath = save_blog_post(html, filename)
    print(f"💾 Saved to: {filepath}")
    
    # Update blog/index.html
    print()
    print("📑 Updating blog index...")
    update_blog_index(post_data, filename)
    
    # Set GitHub Actions environment variables
    set_github_env("BLOG_TITLE", post_data['title'])
    set_github_env("BLOG_SLUG", post_data['slug'])
    set_github_env("BLOG_DATE", post_data['date'])
    set_github_env("BLOG_FILENAME", filename)
    
    print()
    print("=" * 60)
    print("✅ Blog post generated successfully!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  • Title: {post_data['title']}")
    print(f"  • File: {filename}")
    print(f"  • Category: {post_data['category']}")
    print(f"  • Read time: {post_data['read_time']} min")
    print(f"  • Title length: {len(post_data['title'])} chars (max 55)")
    print(f"  • Hero image: ✅ Included")
    print(f"  • Inline images: ✅ 2 images embedded")
    print(f"  • Canonical URL: {canonical_url}")
    print()


if __name__ == "__main__":
    main()
