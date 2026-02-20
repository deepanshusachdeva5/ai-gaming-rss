from flask import Flask, jsonify, render_template, request
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import os
from pathlib import Path

import db
from fetcher import fetch_all_feeds, fetch_github_repos, fetch_arxiv_papers, fetch_tavily_sites, preview_feed

# Load .env if it exists (no extra dependency needed)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Background scheduler — RSS every 30 min, GitHub every 2 hours
# ---------------------------------------------------------------------------
def _refresh_all():
    fetch_all_feeds()
    fetch_github_repos()
    fetch_arxiv_papers()
    fetch_tavily_sites()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(_refresh_all, "interval", minutes=30, id="feed_refresh")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/articles")
def api_articles():
    keyword = request.args.get("q", "").strip() or None
    articles = db.get_articles(keyword=keyword)
    return jsonify(articles)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    rss_count = fetch_all_feeds()
    gh_count = fetch_github_repos()
    arxiv_count = fetch_arxiv_papers()
    tavily_count = fetch_tavily_sites()
    stats = db.get_stats()
    return jsonify({"fetched": rss_count + gh_count + arxiv_count + tavily_count, **stats})


@app.route("/api/status")
def api_status():
    return jsonify(db.get_stats())


# ---------------------------------------------------------------------------
# Custom feed management
# ---------------------------------------------------------------------------

@app.route("/api/feeds", methods=["GET"])
def api_get_feeds():
    return jsonify(db.get_custom_feeds())


@app.route("/api/feeds/preview", methods=["GET"])
def api_preview_feed():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "url param required"}), 400
    try:
        info = preview_feed(url)
        return jsonify(info)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/feeds", methods=["POST"])
def api_add_feed():
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    name = data.get("name", "").strip()
    category = data.get("category", "AI Models").strip()

    if not url:
        return jsonify({"error": "url is required"}), 400

    # Auto-detect name from feed metadata if not supplied
    try:
        info = preview_feed(url)
    except Exception as exc:
        return jsonify({"error": f"Could not read feed: {exc}"}), 400

    if not name:
        name = info.get("title") or url

    try:
        feed_id = db.add_custom_feed(name, url, category)
    except Exception as exc:
        return jsonify({"error": f"Feed already exists or DB error: {exc}"}), 409

    # Immediately fetch articles from the new feed
    from fetcher import insert_articles, _clean_html, _parse_date
    import feedparser as _fp
    parsed = _fp.parse(url)
    articles = []
    for entry in parsed.entries:
        title = _clean_html(getattr(entry, "title", ""))
        entry_url = getattr(entry, "link", "")
        if not title or not entry_url:
            continue
        summary_raw = ""
        if hasattr(entry, "content") and entry.content:
            summary_raw = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            summary_raw = entry.summary
        articles.append({
            "title": title, "url": entry_url, "source": name,
            "category": category,
            "summary": _clean_html(summary_raw)[:500],
            "published": _parse_date(entry),
        })
    if articles:
        insert_articles(articles)

    return jsonify({"id": feed_id, "name": name, "url": url,
                    "category": category, "fetched": len(articles)})


@app.route("/api/feeds/<int:feed_id>", methods=["DELETE"])
def api_delete_feed(feed_id):
    db.delete_custom_feed(feed_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Scraped sites management (Tavily)
# ---------------------------------------------------------------------------

@app.route("/api/sites", methods=["GET"])
def api_get_sites():
    return jsonify(db.get_scraped_sites())


@app.route("/api/sites", methods=["POST"])
def api_add_site():
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()
    name = data.get("name", "").strip()
    category = data.get("category", "AI Models").strip()
    query = data.get("query", "").strip()

    if not url:
        return jsonify({"error": "url is required"}), 400

    if not name:
        from urllib.parse import urlparse
        name = urlparse(url).netloc or url

    try:
        site_id = db.add_scraped_site(name, url, category, query)
    except Exception as exc:
        return jsonify({"error": f"Site already exists or DB error: {exc}"}), 409

    # Immediately scrape the newly added site
    site = {"id": site_id, "name": name, "url": url, "category": category, "query": query}
    fetched = fetch_tavily_sites(sites=[site])

    return jsonify({"id": site_id, "name": name, "url": url,
                    "category": category, "fetched": fetched})


@app.route("/api/sites/<int:site_id>", methods=["DELETE"])
def api_delete_site(site_id):
    db.delete_scraped_site(site_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    print("[app] Running initial feed fetch…")
    fetch_all_feeds()
    fetch_github_repos()
    fetch_arxiv_papers()
    fetch_tavily_sites()
    print("[app] Starting Flask on http://localhost:5000")
    app.run(debug=False, port=5000)
