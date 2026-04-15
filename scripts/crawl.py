#!/usr/bin/env python3
"""
crawl.py — 每日論文爬蟲
========================
從 6 個來源抓取論文，去重合併，輸出單一 JSON 檔。

輸出：data/{YYYY-MM-DD}.json
格式：{ date, crawled_at, stats, papers[] }

每篇 paper 包含：
  id, title, authors, abstract, sources[], url, keyword_hits, upvotes, tracked_author
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TODAY = os.environ.get("SCOUT_DATE", "") or date.today().isoformat()
OUT_PATH = Path("data") / f"{TODAY}.json"

ARXIV_CATEGORIES = ["cs.CL", "cs.SD", "cs.AI", "eess.AS"]

KEYWORDS = [
    # Primary (audio/speech)
    "audio codec", "neural codec", "token learnability", "codebook",
    "speech foundation", "audio language model", "modality alignment",
    "discrete representation", "Q-Former", "connector",
    "self-supervised speech", "HuBERT", "wav2vec", "WavTokenizer",
    "ASR", "speech recognition", "speech-to-text",
    "text-to-speech", "TTS", "voice cloning", "voice conversion",
    "audio-visual", "lip reading", "lip-to-speech",
    # Primary (methods)
    "continual fine-tuning", "catastrophic forgetting", "domain adaptation",
    "inference-time scaling", "test-time adaptation", "training-free",
    "early exit", "recursive transformer", "dynamic depth",
    "contrastive learning", "DPO", "preference optimization",
    # Secondary
    "LoRA", "adapter", "PEFT",
    "agent", "tool-calling", "function calling",
    "multimodal", "large language model",
    "whisper", "Qwen2-Audio", "SALMONN",
    "music generation", "audio generation", "sound event",
]

TRACKED_AUTHORS = {
    "Hung-yi Lee": "2364785",
    "Abdelrahman Mohamed": "40aborahman",
    "Shinji Watanabe": "1757803",
    "Kaiming He": "1771551",
}

KEYWORD_SEARCHES = [
    "audio codec",
    "speech foundation model",
    "audio language model",
    "modality alignment audio",
    "inference-time scaling",
]

HEADERS = {"User-Agent": "DailyPaperScout/1.0 (github.com/voidful/paper-daily)"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_url(url, retries=3, delay=2.0):
    req = urllib.request.Request(url, headers=HEADERS)
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  ⚠ {url[:60]}... attempt {i+1}: {e}")
            if i < retries - 1:
                time.sleep(delay * (i + 1))
    return None


def fetch_json(url):
    text = fetch_url(url)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def kw_score(text):
    t = text.lower()
    return sum(1 for k in KEYWORDS if k.lower() in t)


def normalize_id(raw):
    """Extract clean arxiv ID from various formats."""
    if not raw:
        return ""
    if "/abs/" in raw:
        raw = raw.split("/abs/")[-1]
    return re.sub(r"v\d+$", "", raw).strip()


def make_paper(*, arxiv_id, title, authors, abstract, source, **extra):
    """Create a standardized paper dict."""
    arxiv_id = normalize_id(arxiv_id)
    return {
        "id": arxiv_id,
        "title": title.strip().replace("\n", " "),
        "authors": authors[:5],
        "abstract": abstract.strip().replace("\n", " ")[:600],
        "sources": [source],
        "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        "keyword_hits": kw_score(title + " " + abstract),
        **{k: v for k, v in extra.items() if v},
    }


# ---------------------------------------------------------------------------
# Source crawlers — each returns list[dict]
# ---------------------------------------------------------------------------

def crawl_huggingface():
    print("📥 HuggingFace Daily Papers")
    raw = fetch_json("https://huggingface.co/api/daily_papers?limit=100")
    if not raw:
        return []
    papers = []
    for item in raw:
        p = item.get("paper", {})
        papers.append(make_paper(
            arxiv_id=p.get("id", ""),
            title=p.get("title", ""),
            authors=[a.get("name", "") for a in p.get("authors", [])],
            abstract=p.get("summary", ""),
            source="huggingface",
            upvotes=item.get("numUpvotes", 0),
        ))
    print(f"  → {len(papers)} papers")
    return papers


def crawl_arxiv_category(cat):
    print(f"📥 arXiv {cat}")
    q = urllib.parse.quote(f"cat:{cat}")
    url = f"http://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=80"
    xml = fetch_url(url)
    if not xml:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    papers = []
    for e in root.findall("a:entry", ns):
        papers.append(make_paper(
            arxiv_id=e.findtext("a:id", "", ns),
            title=e.findtext("a:title", "", ns),
            authors=[a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)],
            abstract=e.findtext("a:summary", "", ns),
            source=f"arxiv_{cat}",
        ))
    print(f"  → {len(papers)} papers")
    time.sleep(3)
    return papers


def crawl_arxiv_keywords():
    print("📥 arXiv keyword search")
    all_papers = []
    seen = set()
    for kw in KEYWORD_SEARCHES:
        q = urllib.parse.quote(f'all:"{kw}"')
        url = f"http://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=15"
        xml = fetch_url(url)
        if not xml:
            time.sleep(3)
            continue
        ns = {"a": "http://www.w3.org/2005/Atom"}
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            time.sleep(3)
            continue
        for e in root.findall("a:entry", ns):
            aid = normalize_id(e.findtext("a:id", "", ns))
            if aid in seen:
                continue
            seen.add(aid)
            all_papers.append(make_paper(
                arxiv_id=aid,
                title=e.findtext("a:title", "", ns),
                authors=[a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)],
                abstract=e.findtext("a:summary", "", ns),
                source="arxiv_keyword",
                search_keyword=kw,
            ))
        time.sleep(3)
    print(f"  → {len(all_papers)} papers")
    return all_papers


def crawl_semantic_scholar():
    print("📥 Semantic Scholar (tracked researchers)")
    cutoff = datetime.now().year - 1
    all_papers = []
    for name, sid in TRACKED_AUTHORS.items():
        if not sid:
            continue
        print(f"  🔍 {name}")
        url = (f"https://api.semanticscholar.org/graph/v1/author/{sid}/papers"
               f"?fields=title,abstract,externalIds,year,venue,citationCount,authors&limit=10")
        data = fetch_json(url)
        if not data or "data" not in data:
            time.sleep(1)
            continue
        for p in data["data"]:
            yr = p.get("year")
            if not yr or yr < cutoff:
                continue
            ext = p.get("externalIds") or {}
            all_papers.append(make_paper(
                arxiv_id=ext.get("ArXiv", ""),
                title=p.get("title", ""),
                authors=[a.get("name", "") for a in (p.get("authors") or [])],
                abstract=p.get("abstract") or "",
                source="semantic_scholar",
                tracked_author=name,
                citations=p.get("citationCount", 0),
            ))
        time.sleep(1)
    print(f"  → {len(all_papers)} papers")
    return all_papers


def crawl_paperswithcode():
    print("📥 Papers With Code")
    data = fetch_json("https://paperswithcode.com/api/v1/papers/?ordering=-date&items_per_page=50")
    if not data or "results" not in data:
        return []
    papers = []
    for item in data["results"]:
        papers.append(make_paper(
            arxiv_id=item.get("arxiv_id", ""),
            title=item.get("title", ""),
            authors=item.get("authors") or [],
            abstract=item.get("abstract") or "",
            source="paperswithcode",
        ))
    print(f"  → {len(papers)} papers")
    return papers


def crawl_alphaxiv():
    print("📥 alphaXiv trending")
    html = fetch_url("https://alphaxiv.org/trending")
    if not html:
        return []
    ids = list(dict.fromkeys(re.findall(r"(?:arxiv|alphaxiv)\.org/abs/(\d{4}\.\d{4,5})", html)))
    if not ids:
        return []
    batch = ids[:20]
    xml = fetch_url(f"http://export.arxiv.org/api/query?id_list={','.join(batch)}&max_results={len(batch)}")
    if not xml:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    papers = []
    try:
        root = ET.fromstring(xml)
        for i, e in enumerate(root.findall("a:entry", ns)):
            papers.append(make_paper(
                arxiv_id=e.findtext("a:id", "", ns),
                title=e.findtext("a:title", "", ns),
                authors=[a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)],
                abstract=e.findtext("a:summary", "", ns),
                source="alphaxiv",
                trending_rank=i + 1,
            ))
    except ET.ParseError:
        pass
    print(f"  → {len(papers)} papers")
    return papers


# ---------------------------------------------------------------------------
# Dedup + Merge
# ---------------------------------------------------------------------------

def merge(all_papers):
    """Deduplicate by arxiv ID, merge source lists."""
    by_id = {}
    no_id = []
    for p in all_papers:
        aid = p.get("id", "").strip()
        if not aid:
            no_id.append(p)
            continue
        if aid in by_id:
            existing = by_id[aid]
            # Merge sources
            for s in p["sources"]:
                if s not in existing["sources"]:
                    existing["sources"].append(s)
            # Keep max keyword_hits
            existing["keyword_hits"] = max(existing["keyword_hits"], p["keyword_hits"])
            # Keep longer abstract
            if len(p.get("abstract", "")) > len(existing.get("abstract", "")):
                existing["abstract"] = p["abstract"]
            # Keep upvotes / tracked_author / citations
            for key in ("upvotes", "tracked_author", "citations", "trending_rank"):
                if p.get(key) and not existing.get(key):
                    existing[key] = p[key]
        else:
            by_id[aid] = p

    # Add no-id papers (deduplicate by title)
    titles_seen = {p["title"].lower() for p in by_id.values()}
    for p in no_id:
        if p["title"].lower() not in titles_seen:
            titles_seen.add(p["title"].lower())
            by_id[p["title"]] = p

    return list(by_id.values())


def priority(p):
    """Compute sort priority. Higher = more relevant."""
    s = p.get("keyword_hits", 0) * 10
    s += (len(p.get("sources", [])) - 1) * 15       # multi-source bonus
    s += min(p.get("upvotes", 0), 50) * 0.5          # HF upvotes
    s += 20 if p.get("tracked_author") else 0         # tracked researcher
    s += min(p.get("citations", 0), 100) * 0.1       # citations
    if p.get("trending_rank"):
        s += max(0, 20 - p["trending_rank"])          # alphaXiv rank
    return s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"🚀 Daily Paper Crawler — {TODAY}\n")

    all_papers = []
    stats = {}

    # Crawl all sources
    crawlers = [
        ("huggingface", crawl_huggingface),
        ("arxiv_cs.CL", lambda: crawl_arxiv_category("cs.CL")),
        ("arxiv_cs.SD", lambda: crawl_arxiv_category("cs.SD")),
        ("arxiv_cs.AI", lambda: crawl_arxiv_category("cs.AI")),
        ("arxiv_eess.AS", lambda: crawl_arxiv_category("eess.AS")),
        ("arxiv_keyword", crawl_arxiv_keywords),
        ("semantic_scholar", crawl_semantic_scholar),
        ("paperswithcode", crawl_paperswithcode),
        ("alphaxiv", crawl_alphaxiv),
    ]

    for name, fn in crawlers:
        try:
            papers = fn()
            stats[name] = len(papers)
            all_papers.extend(papers)
        except Exception as e:
            print(f"  ❌ {name} failed: {e}")
            stats[name] = 0
        print()

    # Merge & sort
    unique = merge(all_papers)
    for p in unique:
        p["priority"] = round(priority(p), 1)
    unique.sort(key=lambda p: p["priority"], reverse=True)

    # Remove zero-priority noise (keep top papers manageable for LLM)
    # Keep all with keyword_hits > 0, plus top 100 even if 0 hits
    relevant = [p for p in unique if p["keyword_hits"] > 0]
    filler = [p for p in unique if p["keyword_hits"] == 0][:100]
    final = relevant + filler

    # Build output
    output = {
        "date": TODAY,
        "crawled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stats": {
            "sources": stats,
            "total_crawled": sum(stats.values()),
            "after_dedup": len(unique),
            "keyword_matched": len(relevant),
        },
        "papers": final,
    }

    # Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Update index
    update_index(output)

    # Print summary
    print("=" * 50)
    print(f"✅ {TODAY} — {len(final)} papers saved to {OUT_PATH}")
    print(f"   Keyword matched: {len(relevant)}")
    print(f"   Top 5:")
    for p in final[:5]:
        print(f"   {p['priority']:5.0f} | {p['keyword_hits']}kw | {p['title'][:65]}")

    if len(final) == 0:
        print("\n⚠️  No papers found — all sources may be down.")
        sys.exit(1)


def update_index(today_output):
    """Update data/index.json with today's entry."""
    index_path = Path("data") / "index.json"
    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {"entries": []}

    # Remove existing entry for today (if re-running)
    index["entries"] = [e for e in index["entries"] if e["date"] != TODAY]

    # Add today
    index["entries"].append({
        "date": TODAY,
        "file": f"{TODAY}.json",
        "total_papers": len(today_output["papers"]),
        "keyword_matched": today_output["stats"]["keyword_matched"],
        "crawled_at": today_output["crawled_at"],
    })

    # Sort by date descending
    index["entries"].sort(key=lambda e: e["date"], reverse=True)
    index["latest"] = TODAY

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
