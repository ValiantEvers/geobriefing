#!/usr/bin/env python3
"""
Geopolitical Daily Briefing — Collector & Scorer
Fetches RSS feeds + GDELT, scores articles, outputs briefing.json
"""

import json
import re
import hashlib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import Counter
from html import unescape

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ──────────────────────────────────────────────
# RSS Fetching
# ──────────────────────────────────────────────

def fetch_rss(url, source_name, timeout=15):
    """Fetch and parse a single RSS feed. Returns list of article dicts."""
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GeoBriefing/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        root = ET.fromstring(data)

        # Handle both RSS 2.0 and Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items:
            title = (
                _text(item, "title")
                or _text(item, "atom:title", ns)
                or ""
            )
            link = (
                _text(item, "link")
                or _attr(item, "atom:link", "href", ns)
                or ""
            )
            desc = (
                _text(item, "description")
                or _text(item, "atom:summary", ns)
                or ""
            )
            pub_date = (
                _text(item, "pubDate")
                or _text(item, "atom:updated", ns)
                or ""
            )

            # Clean HTML from description
            desc = re.sub(r"<[^>]+>", "", unescape(desc)).strip()
            if len(desc) > 300:
                desc = desc[:297] + "..."

            title = unescape(title).strip()
            if not title:
                continue

            article_id = hashlib.md5((title + link).encode()).hexdigest()[:12]

            articles.append({
                "id": article_id,
                "title": title,
                "description": desc,
                "link": link,
                "source": source_name,
                "pub_date": pub_date,
            })
    except Exception as e:
        print(f"  [WARN] Failed to fetch {source_name}: {e}")

    return articles


def _text(el, tag, ns=None):
    child = el.find(tag, ns) if ns else el.find(tag)
    return child.text if child is not None and child.text else None


def _attr(el, tag, attr, ns=None):
    child = el.find(tag, ns) if ns else el.find(tag)
    return child.get(attr) if child is not None else None

# ──────────────────────────────────────────────
# GDELT Integration
# ──────────────────────────────────────────────

def fetch_gdelt_events(max_records=50):
    """Fetch recent GDELT events via the GDELT DOC 2.0 API."""
    articles = []
    try:
        # Use GDELT DOC API for article search
        query = urllib.parse.urlencode({
            "query": "sourcelang:eng",
            "mode": "ArtList",
            "maxrecords": str(max_records),
            "format": "json",
            "sort": "DateDesc",
        })
        url = f"https://api.gdeltproject.org/api/v2/doc/doc?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "GeoBriefing/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        for art in data.get("articles", []):
            title = art.get("title", "").strip()
            if not title:
                continue
            article_id = hashlib.md5(
                (title + art.get("url", "")).encode()
            ).hexdigest()[:12]

            articles.append({
                "id": article_id,
                "title": title,
                "description": art.get("seendate", ""),
                "link": art.get("url", ""),
                "source": "GDELT",
                "pub_date": art.get("seendate", ""),
                "gdelt_tone": art.get("tone", 0),
                "gdelt_domain": art.get("domain", ""),
            })
    except Exception as e:
        print(f"  [WARN] GDELT fetch failed: {e}")

    return articles

# ──────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────

def deduplicate(articles):
    """
    Group similar articles by fuzzy title matching.
    Returns list of unique articles with source_count.
    """
    groups = []

    for article in articles:
        title_words = _normalize(article["title"])
        matched = False

        for group in groups:
            ref_words = _normalize(group["title"])
            overlap = len(title_words & ref_words)
            max_len = max(len(title_words), len(ref_words), 1)
            if overlap / max_len > 0.45:
                # Merge into existing group
                group["sources"].add(article["source"])
                if len(article.get("description", "")) > len(group.get("description", "")):
                    group["description"] = article["description"]
                if article.get("link") and not group.get("link"):
                    group["link"] = article["link"]
                matched = True
                break

        if not matched:
            article["sources"] = {article["source"]}
            groups.append(article)

    # Add source_count
    for g in groups:
        g["source_count"] = len(g["sources"])
        g["source_names"] = sorted(g["sources"])
        del g["sources"]

    return groups


def _normalize(text):
    """Normalize title to set of lowercase words for comparison."""
    text = re.sub(r"[^a-zæøå0-9\s]", "", text.lower())
    stop = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "is", "are", "was", "has", "with", "by"}
    return {w for w in text.split() if w not in stop and len(w) > 2}

# ──────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────

def score_articles(articles, config):
    """Score each article on 1-10 scale using heuristic weights."""
    weights = config["scoring"]
    tracks = config["tracks"]
    g20 = [a.lower() for a in config["g20_actors"]]

    max_sources = max((a.get("source_count", 1) for a in articles), default=1)

    for article in articles:
        text = (article["title"] + " " + article.get("description", "")).lower()

        # 1) Consensus score (0-10): how many sources cover this
        src_count = article.get("source_count", 1)
        consensus = min(10, (src_count / max(max_sources, 1)) * 10)

        # 2) Track match score (0-10): does it match user's tracks?
        matched_tracks = []
        track_score = 0
        for track_name, track_data in tracks.items():
            kw_hits = sum(1 for kw in track_data["keywords"] if kw in text)
            if kw_hits > 0:
                matched_tracks.append({
                    "name": track_name,
                    "color": track_data["color"],
                    "hits": kw_hits,
                })
                track_score += min(3, kw_hits)
        track_score = min(10, track_score * 2)

        # 3) Goldstein-proxy score (0-10): intensity keywords
        intensity_words = [
            "war", "invasion", "nuclear", "crisis", "collapse", "crash",
            "sanctions", "escalat", "emergency", "coup", "missile", "attack",
            "unprecedented", "historic", "record", "surge", "plunge",
            "krig", "krise", "kollaps", "angrep", "historisk",
        ]
        intensity = sum(1 for w in intensity_words if w in text)
        goldstein = min(10, intensity * 2.5)

        # 4) G20 actor score (0-10): mentions major actors
        actor_hits = sum(1 for a in g20 if a in text)
        actor_score = min(10, actor_hits * 2.5)

        # Weighted total
        total = (
            consensus * weights["consensus_weight"]
            + track_score * weights["track_match_weight"]
            + goldstein * weights["goldstein_weight"]
            + actor_score * weights["actor_weight"]
        )

        # Scale to 1-10
        article["score"] = round(max(1, min(10, total)), 1)
        article["matched_tracks"] = matched_tracks
        article["consensus_sources"] = src_count

    return articles

# ──────────────────────────────────────────────
# Threat Level
# ──────────────────────────────────────────────

def compute_threat_level(articles):
    """Compute overall geopolitical tension level."""
    if not articles:
        return {"level": "Low", "color": "#639922"}

    avg = sum(a["score"] for a in articles) / len(articles)
    conflict_count = sum(
        1 for a in articles
        if any(t["name"] == "konflikter" for t in a.get("matched_tracks", []))
    )

    if avg >= 7.5 or conflict_count >= 3:
        return {"level": "High", "color": "#A32D2D"}
    elif avg >= 5.5 or conflict_count >= 2:
        return {"level": "Elevated", "color": "#BA7517"}
    else:
        return {"level": "Low", "color": "#639922"}

# ──────────────────────────────────────────────
# Track Summary
# ──────────────────────────────────────────────

def compute_track_summary(articles, config):
    """Count articles per track."""
    summary = {}
    for track_name, track_data in config["tracks"].items():
        count = sum(
            1 for a in articles
            if any(t["name"] == track_name for t in a.get("matched_tracks", []))
        )
        summary[track_name] = {
            "count": count,
            "color": track_data["color"],
            "label": track_name.replace("_", " / ").title(),
        }
    return summary

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    config = load_config()
    all_articles = []

    print("=== Geopolitical Daily Briefing ===")
    print(f"Fetching from {len(config['sources'])} RSS sources...")

    # 1) Fetch RSS
    for name, url in config["sources"].items():
        print(f"  Fetching {name}...")
        articles = fetch_rss(url, name)
        print(f"    → {len(articles)} articles")
        all_articles.extend(articles)

    # 2) Fetch GDELT
    print("  Fetching GDELT...")
    gdelt = fetch_gdelt_events(50)
    print(f"    → {len(gdelt)} articles")
    all_articles.extend(gdelt)

    print(f"\nTotal raw articles: {len(all_articles)}")

    # 3) Deduplicate
    unique = deduplicate(all_articles)
    print(f"After dedup: {len(unique)}")

    # 4) Score
    scored = score_articles(unique, config)

    # 5) Filter & sort
    min_score = config.get("min_score", 5.0)
    max_articles = config.get("max_articles", 10)
    filtered = [a for a in scored if a["score"] >= min_score]
    filtered.sort(key=lambda x: x["score"], reverse=True)
    top = filtered[:max_articles]

    print(f"Above threshold ({min_score}): {len(filtered)}")
    print(f"Final selection: {len(top)}")

    # 6) Compute metadata
    threat = compute_threat_level(top)
    tracks = compute_track_summary(top, config)
    now = datetime.now(timezone.utc)

    # 7) Build output
    output = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_date": now.strftime("%d. %B %Y").lower(),
        "threat_level": threat,
        "track_summary": tracks,
        "articles": [
            {
                "id": a["id"],
                "title": a["title"],
                "description": a.get("description", ""),
                "link": a.get("link", ""),
                "score": a["score"],
                "source_count": a.get("consensus_sources", 1),
                "source_names": a.get("source_names", []),
                "tracks": a.get("matched_tracks", []),
            }
            for a in top
        ],
        "stats": {
            "total_fetched": len(all_articles),
            "after_dedup": len(unique),
            "above_threshold": len(filtered),
            "published": len(top),
        },
    }

    # 8) Write output
    with open("briefing.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ briefing.json written with {len(top)} articles")
    print(f"  Threat level: {threat['level']}")
    for name, data in tracks.items():
        if data["count"] > 0:
            print(f"  {data['label']}: {data['count']} articles")


if __name__ == "__main__":
    main()
