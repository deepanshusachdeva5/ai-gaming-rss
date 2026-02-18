# Optional `filter_keywords` field:
# If present, an article is only kept if its title or summary contains
# at least one of those keywords (case-insensitive).
# Omit the field (or leave it empty) to keep every article from that feed.

FEEDS = [
    # ------------------------------------------------------------------
    # Tier 1 — Company / research blogs that are already focused on AI
    #           → All articles pass through, no keyword filter
    # ------------------------------------------------------------------
    {
        "name": "NVIDIA Developer Blog",
        "url": "https://developer.nvidia.com/blog/feed/",
        "category": "AI Models",
    },
    {
        "name": "NVIDIA Technical Blog",
        "url": "https://blogs.nvidia.com/feed/",
        "category": "AI Models",
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "AI Models",
    },
    {
        "name": "Google DeepMind",
        "url": "https://deepmind.google/blog/rss.xml",
        "category": "AI Models",
    }

    # ------------------------------------------------------------------
    # Tier 2 — Broad AI/tech news; only pass articles relevant to
    #           gaming AI, model releases, or generative media
    # ------------------------------------------------------------------
]
