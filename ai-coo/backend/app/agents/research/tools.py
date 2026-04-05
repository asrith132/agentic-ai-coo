"""
app/agents/research/tools.py

ResearchAgent tools:
- get_competitors()          -> derive a market topic, search discovery pages, scrape them,
                                and use an LLM to extract competitor companies/products/websites
- analyze_market_sentiment() -> search complaints/reviews/discussions, scrape sources,
                                and use an LLM to summarize sentiment and recurring themes
- generate_insight_report()  -> use an LLM to generate a founder-ready insight report

BaseAgent alignment:
- Tools do not emit events directly.
- Tools do not update global context directly.
- Tools may persist to research-owned tables.
- Tools return structured data for ResearchAgent.execute() to act on.

Tables used:
- research_competitors
- research_cache
- research_reports
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from supabase import Client, create_client


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)

# Keep bounded for hackathon cost / latency
MAX_SOURCE_TEXT_CHARS = 4000
MAX_LLM_SOURCES = 6
MAX_SEARCH_RESULTS_PER_QUERY = 5

SEARCH_ENGINE_DOMAINS = {
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "yahoo.com",
}

# These may still be useful discovery sources sometimes, but they should never
# become final competitors.
NON_COMPETITOR_FINAL_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
    "crunchbase.com",
    "g2.com",
    "capterra.com",
    "reddit.com",
    "producthunt.com",
    "news.ycombinator.com",
    "medium.com",
    "substack.com",
}


class ResearchConfigError(RuntimeError):
    pass


class ResearchToolError(RuntimeError):
    pass


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise ResearchConfigError(
            "Missing SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY."
        )
    return create_client(url, key)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _hash_query(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _normalize_website(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_search_engine_url(url: str) -> bool:
    d = _domain(url)
    return any(d.endswith(bad) for bad in SEARCH_ENGINE_DOMAINS)


def _is_usable_discovery_source(url: str) -> bool:
    """
    Discovery sources can be:
    - company sites
    - listicles
    - comparison pages
    - review pages
    - articles

    We only reject obvious search engine URLs here.
    """
    if not url:
        return False
    return not _is_search_engine_url(url)


def _is_valid_competitor_website(url: str | None) -> bool:
    if not url:
        return False
    d = _domain(url)
    if not d:
        return False
    if any(d.endswith(bad) for bad in SEARCH_ENGINE_DOMAINS | NON_COMPETITOR_FINAL_DOMAINS):
        return False
    return True


def _request_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.get(url, headers=headers or {}, timeout=20)
    response.raise_for_status()
    return response.json()


def _request_text(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    return response.text


def _call_anthropic_json(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_ANTHROPIC_MODEL,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ResearchConfigError("Missing ANTHROPIC_API_KEY.")

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    response = requests.post(
        ANTHROPIC_MESSAGES_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    blocks = data.get("content", [])
    text_parts = [block.get("text", "") for block in blocks if block.get("type") == "text"]
    raw_text = "\n".join(text_parts).strip()

    if not raw_text:
        raise ResearchToolError("Anthropic returned no text content.")

    def _try_parse_json(text: str):
        text = text.strip()

        # plain JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # fenced json
        fenced = re.search(r"```json\s*(\{.*?\}|$begin:math:display$\.\*\?$end:math:display$)\s*```", text, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        # inline object/array
        inline = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if inline:
            try:
                return json.loads(inline.group(1))
            except json.JSONDecodeError:
                pass

        return None

    parsed = _try_parse_json(raw_text)
    if parsed is not None:
        return parsed

    # Repair pass
    repair_payload = {
        "model": model,
        "max_tokens": 1200,
        "system": (
            "You repair malformed JSON. "
            "Return ONLY valid JSON. "
            "Do not add commentary."
        ),
        "messages": [
            {
                "role": "user",
                "content": (
                    "Fix this malformed JSON and return only valid JSON:\n\n"
                    f"{raw_text}"
                ),
            }
        ],
    }

    repair_response = requests.post(
        ANTHROPIC_MESSAGES_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=repair_payload,
        timeout=60,
    )
    repair_response.raise_for_status()
    repair_data = repair_response.json()

    repair_blocks = repair_data.get("content", [])
    repair_text_parts = [
        block.get("text", "") for block in repair_blocks if block.get("type") == "text"
    ]
    repaired_text = "\n".join(repair_text_parts).strip()

    parsed = _try_parse_json(repaired_text)
    if parsed is not None:
        return parsed

    raise ResearchToolError(
        f"Could not parse JSON from Anthropic response. Raw response start:\n{raw_text[:1000]}"
    )

def web_search(query: str, max_results: int = 10) -> list[dict[str, str]]:
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        raise ResearchConfigError("Missing SERPER_API_KEY.")

    response = requests.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": serper_key,
            "Content-Type": "application/json",
        },
        json={"q": query},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append(
            {
                "title": _clean_text(item.get("title", "")),
                "url": item.get("link", ""),
                "description": _clean_text(item.get("snippet", "")),
            }
        )
    return results


def scrape_url(url: str, max_chars: int = MAX_SOURCE_TEXT_CHARS) -> dict[str, Any]:
    """
    Fetch and parse a URL using requests + BeautifulSoup.

    Returns:
      {
        "url": str,
        "title": str,
        "text": str,
        "meta_description": str | None
      }
    """
    try:
        html = _request_text(url)
    except Exception as exc:
        raise ResearchToolError(f"Failed to fetch {url}: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    meta_description = None
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        meta_description = _clean_text(str(meta["content"]))

    text = _clean_text(soup.get_text(" ", strip=True))
    if len(text) > max_chars:
        text = text[:max_chars]

    return {
        "url": url,
        "title": title,
        "text": text,
        "meta_description": meta_description,
    }


def extract_company_info(url: str) -> dict[str, Any]:
    """
    Lightweight extraction from a direct company website.
    """
    page = scrape_url(url, max_chars=1200)
    title = page["title"]
    text = page["text"]
    meta_description = page["meta_description"] or ""

    parsed = urlparse(url)
    website = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else url

    raw_name = (
        title.split("|")[0].split("—")[0].split("-")[0].strip()
        if title
        else _domain(url).split(".")[0]
    )
    raw_name = re.sub(r"^(welcome to|home of)\s+", "", raw_name, flags=re.I).strip()

    return {
        "competitor_name": raw_name or _domain(url).split(".")[0].title(),
        "product_name": raw_name or _domain(url).split(".")[0].title(),
        "website": website,
        "summary": _clean_text(f"{title}. {meta_description}. {text[:500]}")[:500],
    }


def _persist_cache(
    supabase: Client,
    query: str,
    result: dict[str, Any],
    ttl_hours: int = 24,
) -> None:
    query_hash = _hash_query(query)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()

    existing = (
        supabase.table("research_cache")
        .select("id")
        .eq("query_hash", query_hash)
        .limit(1)
        .execute()
    )

    payload = {
        "query_hash": query_hash,
        "query": query,
        "result": result,
        "expires_at": expires_at,
    }

    if existing.data:
        supabase.table("research_cache").update(payload).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("research_cache").insert(payload).execute()


def _dedupe_competitors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_websites: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        competitor_name = _clean_text(str(item.get("competitor_name", "")))
        product_name = _clean_text(str(item.get("product_name", "")))
        website = _normalize_website(item.get("website"))

        if not competitor_name:
            continue

        pair = (competitor_name.lower(), product_name.lower())
        website_key = website.lower() if website else ""

        if website_key and website_key in seen_websites:
            continue
        if pair in seen_pairs:
            continue

        if website_key:
            seen_websites.add(website_key)
        seen_pairs.add(pair)

        deduped.append(
            {
                "competitor_name": competitor_name,
                "product_name": product_name or None,
                "website": website,
            }
        )

    return deduped


def _insert_competitors(supabase: Client, competitors: list[dict[str, Any]]) -> int:
    if not competitors:
        return 0

    existing_resp = (
        supabase.table("research_competitors")
        .select("competitor_name, product_name, website")
        .execute()
    )
    existing_rows = existing_resp.data or []

    existing_pairs = {
        (
            _clean_text(str(row.get("competitor_name", "")).lower()),
            _clean_text(str(row.get("product_name", "")).lower()),
        )
        for row in existing_rows
    }
    existing_websites = {
        _clean_text(str(row.get("website", "")).lower())
        for row in existing_rows
        if row.get("website")
    }

    to_insert: list[dict[str, Any]] = []
    for item in competitors:
        pair = (
            _clean_text(item["competitor_name"].lower()),
            _clean_text((item.get("product_name") or "").lower()),
        )
        website = _clean_text((item.get("website") or "").lower())

        if pair in existing_pairs:
            continue
        if website and website in existing_websites:
            continue

        to_insert.append(item)

    if not to_insert:
        return 0

    supabase.table("research_competitors").insert(to_insert).execute()
    return len(to_insert)


def _derive_topic_and_queries(
    idea_text: str,
    product_name: str,
    product_description: str,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """
    Use the LLM to derive a concise market topic plus exactly 3 discovery queries:
    - top companies in <topic>
    - best products in <topic>
    - recommended <topic>
    """
    payload = {
        "idea_text": idea_text,
        "product_name": product_name,
        "product_description": product_description,
        "keywords": keywords or [],
    }

    result = _call_anthropic_json(
        system_prompt=(
            "You are given a startup idea. Infer the market/category topic in plain English. "
            "The startup itself may not be known publicly, so do NOT search for competitors to its name. "
            "Instead, identify the market topic the company belongs to. "
            "Return ONLY valid JSON with this schema: "
            "{"
            "\"topic\": str, "
            "\"queries\": ["
            "\"top companies in <topic>\", "
            "\"best products in <topic>\", "
            "\"recommended <topic>\""
            "]"
            "}"
        ),
        user_prompt=json.dumps(payload, ensure_ascii=False),
        max_tokens=300,
    )

    topic = _clean_text(result.get("topic", ""))
    queries = result.get("queries", []) if isinstance(result, dict) else []

    cleaned_queries = [_clean_text(str(q)) for q in queries if _clean_text(str(q))]
    if len(cleaned_queries) != 3:
        if not topic:
            topic = _clean_text(" ".join((keywords or [])[:2])) or _clean_text(product_description[:60]) or "startup software"
        cleaned_queries = [
            f"top companies in {topic}",
            f"best products in {topic}",
            f"recommended {topic}",
        ]

    return {
        "topic": topic,
        "queries": cleaned_queries[:3],
    }


def _gather_discovery_sources(
    queries: list[str],
    max_results_per_query: int = MAX_SEARCH_RESULTS_PER_QUERY,
    max_total_sources: int = MAX_LLM_SOURCES,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for query in queries:
        search_results = web_search(query, max_results=max_results_per_query)
        for result in search_results:
            url = result.get("url", "")
            if not url or url in seen_urls or not _is_usable_discovery_source(url):
                continue

            seen_urls.add(url)

            text = ""
            try:
                scraped = scrape_url(url, max_chars=MAX_SOURCE_TEXT_CHARS)
                text = _clean_text(
                    " ".join(
                        part
                        for part in [
                            scraped.get("title", ""),
                            scraped.get("meta_description", ""),
                            scraped.get("text", ""),
                        ]
                        if part
                    )
                )[:MAX_SOURCE_TEXT_CHARS]
            except Exception:
                text = _clean_text(
                    " ".join(
                        [
                            result.get("title", ""),
                            result.get("description", ""),
                        ]
                    )
                )[:MAX_SOURCE_TEXT_CHARS]

            sources.append(
                {
                    "query": query,
                    "title": result.get("title", ""),
                    "url": url,
                    "description": result.get("description", ""),
                    "text": text,
                }
            )

            if len(sources) >= max_total_sources:
                return sources

    return sources


def get_competitors(
    product_name: str,
    product_description: str,
    keywords: list[str] | None = None,
    max_results: int = MAX_SEARCH_RESULTS_PER_QUERY,
) -> dict[str, Any]:
    """
    Discover competitors by:
    1. deriving a market topic from the startup idea
    2. running exactly 3 market queries:
       - top companies in <topic>
       - best products in <topic>
       - recommended <topic>
    3. scraping the returned sources
    4. using the LLM to extract likely competitors from those sources
    5. validating/deduping/saving them
    """
    keywords = keywords or []
    supabase = _get_supabase()

    idea_text = " ".join(
        part for part in [product_name, product_description, " ".join(keywords)] if part
    )

    topic_result = _derive_topic_and_queries(
        idea_text=idea_text,
        product_name=product_name,
        product_description=product_description,
        keywords=keywords,
    )
    topic = topic_result["topic"]
    queries = topic_result["queries"]

    sources = _gather_discovery_sources(
        queries,
        max_results_per_query=max_results,
        max_total_sources=MAX_LLM_SOURCES,
    )

    if not sources:
        return {
            "topic": topic,
            "queries_used": queries,
            "sources_used": [],
            "competitors_found": [],
            "saved_count": 0,
        }

    llm_input = {
        "topic": topic,
        "product_name": product_name,
        "product_description": product_description,
        "keywords": keywords,
        "sources": sources,
    }

    extraction = _call_anthropic_json(
        system_prompt=(
            "You extract likely competitors from scraped web research. "
            "Sources may include company pages, listicles, comparison pages, reviews, and articles. "
            "Identify the actual companies/products in the market topic. "
            "Do NOT return search engines, publishers, directories, social platforms, or article websites as competitors. "
            "Use only the provided sources. "
            "If a source is a list or comparison page, extract the actual market players mentioned there. "
            "Return ONLY valid JSON with this schema: "
            "{"
            "\"competitors\": ["
            "{\"competitor_name\": str, \"product_name\": str|null, \"website\": str|null, \"reason\": str}"
            "]"
            "}"
        ),
        user_prompt=json.dumps(llm_input, ensure_ascii=False),
        max_tokens=1200,
    )

    raw_competitors = extraction.get("competitors", []) if isinstance(extraction, dict) else []
    normalized_candidates: list[dict[str, Any]] = []

    for candidate in raw_competitors:
        if not isinstance(candidate, dict):
            continue

        competitor_name = _clean_text(str(candidate.get("competitor_name", "")))
        product_name_value = candidate.get("product_name")
        product_name_clean = _clean_text(str(product_name_value)) if product_name_value else None
        website = _normalize_website(candidate.get("website"))

        # If the LLM gave a website, validate it.
        if website and not _is_valid_competitor_website(website):
            website = None

        # If website missing, only infer it from a source when the source URL itself
        # plausibly belongs to that company.
        if not website and competitor_name:
            comp_name_slug = re.sub(r"[^a-z0-9]", "", competitor_name.lower())
            for source in sources:
                source_url = _normalize_website(source.get("url"))
                if not source_url or not _is_valid_competitor_website(source_url):
                    continue
                source_dom = re.sub(r"[^a-z0-9]", "", _domain(source_url))
                if comp_name_slug and comp_name_slug in source_dom:
                    website = source_url
                    break

        if competitor_name:
            normalized_candidates.append(
                {
                    "competitor_name": competitor_name,
                    "product_name": product_name_clean,
                    "website": website,
                }
            )

    deduped = _dedupe_competitors(normalized_candidates)
    saved_count = _insert_competitors(supabase, deduped)

    return {
        "topic": topic,
        "queries_used": queries,
        "sources_used": [
            {"title": s["title"], "url": s["url"], "query": s["query"]}
            for s in sources
        ],
        "competitors_found": deduped,
        "saved_count": saved_count,
    }


def _build_sentiment_queries(query: str, competitor_names: list[str]) -> list[str]:
    queries = [
        f"{query} complaints",
        f"{query} reviews",
        f"{query} problems",
        f"{query} reddit",
    ]
    for competitor in competitor_names[:4]:
        queries.extend(
            [
                f'"{competitor}" complaints',
                f'"{competitor}" reviews',
                f'"{competitor}" reddit',
            ]
        )

    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        qn = q.lower().strip()
        if qn and qn not in seen:
            seen.add(qn)
            out.append(q)
    return out[:8]


def analyze_market_sentiment(
    query: str,
    competitor_names: list[str] | None = None,
    max_sources: int = 10,
) -> dict[str, Any]:
    """
    Analyze market sentiment by:
    1. searching complaints/reviews/discussions
    2. scraping source text
    3. asking the LLM for themes, sentiment, and supporting evidence
    4. caching the result
    """
    competitor_names = competitor_names or []
    supabase = _get_supabase()

    queries = _build_sentiment_queries(query, competitor_names)
    sources = _gather_discovery_sources(queries, max_results_per_query=max_sources)

    # Keep LLM input bounded and cheaper
    sources = sources[:5]

    if not sources:
        empty_result = {
            "queries_used": queries,
            "source_count": 0,
            "sources": [],
            "theme_summary": [],
            "sentiment_breakdown": {
                "positive": {"count": 0, "share": 0.0},
                "neutral": {"count": 0, "share": 0.0},
                "negative": {"count": 0, "share": 0.0},
            },
        }
        _persist_cache(supabase, query=query, result=empty_result)
        return empty_result

    llm_input = {
        "market_query": query,
        "competitor_names": competitor_names,
        "sources": sources,
    }

    analysis = _call_anthropic_json(
        system_prompt=(
            "You analyze public market sentiment from scraped sources. "
            "Use only the provided sources. "
            "Return ONLY valid JSON with double quotes everywhere. "
            "Do not include markdown fences. "
            "Do not include trailing commas. "
            "Keep the response concise but complete. "
            "Return at most 4 themes, at most 2 evidence snippets per theme, and at most 5 source summaries. "
            "Output schema: "
            "{"
            "\"theme_summary\": ["
            "{\"theme\": str, \"sentiment\": \"positive\"|\"neutral\"|\"negative\", \"frequency\": int, \"share_of_sources\": float, \"evidence\": [str]}"
            "], "
            "\"sentiment_breakdown\": {"
            "\"positive\": {\"count\": int, \"share\": float}, "
            "\"neutral\": {\"count\": int, \"share\": float}, "
            "\"negative\": {\"count\": int, \"share\": float}"
            "}, "
            "\"sources\": ["
            "{\"title\": str, \"url\": str, \"sentiment\": \"positive\"|\"neutral\"|\"negative\", \"excerpt\": str}"
            "]"
            "}"
        ),
        user_prompt=json.dumps(llm_input, ensure_ascii=False),
        max_tokens=2200,
    )

    result = {
        "queries_used": queries,
        "source_count": len(analysis.get("sources", [])) if isinstance(analysis, dict) else 0,
        "sources": analysis.get("sources", []) if isinstance(analysis, dict) else [],
        "theme_summary": analysis.get("theme_summary", []) if isinstance(analysis, dict) else [],
        "sentiment_breakdown": analysis.get("sentiment_breakdown", {}) if isinstance(analysis, dict) else {},
    }

    if not result["sentiment_breakdown"]:
        result["sentiment_breakdown"] = {
            "positive": {"count": 0, "share": 0.0},
            "neutral": {"count": 0, "share": 0.0},
            "negative": {"count": 0, "share": 0.0},
        }

    _persist_cache(supabase, query=query, result=result)
    return result


def generate_insight_report(
    product_name: str,
    product_description: str,
    competitors: list[dict[str, Any]],
    sentiment_data: dict[str, Any],
    requesting_agent: str | None = None,
) -> dict[str, Any]:
    """
    Generate a founder-ready insight report from competitors + market sentiment,
    then persist it to research_reports.
    """
    supabase = _get_supabase()

    llm_input = {
        "product_name": product_name,
        "product_description": product_description,
        "competitors": competitors,
        "sentiment_data": sentiment_data,
    }

    report = _call_anthropic_json(
        system_prompt=(
            "You are a startup market intelligence analyst. "
            "Given competitors and sentiment findings, create a concise founder-ready report. "
            "Return ONLY valid JSON with this schema: "
            "{"
            "\"executive_summary\": str, "
            "\"key_findings\": ["
            "{\"type\": str, \"title\": str, \"detail\": str}"
            "], "
            "\"recommended_actions\": [str]"
            "}"
        ),
        user_prompt=json.dumps(llm_input, ensure_ascii=False),
        max_tokens=1000,
    )

    executive_summary = report.get("executive_summary", "") if isinstance(report, dict) else ""
    key_findings = report.get("key_findings", []) if isinstance(report, dict) else []
    recommended_actions = report.get("recommended_actions", []) if isinstance(report, dict) else []

    payload = {
        "query": f"Market insight report for {product_name}",
        "requesting_agent": requesting_agent,
        "report_type": "market_insight",
        "findings": key_findings,
        "executive_summary": executive_summary,
        "sources": [
            source.get("url")
            for source in sentiment_data.get("sources", [])[:15]
            if source.get("url")
        ],
        "status": "completed",
    }

    saved_report_id = None
    response = supabase.table("research_reports").insert(payload).execute()
    if response.data:
        saved_report_id = response.data[0].get("id")

    return {
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "recommended_actions": recommended_actions,
        "saved_report_id": saved_report_id,
    }