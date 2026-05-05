import feedparser
import requests
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ============================================================
# 設定
# ============================================================

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# 監視するRSSフィード一覧
RSS_FEEDS = [
    {"name": "Zenn AI",       "url": "https://zenn.dev/topics/ai/feed"},
    {"name": "Zenn LLM",      "url": "https://zenn.dev/topics/llm/feed"},
    {"name": "Qiita AI",      "url": "https://qiita.com/tags/ai/feed"},
    {"name": "Qiita LLM",     "url": "https://qiita.com/tags/llm/feed"},
    {"name": "ITmedia AI+",   "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"},
    {"name": "TechCrunch JP", "url": "https://jp.techcrunch.com/feed/"},
]

# AIに関連するキーワード（タイトル・概要に含まれる記事のみ取得）
AI_KEYWORDS = [
    "AI", "人工知能", "機械学習", "LLM", "ChatGPT", "Claude", "Gemini",
    "生成AI", "深層学習", "ディープラーニング", "GPT", "OpenAI", "Anthropic",
    "自然言語処理", "NLP", "RAG", "エージェント", "チャットボット",
]

# 何時間以内の記事を取得するか（朝・夕の2回実行に合わせて12時間）
FETCH_HOURS = 12

# 1回の投稿で最大何件まで
MAX_ARTICLES = 10

JST = ZoneInfo("Asia/Tokyo")

# ============================================================
# RSS取得・フィルタリング
# ============================================================

def fetch_articles():
    """RSSフィードから記事を取得してフィルタリング"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FETCH_HOURS)
    articles = []

    for feed_info in RSS_FEEDS:
        print(f"取得中: {feed_info['name']} ({feed_info['url']})")
        try:
            feed = feedparser.parse(feed_info["url"])
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            continue

        for entry in feed.entries:
            # 公開日時を取得
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

            # 公開日時不明 or 古い記事はスキップ
            if not published or published < cutoff:
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            text = (title + " " + summary).upper()

            # キーワードフィルタ
            matched = [kw for kw in AI_KEYWORDS if kw.upper() in text]
            if not matched:
                continue

            articles.append({
                "source": feed_info["name"],
                "title": title,
                "url": entry.get("link", ""),
                "published": published.astimezone(JST),
            })

    # 新しい順にソートして上限件数に絞る
    articles.sort(key=lambda x: x["published"], reverse=True)
    return articles[:MAX_ARTICLES]

# ============================================================
# Slack投稿
# ============================================================

def build_slack_message(articles, period: str):
    """Slackメッセージ（Block Kit形式）を構築"""
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    if not articles:
        return {
            "text": f"📭 {period}のAIニュース ({now_str}) — 新着記事はありませんでした。"
        }

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🤖 {period}のAIニュース  |  {now_str}",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    for i, article in enumerate(articles, 1):
        pub_str = article["published"].strftime("%m/%d %H:%M")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{i}. <{article['url']}|{article['title']}>*\n"
                    f"　📰 {article['source']}　🕐 {pub_str}"
                ),
            },
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"全 {len(articles)} 件 | 過去 {FETCH_HOURS} 時間以内の記事",
            }
        ],
    })

    return {
        "text": f"🤖 {period}のAIニュース ({now_str}) — {len(articles)}件",
        "blocks": blocks,
    }


def post_to_slack(payload: dict):
    """SlackにWebhookで投稿"""
    if not SLACK_WEBHOOK_URL:
        raise ValueError("環境変数 SLACK_WEBHOOK_URL が設定されていません")

    res = requests.post(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    res.raise_for_status()
    print(f"✅ Slack投稿完了: {res.status_code}")

# ============================================================
# メイン
# ============================================================

def main():
    hour = datetime.now(JST).hour
    period = "朝" if hour < 13 else "夕"

    print(f"=== AI RSSフィード → Slack ({period}) ===")
    articles = fetch_articles()
    print(f"対象記事: {len(articles)} 件")

    payload = build_slack_message(articles, period)
    post_to_slack(payload)


if __name__ == "__main__":
    main()
