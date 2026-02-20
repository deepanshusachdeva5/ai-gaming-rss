import feedparser
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from time import mktime

from db import insert_articles, get_custom_feeds, get_scraped_sites
from feeds import FEEDS

# GitHub Search API queries — AI models and tools usable in / for games.
# Each entry is (query, label) — label is stored as the `source` in the DB
# so cards show something meaningful instead of just "GitHub".
GITHUB_QUERIES = [
    # --- Generative media ---
    ("topic:text-to-3d",                        "GitHub · Text-to-3D"),
    ("text to mesh 3D generation diffusion",    "GitHub · Text-to-3D"),
    ("topic:text-to-image",                     "GitHub · Text-to-Image"),
    ("video generation world model diffusion",  "GitHub · Video / World Models"),
    ("world model game simulation neural",      "GitHub · World Models"),
    ("audio generation speech synthesis game",  "GitHub · Audio AI"),

    # --- AI in games & NPCs ---
    ("topic:game-ai",                           "GitHub · Game AI"),
    ("AI NPC agent game language model",        "GitHub · Game Agents"),
    ("reinforcement learning game environment", "GitHub · RL in Games"),
    ("procedural generation game neural",       "GitHub · Proc-Gen"),

    # --- Tooling & engines ---
    ("NVIDIA DLSS upscaling real-time AI",      "GitHub · NVIDIA / AMD"),
    ("AI game engine tools unity unreal",       "GitHub · Game Engines"),
]

def _github_headers() -> dict:
    headers = {
        "User-Agent": "AI-Gaming-RSS-Reader/1.0",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _clean_html(raw: str) -> str:
    """Strip HTML tags and decode entities from a string."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return " ".join(text.split())


def _parse_date(entry) -> str | None:
    """Return an ISO date string from a feedparser entry, or None."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed)).isoformat()
    return None


def _matches_filter(text: str, keywords: list[str]) -> bool:
    """Return True if text contains at least one keyword (case-insensitive)."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def preview_feed(url: str) -> dict:
    """Fetch a feed URL and return its title and entry count (for validation)."""
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise ValueError(parsed.bozo_exception or "Could not parse feed")
    return {
        "title": _clean_html(parsed.feed.get("title", "")),
        "entry_count": len(parsed.entries),
    }


def fetch_all_feeds() -> int:
    """Fetch built-in + user-added feeds, insert new articles into DB."""
    articles = []
    all_feeds = list(FEEDS) + [
        {"name": f["name"], "url": f["url"], "category": f["category"]}
        for f in get_custom_feeds()
    ]
    for feed in all_feeds:
        filter_kw: list[str] = feed.get("filter_keywords", [])
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries:
                title = _clean_html(getattr(entry, "title", ""))
                url = getattr(entry, "link", "")
                if not title or not url:
                    continue

                # Prefer content > summary > description for the excerpt
                summary_raw = ""
                if hasattr(entry, "content") and entry.content:
                    summary_raw = entry.content[0].get("value", "")
                elif hasattr(entry, "summary"):
                    summary_raw = entry.summary
                elif hasattr(entry, "description"):
                    summary_raw = entry.description

                summary = _clean_html(summary_raw)[:500]

                # Apply keyword filter for Tier-2 feeds
                if filter_kw and not _matches_filter(title + " " + summary, filter_kw):
                    continue

                articles.append(
                    {
                        "title": title,
                        "url": url,
                        "source": feed["name"],
                        "category": feed["category"],
                        "summary": summary,
                        "published": _parse_date(entry),
                    }
                )
        except Exception as exc:
            print(f"[fetcher] Error fetching {feed['name']}: {exc}")

    if articles:
        insert_articles(articles)

    print(f"[fetcher] Processed {len(articles)} articles across {len(all_feeds)} feeds ({len(get_custom_feeds())} custom).")
    return len(articles)


def fetch_github_repos() -> int:
    """Search GitHub for trending AI-in-gaming repos and insert into DB."""
    repos = []
    seen: set[str] = set()

    for query, source_label in GITHUB_QUERIES:
        api_url = (
            "https://api.github.com/search/repositories"
            f"?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page=10"
        )
        req = urllib.request.Request(api_url, headers=_github_headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            for repo in data.get("items", []):
                url = repo.get("html_url", "")
                if not url or url in seen:
                    continue
                seen.add(url)

                stars = repo.get("stargazers_count", 0)
                topics = ", ".join(repo.get("topics", [])[:6])
                desc = repo.get("description") or ""
                summary_parts = []
                if desc:
                    summary_parts.append(desc)
                if topics:
                    summary_parts.append(f"Topics: {topics}")
                summary_parts.append(f"★ {stars:,} stars")

                repos.append({
                    "title": repo["full_name"],
                    "url": url,
                    "source": source_label,
                    "category": "GitHub",
                    "summary": " | ".join(summary_parts),
                    "published": repo.get("pushed_at") or repo.get("created_at"),
                })
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                body = exc.read().decode(errors="ignore")
                if "rate limit" in body.lower():
                    print("[github] Rate limit hit. Set GITHUB_TOKEN env var to increase quota.")
                else:
                    print(f"[github] 403 Access Denied for '{query}'. Set GITHUB_TOKEN env var.")
                break  # no point retrying other queries if we're blocked
            print(f"[github] HTTP {exc.code} for '{query}': {exc}")
        except Exception as exc:
            print(f"[github] Error fetching '{query}': {exc}")

    if repos:
        insert_articles(repos)

    print(f"[github] Processed {len(repos)} unique repos across {len(GITHUB_QUERIES)} queries.")
    return len(repos)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

# Each entry: (arXiv API search_query, source label shown on card)
ARXIV_QUERIES = [
    # Generative media
    ('ti:"text to 3D" OR ti:"3D generation" OR ti:"text-to-3D" OR ti:"3D gaussian"',
     "arXiv · Text-to-3D"),
    ('ti:"neural rendering" OR ti:"NeRF" OR ti:"gaussian splatting"',
     "arXiv · Neural Rendering"),
    ('ti:"video generation" OR ti:"video synthesis" OR ti:"world model"',
     "arXiv · Video / World Models"),
    ('ti:"text to image" OR ti:"image generation" OR ti:"diffusion model"',
     "arXiv · Text-to-Image"),
    ('ti:"audio generation" OR ti:"music generation" OR ti:"sound synthesis"',
     "arXiv · Audio AI"),

    # AI in games
    ('ti:"game" AND (ti:"reinforcement learning" OR ti:"agent" OR ti:"policy")',
     "arXiv · RL / Game Agents"),
    ('ti:"procedural generation" OR ti:"game AI" OR ti:"NPC" OR ti:"game environment"',
     "arXiv · Game AI"),
    ('ti:"game" AND (ti:"large language model" OR ti:"LLM" OR ti:"generative")',
     "arXiv · LLMs in Games"),
]

_ARXIV_BASE = "https://export.arxiv.org/api/query"


def fetch_arxiv_papers() -> int:
    """Query arXiv API for recent papers on relevant topics, insert into DB."""
    papers = []
    seen: set[str] = set()

    for query, source_label in ARXIV_QUERIES:
        params = urllib.parse.urlencode({
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 8,
        })
        url = f"{_ARXIV_BASE}?{params}"
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                # Canonical arXiv URL — strip version suffix (e.g. v1, v2)
                paper_url = re.sub(r"v\d+$", "", entry.get("id", "").strip())
                if not paper_url or paper_url in seen:
                    continue
                seen.add(paper_url)

                title = _clean_html(getattr(entry, "title", "").replace("\n", " "))
                abstract = _clean_html(getattr(entry, "summary", ""))

                # Prepend up to 3 author names
                author_names = [
                    a.get("name", "") for a in getattr(entry, "authors", [])[:3]
                ]
                if author_names:
                    suffix = " et al." if len(getattr(entry, "authors", [])) > 3 else ""
                    summary = f"{', '.join(author_names)}{suffix} — {abstract}"
                else:
                    summary = abstract

                papers.append({
                    "title": title,
                    "url": paper_url,
                    "source": source_label,
                    "category": "Research",
                    "summary": summary[:500],
                    "published": _parse_date(entry),
                })
        except Exception as exc:
            print(f"[arxiv] Error fetching '{source_label}': {exc}")

    if papers:
        insert_articles(papers)

    print(f"[arxiv] Processed {len(papers)} unique papers across {len(ARXIV_QUERIES)} queries.")
    return len(papers)


# ---------------------------------------------------------------------------
# Tavily — scrape any website (no RSS required)
# ---------------------------------------------------------------------------

def fetch_tavily_sites(sites: list[dict] | None = None) -> int:
    """Use Tavily AI search to scrape user-added websites and insert into DB."""
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        print("[tavily] No TAVILY_API_KEY set — skipping.")
        return 0

    try:
        from tavily import TavilyClient
    except ImportError:
        print("[tavily] tavily-python not installed. Run: pip install tavily-python")
        return 0

    if sites is None:
        sites = get_scraped_sites()
    if not sites:
        return 0

    client = TavilyClient(api_key=api_key)
    articles = []

    for site in sites:
        domain = urllib.parse.urlparse(site["url"]).netloc or site["url"]
        query = (site.get("query") or "").strip() or "AI gaming news"
        try:
            response = client.search(
                query=query,
                include_domains=[domain],
                max_results=10,
                search_depth="basic",
            )
            for r in response.get("results", []):
                title = (r.get("title") or "").strip()
                url = (r.get("url") or "").strip()
                if not title or not url:
                    continue
                articles.append({
                    "title": title,
                    "url": url,
                    "source": site["name"],
                    "category": site["category"],
                    "summary": (r.get("content") or "")[:500],
                    "published": r.get("published_date"),
                })
        except Exception as exc:
            print(f"[tavily] Error scraping {site['name']}: {exc}")

    if articles:
        insert_articles(articles)

    print(f"[tavily] Processed {len(articles)} articles from {len(sites)} scraped sites.")
    return len(articles)
