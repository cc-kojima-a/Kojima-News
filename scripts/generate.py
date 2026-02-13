#!/usr/bin/env python3
"""Kojima News v2 - Daily news generator.

Fetches weather, stock indices, crypto prices, and RSS feeds,
summarizes via OpenAI Responses API (GPT-5.2),
and generates HTML pages.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import openai
import requests
import yfinance as yf
from jinja2 import Environment, FileSystemLoader

# Timezone
JST = timezone(timedelta(hours=9))

# RSS feeds - Domestic crypto
CRYPTO_FEEDS_DOMESTIC = [
    {"name": "CoinPost", "url": "https://coinpost.jp/?feed=rss2"},
    {"name": "NADA NEWS", "url": "https://www.nadanews.com/feed/"},
    {"name": "COINTELEGRAPH Japan", "url": "https://jp.cointelegraph.com/rss"},
]

# RSS feeds - International crypto
CRYPTO_FEEDS_INTERNATIONAL = [
    {"name": "Bitcoin.com News", "url": "https://news.bitcoin.com/feed/"},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed"},
]

# RSS feeds - Stock news
STOCK_NEWS_FEEDS = [
    {"name": "Reuters Business", "url": "https://www.reuters.com/arc/outboundfeeds/v3/all/business/?outputType=xml"},
    {"name": "CNBC Top News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"},
]

# Categories
CATEGORIES = [
    "市場動向",
    "規制・政策",
    "プロジェクト・技術",
    "取引所・サービス",
    "その他",
]

# Stock indices
STOCK_INDICES = [
    {"symbol": "^N225", "name": "日経平均"},
    {"symbol": "^TPX", "name": "TOPIX"},
    {"symbol": "^GSPC", "name": "S&P 500"},
    {"symbol": "^IXIC", "name": "NASDAQ"},
    {"symbol": "^DJI", "name": "ダウ平均"},
]

# Crypto currencies for price tracking
CRYPTO_IDS = "bitcoin,ethereum,ripple,solana,binancecoin,cardano,dogecoin"
CRYPTO_DISPLAY_NAMES = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "ripple": "XRP",
    "solana": "SOL",
    "binancecoin": "BNB",
    "cardano": "ADA",
    "dogecoin": "DOGE",
}

# Weather code to Japanese text mapping
WEATHER_CODE_MAP = {
    0: "快晴",
    1: "晴れ",
    2: "一部曇り",
    3: "曇り",
    45: "霧",
    48: "着氷性の霧",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    56: "弱い着氷性の霧雨",
    57: "強い着氷性の霧雨",
    61: "弱い雨",
    63: "雨",
    65: "強い雨",
    66: "弱い着氷性の雨",
    67: "強い着氷性の雨",
    71: "弱い雪",
    73: "雪",
    75: "強い雪",
    77: "霧雪",
    80: "弱いにわか雨",
    81: "にわか雨",
    82: "激しいにわか雨",
    85: "弱いにわか雪",
    86: "強いにわか雪",
    95: "雷雨",
    96: "雹を伴う雷雨",
    99: "強い雹を伴う雷雨",
}

# Weather locations
WEATHER_LOCATIONS = [
    {"name": "品川区大井町", "lat": 35.6067, "lon": 139.7345},
    {"name": "渋谷区渋谷駅", "lat": 35.6580, "lon": 139.7016},
]

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT_DIR / "templates"
DOCS_DIR = ROOT_DIR / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"


def weather_code_to_text(code):
    """Convert WMO weather code to Japanese text."""
    return WEATHER_CODE_MAP.get(code, f"不明({code})")


def fetch_weather():
    """Fetch weather data from Open-Meteo API for configured locations."""
    print("Fetching weather data...")
    latitudes = ",".join(str(loc["lat"]) for loc in WEATHER_LOCATIONS)
    longitudes = ",".join(str(loc["lon"]) for loc in WEATHER_LOCATIONS)

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitudes}"
        f"&longitude={longitudes}"
        "&current=temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        "&timezone=Asia/Tokyo"
        "&forecast_days=1"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Error fetching weather: {e}")
        return []

    weather_list = []
    # Open-Meteo returns a list when multiple locations are requested
    locations_data = data if isinstance(data, list) else [data]

    for i, loc_data in enumerate(locations_data):
        if i >= len(WEATHER_LOCATIONS):
            break
        loc = WEATHER_LOCATIONS[i]
        current = loc_data.get("current", {})
        daily = loc_data.get("daily", {})

        weather_list.append({
            "name": loc["name"],
            "temperature": current.get("temperature_2m"),
            "weather": weather_code_to_text(current.get("weather_code", -1)),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "temp_max": daily.get("temperature_2m_max", [None])[0],
            "temp_min": daily.get("temperature_2m_min", [None])[0],
            "precip_prob": daily.get("precipitation_probability_max", [None])[0],
            "daily_weather": weather_code_to_text(daily.get("weather_code", [-1])[0]),
        })

    print(f"  Weather data fetched for {len(weather_list)} locations")
    return weather_list


def fetch_stock_indices():
    """Fetch stock index data via yfinance."""
    print("Fetching stock indices...")
    indices = []

    for idx_info in STOCK_INDICES:
        try:
            ticker = yf.Ticker(idx_info["symbol"])
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                close = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
                change_pct = ((close - prev_close) / prev_close) * 100
                indices.append({
                    "name": idx_info["name"],
                    "symbol": idx_info["symbol"],
                    "close": round(close, 2),
                    "change_pct": round(change_pct, 2),
                })
            elif len(hist) == 1:
                close = hist["Close"].iloc[-1]
                indices.append({
                    "name": idx_info["name"],
                    "symbol": idx_info["symbol"],
                    "close": round(close, 2),
                    "change_pct": 0.0,
                })
            else:
                print(f"  No data for {idx_info['name']}")
        except Exception as e:
            print(f"  Error fetching {idx_info['name']}: {e}")

    print(f"  Stock indices fetched: {len(indices)}")
    return indices


def fetch_stock_news():
    """Fetch stock market news from RSS feeds."""
    print("Fetching stock news...")
    now = datetime.now(JST)
    cutoff = now - timedelta(hours=24)
    articles = []

    for feed_info in STOCK_NEWS_FEEDS:
        print(f"  Fetching: {feed_info['name']} ...")
        try:
            feed = feedparser.parse(feed_info["url"])
        except Exception as e:
            print(f"    Error fetching {feed_info['name']}: {e}")
            continue

        for entry in feed.entries[:10]:  # Limit to 10 per feed
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            if published and published.astimezone(JST) < cutoff:
                continue

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            description = entry.get("summary", entry.get("description", "")).strip()
            description = re.sub(r"<[^>]+>", "", description).strip()
            if len(description) > 300:
                description = description[:300] + "..."

            articles.append({
                "title": title,
                "link": link,
                "description": description,
                "source": feed_info["name"],
            })

    print(f"  Stock news articles fetched: {len(articles)}")
    return articles


def fetch_crypto_prices():
    """Fetch crypto prices from CoinGecko API."""
    print("Fetching crypto prices...")
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={CRYPTO_IDS}"
        "&vs_currencies=usd,jpy"
        "&include_24hr_change=true"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Error fetching crypto prices: {e}")
        return []

    prices = []
    for crypto_id, display_name in CRYPTO_DISPLAY_NAMES.items():
        if crypto_id in data:
            info = data[crypto_id]
            prices.append({
                "id": crypto_id,
                "symbol": display_name,
                "usd": info.get("usd"),
                "jpy": info.get("jpy"),
                "change_24h": round(info.get("usd_24h_change", 0), 2),
            })

    print(f"  Crypto prices fetched: {len(prices)}")
    return prices


def fetch_articles(feeds):
    """Fetch articles from RSS feeds published within the last 24 hours."""
    now = datetime.now(JST)
    cutoff = now - timedelta(hours=24)
    articles = []

    for feed_info in feeds:
        print(f"  Fetching: {feed_info['name']} ...")
        try:
            feed = feedparser.parse(feed_info["url"])
        except Exception as e:
            print(f"    Error fetching {feed_info['name']}: {e}")
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
            description = re.sub(r"<[^>]+>", "", description).strip()
            if len(description) > 300:
                description = description[:300] + "..."

            articles.append({
                "title": title,
                "link": link,
                "description": description,
                "source": feed_info["name"],
                "published": published_jst.isoformat(),
            })

    return articles


def summarize_with_openai(domestic_articles, international_articles, stock_news, crypto_prices):
    """Send all data to OpenAI Responses API (GPT-5.2) for summarization."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set.")
        sys.exit(1)

    has_domestic = len(domestic_articles) > 0
    has_international = len(international_articles) > 0
    has_stock_news = len(stock_news) > 0

    if not has_domestic and not has_international and not has_stock_news:
        return {
            "market_summary": "",
            "stock_news_summary": [],
            "domestic_categories": {cat: [] for cat in CATEGORIES},
            "international_categories": {cat: [] for cat in CATEGORIES},
            "price_analysis": "",
        }

    # Build domestic article list
    domestic_text = ""
    if has_domestic:
        domestic_list = []
        for i, a in enumerate(domestic_articles, 1):
            domestic_list.append(
                f"D{i}. [{a['source']}] {a['title']}\n   URL: {a['link']}\n   概要: {a['description']}"
            )
        domestic_text = "【国内暗号資産ニュース】\n\n" + "\n\n".join(domestic_list)

    # Build international article list
    international_text = ""
    if has_international:
        intl_list = []
        for i, a in enumerate(international_articles, 1):
            intl_list.append(
                f"I{i}. [{a['source']}] {a['title']}\n   URL: {a['link']}\n   概要: {a['description']}"
            )
        international_text = "【海外暗号資産ニュース】\n\n" + "\n\n".join(intl_list)

    # Build stock news list
    stock_news_text = ""
    if has_stock_news:
        stock_list = []
        for i, a in enumerate(stock_news, 1):
            stock_list.append(
                f"S{i}. [{a['source']}] {a['title']}\n   概要: {a['description']}"
            )
        stock_news_text = "【株式市場ニュース】\n\n" + "\n\n".join(stock_list)

    # Build crypto price info
    price_text = ""
    if crypto_prices:
        price_lines = []
        for p in crypto_prices:
            price_lines.append(
                f"- {p['symbol']}: ${p['usd']:,.2f} (¥{p['jpy']:,.0f}) 24h変動: {p['change_24h']:+.2f}%"
            )
        price_text = "【暗号資産価格（現在）】\n\n" + "\n".join(price_lines)

    all_text = "\n\n---\n\n".join(
        section for section in [domestic_text, international_text, stock_news_text, price_text] if section
    )

    prompt = f"""以下は本日のマーケットデータとニュース一覧です。

{all_text}

---

上記のデータについて、以下のJSON形式で出力してください。JSON以外のテキストは出力しないでください。

{{
  "market_summary": "マーケット全体（株式・暗号資産）の動向を俯瞰するサマリー（3〜5文の日本語テキスト）",
  "stock_news_summary": [
    {{"title": "要約タイトル", "digest": "1行要約（日本語）", "source": "ソース名"}}
  ],
  "domestic_categories": {{
    "市場動向": [
      {{"index": "D1", "digest": "1行要約（日本語）"}}
    ],
    "規制・政策": [...],
    "プロジェクト・技術": [...],
    "取引所・サービス": [...],
    "その他": [...]
  }},
  "international_categories": {{
    "市場動向": [
      {{"index": "I1", "digest": "1行要約（日本語）"}}
    ],
    "規制・政策": [...],
    "プロジェクト・技術": [...],
    "取引所・サービス": [...],
    "その他": [...]
  }},
  "price_analysis": "暗号資産の価格変動とニュースの関連性分析（2〜4文の日本語テキスト。どのニュースがどの通貨の価格に影響しているかを分析）"
}}

ルール:
- すべての国内暗号資産ニュースをdomestic_categoriesのいずれかのカテゴリに分類してください
- すべての海外暗号資産ニュースをinternational_categoriesのいずれかのカテゴリに分類してください
- indexはニュース一覧のID（D1, D2, I1, I2...）に対応させてください
- digestは各記事の要点を1行で簡潔に日本語で書いてください
- market_summaryは株式市場と暗号資産市場の両方を俯瞰してまとめてください
- stock_news_summaryは主要な株式ニュースを最大5件まで要約してください
- price_analysisでは、ニュースと価格変動の因果関係を分析してください
- JSON以外の出力は禁止です
"""

    client = openai.OpenAI(api_key=api_key)
    print("Calling OpenAI API (GPT-5.2 Responses API) for summarization...")

    try:
        response = client.responses.create(
            model="gpt-5.2",
            reasoning={"effort": "medium", "summary": "concise"},
            instructions="あなたは金融市場と暗号資産ニュースの要約アシスタントです。指示されたJSON形式で出力してください。",
            input=prompt,
        )
        response_text = response.output_text.strip()
    except Exception as e:
        print(f"Error calling OpenAI Responses API: {e}")
        return {
            "market_summary": "",
            "stock_news_summary": [],
            "domestic_categories": {cat: [] for cat in CATEGORIES},
            "international_categories": {cat: [] for cat in CATEGORIES},
            "price_analysis": "",
        }

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
    if json_match:
        response_text = json_match.group(1).strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"Error parsing OpenAI response as JSON: {e}")
        print(f"Response: {response_text[:500]}")
        return {
            "market_summary": "",
            "stock_news_summary": [],
            "domestic_categories": {cat: [] for cat in CATEGORIES},
            "international_categories": {cat: [] for cat in CATEGORIES},
            "price_analysis": "",
        }

    # Map domestic articles
    domestic_categorized = {}
    for cat_name in CATEGORIES:
        cat_articles = result.get("domestic_categories", {}).get(cat_name, [])
        mapped = []
        for item in cat_articles:
            idx_str = item.get("index", "")
            # Parse D1, D2, etc.
            match = re.match(r"D(\d+)", str(idx_str))
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(domestic_articles):
                    mapped.append({
                        "title": domestic_articles[idx]["title"],
                        "link": domestic_articles[idx]["link"],
                        "source": domestic_articles[idx]["source"],
                        "digest": item.get("digest", ""),
                    })
        domestic_categorized[cat_name] = mapped

    # Map international articles
    international_categorized = {}
    for cat_name in CATEGORIES:
        cat_articles = result.get("international_categories", {}).get(cat_name, [])
        mapped = []
        for item in cat_articles:
            idx_str = item.get("index", "")
            match = re.match(r"I(\d+)", str(idx_str))
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(international_articles):
                    mapped.append({
                        "title": international_articles[idx]["title"],
                        "link": international_articles[idx]["link"],
                        "source": international_articles[idx]["source"],
                        "digest": item.get("digest", ""),
                    })
        international_categorized[cat_name] = mapped

    return {
        "market_summary": result.get("market_summary", ""),
        "stock_news_summary": result.get("stock_news_summary", []),
        "domestic_categories": domestic_categorized,
        "international_categories": international_categorized,
        "price_analysis": result.get("price_analysis", ""),
    }


def get_archive_links():
    """Scan archive directory and return sorted list of archive links."""
    links = []
    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.html"), reverse=True):
            date_str = f.stem  # YYYY-MM-DD
            links.append({"date": date_str, "path": f"archive/{f.name}"})
    return links


def generate_html(date_str, weather, stock_indices, crypto_prices,
                  market_summary, stock_news_summary, domestic_categories,
                  international_categories, price_analysis, archive_links):
    """Render HTML from Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("daily.html")

    return template.render(
        date=date_str,
        weather=weather,
        stock_indices=stock_indices,
        crypto_prices=crypto_prices,
        market_summary=market_summary,
        stock_news_summary=stock_news_summary,
        domestic_categories=domestic_categories,
        international_categories=international_categories,
        price_analysis=price_analysis,
        archive_links=archive_links,
    )


def main():
    today = datetime.now(JST)
    date_str = today.strftime("%Y-%m-%d")
    print(f"Generating news for: {date_str}")

    # Ensure output directories exist
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch weather
    weather = fetch_weather()

    # 2. Fetch stock indices
    stock_indices = fetch_stock_indices()

    # 3. Fetch stock news
    stock_news = fetch_stock_news()

    # 4. Fetch crypto prices
    crypto_prices = fetch_crypto_prices()

    # 5. Fetch crypto articles (domestic / international)
    print("Fetching domestic crypto news...")
    domestic_articles = fetch_articles(CRYPTO_FEEDS_DOMESTIC)
    print(f"  Domestic articles: {len(domestic_articles)}")

    print("Fetching international crypto news...")
    international_articles = fetch_articles(CRYPTO_FEEDS_INTERNATIONAL)
    print(f"  International articles: {len(international_articles)}")

    # 6. Summarize with OpenAI (GPT-5.2 Responses API)
    result = summarize_with_openai(
        domestic_articles, international_articles, stock_news, crypto_prices
    )

    # 7. Generate HTML
    archive_links = get_archive_links()
    html = generate_html(
        date_str=date_str,
        weather=weather,
        stock_indices=stock_indices,
        crypto_prices=crypto_prices,
        market_summary=result["market_summary"],
        stock_news_summary=result["stock_news_summary"],
        domestic_categories=result["domestic_categories"],
        international_categories=result["international_categories"],
        price_analysis=result["price_analysis"],
        archive_links=archive_links,
    )

    # 8. Write archive file
    archive_file = ARCHIVE_DIR / f"{date_str}.html"
    archive_file.write_text(html, encoding="utf-8")
    print(f"Archive saved: {archive_file}")

    # 9. Update archive links (now includes today) and regenerate index
    archive_links = get_archive_links()
    index_html = generate_html(
        date_str=date_str,
        weather=weather,
        stock_indices=stock_indices,
        crypto_prices=crypto_prices,
        market_summary=result["market_summary"],
        stock_news_summary=result["stock_news_summary"],
        domestic_categories=result["domestic_categories"],
        international_categories=result["international_categories"],
        price_analysis=result["price_analysis"],
        archive_links=archive_links,
    )
    index_file = DOCS_DIR / "index.html"
    index_file.write_text(index_html, encoding="utf-8")
    print(f"Index saved: {index_file}")

    print("Done.")


if __name__ == "__main__":
    main()
