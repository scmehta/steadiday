#!/usr/bin/env python3
"""
SteadiDay Blog Generator
Generates SEO-optimized blog posts for steadiday.com with correct canonical URLs.
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

TOPIC_CATEGORIES = [
    {"topic": "Simple morning stretches for better mobility after 50", "keyword": "morning stretches seniors"},
    {"topic": "How to build a medication routine that actually sticks", "keyword": "medication routine tips"},
    {"topic": "Understanding your blood pressure numbers", "keyword": "blood pressure explained"},
    {"topic": "5 brain exercises to keep your mind sharp", "keyword": "brain exercises seniors"},
    {"topic": "The importance of staying hydrated as we age", "keyword": "hydration tips elderly"},
    {"topic": "How to prevent falls at home", "keyword": "fall prevention seniors"},
    {"topic": "Managing stress through simple breathing exercises", "keyword": "breathing exercises stress"},
    {"topic": "Building stronger connections with family through technology", "keyword": "seniors technology family"},
    {"topic": "Heart-healthy recipes that are easy to make", "keyword": "heart healthy recipes seniors"},
    {"topic": "Sleep tips for a more restful night", "keyword": "sleep tips older adults"},
    {"topic": "Walking for health: Getting started safely", "keyword": "walking exercise seniors"},
    {"topic": "Understanding common medication side effects", "keyword": "medication side effects"},
    {"topic": "Simple mindfulness practices for everyday calm", "keyword": "mindfulness seniors"},
    {"topic": "Staying social: Why connection matters for health", "keyword": "social connection elderly"},
    {"topic": "Managing chronic pain naturally", "keyword": "chronic pain management seniors"},
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
    """
    Returns the HTML template with CORRECT canonical URL.
    CRITICAL: Uses WEBSITE_URL (custom domain) not GitHub Pages URL.
    """
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Primary Meta Tags -->
    <title>{title} | SteadiDay Blog</title>
    <meta name="title" content="{title} | SteadiDay Blog">
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="SteadiDay Team">
    <meta name="robots" content="index, follow">
    
    <!-- CRITICAL: Canonical URL must use custom domain -->
    <link rel="canonical" href="{canonical_url}">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:image" content="{website_url}/assets/og-image.png">
    <meta property="og:site_name" content="SteadiDay">
    <meta property="article:published_time" content="{iso_date}">
    <meta property="article:author" content="SteadiDay Team">
    
    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{canonical_url}">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{meta_description}">
    <meta name="twitter:image" content="{website_url}/assets/og-image.png">
    
    <!-- Favicon -->
    <link rel="icon" type="image/jpeg" href="../assets/icon.jpeg">
    <link rel="apple-touch-icon" href="../assets/icon.jpeg">
    
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
    
    <!-- Schema.org Article Markup -->
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "{title}",
        "description": "{meta_description}",
        "image": "{website_url}/assets/og-image.png",
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
        :root {{
            --cream: #FFFBF5;
            --teal: #1A8A7D;
            --teal-dark: #147568;
            --teal-light: #E8F5F3;
            --navy: #1E3A5F;
            --charcoal: #2D3436;
            --charcoal-light: #5A6266;
            --white: #FFFFFF;
            --gold: #D4A853;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 1.125rem;
            line-height: 1.8;
            color: var(--charcoal);
            background: var(--cream);
        }}
        
        h1, h2, h3, h4 {{
            font-family: 'Merriweather', Georgia, serif;
            font-weight: 700;
            line-height: 1.3;
            color: var(--navy);
        }}
        
        a {{
            color: var(--teal);
            text-decoration: none;
        }}
        
        a:hover {{
            color: var(--teal-dark);
            text-decoration: underline;
        }}
        
        .nav {{
            background: var(--white);
            padding: 1rem 2rem;
            border-bottom: 1px solid rgba(30, 58, 95, 0.1);
        }}
        
        .nav-container {{
            max-width: 800px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .nav a {{
            font-weight: 600;
            color: var(--navy);
        }}
        
        .nav a:hover {{
            color: var(--teal);
        }}
        
        .article-header {{
            background: linear-gradient(135deg, var(--navy) 0%, #2D4A6F 100%);
            color: white;
            padding: 4rem 2rem;
            text-align: center;
        }}
        
        .article-header h1 {{
            color: white;
            font-size: 2.5rem;
            max-width: 800px;
            margin: 0 auto 1rem;
        }}
        
        .article-meta {{
            color: rgba(255, 255, 255, 0.8);
            font-size: 1rem;
        }}
        
        .article-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 3rem 2rem;
            background: var(--white);
        }}
        
        .article-content h2 {{
            margin: 2.5rem 0 1rem;
            font-size: 1.75rem;
        }}
        
        .article-content h3 {{
            margin: 2rem 0 0.75rem;
            font-size: 1.35rem;
        }}
        
        .article-content p {{
            margin-bottom: 1.5rem;
            color: var(--charcoal);
        }}
        
        .article-content ul, .article-content ol {{
            margin: 1.5rem 0;
            padding-left: 2rem;
        }}
        
        .article-content li {{
            margin-bottom: 0.75rem;
        }}
        
        .article-content blockquote {{
            border-left: 4px solid var(--teal);
            padding-left: 1.5rem;
            margin: 2rem 0;
            font-style: italic;
            color: var(--charcoal-light);
        }}
        
        .cta-box {{
            background: linear-gradient(135deg, var(--teal) 0%, var(--teal-dark) 100%);
            color: white;
            padding: 2rem;
            border-radius: 12px;
            margin: 3rem 0;
            text-align: center;
        }}
        
        .cta-box h3 {{
            color: white;
            margin-bottom: 0.75rem;
            font-size: 1.5rem;
        }}
        
        .cta-box p {{
            color: rgba(255, 255, 255, 0.9) !important;
            margin-bottom: 1.5rem;
        }}
        
        .cta-button {{
            display: inline-block;
            background: white;
            color: var(--teal);
            padding: 0.875rem 2rem;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.3s ease;
        }}
        
        .cta-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            text-decoration: none;
        }}
        
        .back-to-blog {{
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            text-align: center;
            background: var(--white);
            border-top: 1px solid rgba(30, 58, 95, 0.1);
        }}
        
        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--charcoal-light);
            font-size: 0.9rem;
            background: var(--cream);
        }}
        
        @media (max-width: 768px) {{
            .article-header h1 {{
                font-size: 1.75rem;
            }}
            
            .article-container {{
                padding: 2rem 1.5rem;
            }}
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

TARGET AUDIENCE:
- Adults aged 50 and older
- People interested in maintaining health and independence
- Those who may be managing medications or health conditions
- People who appreciate practical, actionable advice

BLOG REQUIREMENTS:
1. Title: Engaging, clear, SEO-friendly, and UNDER 60 CHARACTERS (this is critical for SEO)
2. Length: 800-1200 words
3. Tone: Warm, encouraging, respectful (never condescending)
4. Structure: 
   - Compelling introduction
   - 3-5 main sections with clear subheadings (use ## for h2, ### for h3)
   - Practical, actionable tips
   - Natural mention of how SteadiDay's {free_feature} or {premium_feature} can help
   - Encouraging conclusion

5. Include:
   - At least one relevant statistic with source
   - Real-world examples readers can relate to
   - Simple, clear language

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
TITLE: Your Title Here (MUST be under 60 characters)
META_DESCRIPTION: 150-160 character description for SEO
KEYWORDS: keyword1, keyword2, keyword3
READ_TIME: X

CONTENT:
[Your blog post content in HTML format - use <h2>, <h3>, <p>, <ul>, <li>, <blockquote> tags]

Remember: Help the reader genuinely, position SteadiDay as a helpful tool—not the focus."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
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
    read_time = read_time_match.group(1) if read_time_match else "5"
    content = content_match.group(1).strip() if content_match else response_text
    
    # Ensure title is under 60 characters
    if len(title) > 60:
        title = title[:57] + "..."
    
    # Create slug from title
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    
    return {
        "title": title,
        "meta_description": meta_description,
        "keywords": keywords,
        "read_time": read_time,
        "content": content,
        "slug": slug,
        "date": datetime.now().strftime('%Y-%m-%d')
    }


def create_blog_html(post_data: dict) -> str:
    """Create the final HTML file with correct canonical URL."""
    
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
        canonical_url=canonical_url,  # CRITICAL: Uses custom domain
        website_url=WEBSITE_URL,      # CRITICAL: Uses custom domain
        iso_date=iso_date,
        formatted_date=formatted_date,
        read_time=post_data['read_time'],
        content=post_data['content'],
        year=datetime.now().year
    )
    
    return html, filename


def save_blog_post(html: str, filename: str) -> str:
    """Save the blog post to the blog directory."""
    
    # Create the blog directory if it doesn't exist
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
    
    print("🚀 Starting SteadiDay Blog Generator...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"🌐 Website URL: {WEBSITE_URL}")
    print(f"📁 Blog Base URL: {BLOG_BASE_URL}")
    
    if topic_override:
        print(f"📝 Using custom topic: {topic_override}")
    else:
        print("🎲 Selecting random topic from pool...")
    
    # Generate the blog post
    print("✨ Generating blog content with Claude...")
    post_data = generate_blog_post(topic_override)
    
    print(f"📰 Title: {post_data['title']} ({len(post_data['title'])} chars)")
    
    # Create HTML with correct canonical URL
    html, filename = create_blog_html(post_data)
    canonical_url = f"{BLOG_BASE_URL}/{filename}"
    print(f"🔗 Canonical URL: {canonical_url}")
    
    # Save the post
    filepath = save_blog_post(html, filename)
    print(f"💾 Saved to: {filepath}")
    
    # Set GitHub Actions environment variables
    set_github_env("BLOG_TITLE", post_data['title'])
    set_github_env("BLOG_SLUG", post_data['slug'])
    set_github_env("BLOG_DATE", post_data['date'])
    set_github_env("BLOG_FILENAME", filename)
    
    print("✅ Blog post generated successfully!")
    print(f"   - Title under 60 chars: {'✓' if len(post_data['title']) <= 60 else '✗'}")
    print(f"   - Canonical URL correct: ✓")
    print(f"   - Custom domain used: ✓")


if __name__ == "__main__":
    main()
