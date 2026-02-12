#!/usr/bin/env python3
"""Kojima News - Daily crypto news generator.

Fetches RSS feeds, summarizes articles via Claude API,
and generates HTML pages.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser
from jinja2 import Environment, FileSystemLoader

# Timezone
JST = timezone(timedelta(hours=9))

# RSS feeds
FEEDS = [
    {"name": "CoinPost", "url": "https://coinpost.jp/?feed=rss2"},
    {"name": "NADA NEWS", "url": "https://www.nadanews.com/feed/"},
    {"name": "COINTELEGRAPH Japan", "url": "https://jp.cointelegraph.com/rss"},
    {"name": "Bitcoin.com News", "url": "https://news.bitcoin.com/feed/"},
]

# Categories
CATEGORIES = [
    "市場動向",
    "規制・政策",
    "プロジェクト・技術",
    "取引所・サービス",
    "その他",
]

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT_DIR / "templates"
DOCS_DIR = ROOT_DIR / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"


def fetch_articles():
    """Fetch articles from RSS feeds published within the last 24 hours."""
    now = datetime.now(JST)
    cutoff = now - timedelta(hours=24)
    articles = []

    for feed_info in FEEDS:
        print(f"Fetching: {feed_info['name']} ...")
        try:
            feed = feedparser.parse(feed_info["url"])
        except Exception as e:
            print(f"  Error fetching {feed_info['name']}: {e}")
            continue

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            if published is None:
                continue

            published_jst = published.astimezone(JST)
            if published_jst < cutoff:
                continue

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            description = entry.get("summary", entry.get("description", "")).strip()
            # Strip HTML tags from description
            description = re.sub(r"<[^>]+>", "", description).strip()
            # Truncate long descriptions
            if len(description) > 300:
                description = description[:300] + "..."

            articles.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": feed_info["name"],
                    "published": published_jst.isoformat(),
                }
            )

    print(f"Total articles fetched: {len(articles)}")
    return articles


def summarize_with_claude(articles):
    """Send articles to Claude API for summarization and categorization."""
    if not articles:
        return {"summary": "", "categories": {cat: [] for cat in CATEGORIES}}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    # Build article list for prompt
    article_list = []
    for i, a in enumerate(articles, 1):
        article_list.append(
            f"{i}. [{a['source']}] {a['title']}\n   URL: {a['link']}\n   概要: {a['description']}"
        )
    articles_text = "\n\n".join(article_list)

    prompt = f"""以下は過去24時間の暗号資産関連ニュース記事の一覧です。

{articles_text}

---

上記の記事について、以下のJSON形式で出力してください。JSON以外のテキストは出力しないでください。

{{
  "summary": "市場全体のサマリー（3〜5文の日本語テキスト）",
  "categories": {{
    "市場動向": [
      {{"index": 記事番号, "digest": "1行要約（日本語）"}}
    ],
    "規制・政策": [...],
    "プロジェクト・技術": [...],
    "取引所・サービス": [...],
    "その他": [...]
  }}
}}

ルール:
- すべての記事をいずれかのカテゴリに分類してください
- digestは各記事の要点を1行で簡潔に日本語で書いてください
- indexは記事一覧の番号に対応させてください
- summaryは市場全体の動向を俯瞰的にまとめてください
- JSON以外の出力は禁止です
"""

    client = anthropic.Anthropic(api_key=api_key)
    print("Calling Claude API for summarization...")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
    if json_match:
        response_text = json_match.group(1).strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Error parsing Claude response as JSON: {e}")
        print(f"Response: {response_text[:500]}")
        return {"summary": "", "categories": {cat: [] for cat in CATEGORIES}}

    # Map index back to article data
    categorized = {}
    for cat_name in CATEGORIES:
        cat_articles = result.get("categories", {}).get(cat_name, [])
        mapped = []
        for item in cat_articles:
            idx = item.get("index", 0) - 1
            if 0 <= idx < len(articles):
                mapped.append(
                    {
                        "title": articles[idx]["title"],
                        "link": articles[idx]["link"],
                        "source": articles[idx]["source"],
                        "digest": item.get("digest", ""),
                    }
                )
        categorized[cat_name] = mapped

    return {"summary": result.get("summary", ""), "categories": categorized}


def get_archive_links():
    """Scan archive directory and return sorted list of archive links."""
    links = []
    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.html"), reverse=True):
            date_str = f.stem  # YYYY-MM-DD
            links.append({"date": date_str, "path": f"archive/{f.name}"})
    return links


def generate_html(date_str, summary, categories, archive_links):
    """Render HTML from Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("daily.html")

    return template.render(
        date=date_str,
        summary=summary,
        categories=categories,
        archive_links=archive_links,
    )


def main():
    today = datetime.now(JST)
    date_str = today.strftime("%Y-%m-%d")
    print(f"Generating news for: {date_str}")

    # Ensure output directories exist
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch articles
    articles = fetch_articles()

    # 2. Summarize with Claude
    result = summarize_with_claude(articles)

    # 3. Generate HTML
    archive_links = get_archive_links()
    html = generate_html(date_str, result["summary"], result["categories"], archive_links)

    # 4. Write archive file
    archive_file = ARCHIVE_DIR / f"{date_str}.html"
    archive_file.write_text(html, encoding="utf-8")
    print(f"Archive saved: {archive_file}")

    # 5. Update archive links (now includes today) and regenerate index
    archive_links = get_archive_links()
    index_html = generate_html(date_str, result["summary"], result["categories"], archive_links)
    index_file = DOCS_DIR / "index.html"
    index_file.write_text(index_html, encoding="utf-8")
    print(f"Index saved: {index_file}")

    print("Done.")


if __name__ == "__main__":
    main()
