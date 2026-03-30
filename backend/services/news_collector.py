import feedparser
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from email.utils import parsedate_to_datetime

from config import RSS_FEEDS, PRIORITY_TOPICS, EXCLUDE_TOPICS

logger = logging.getLogger(__name__)


def _parse_date(entry: Any) -> Optional[datetime]:
    """Parse publication date from a feed entry."""
    # Try various date fields
    for date_field in ("published", "updated", "created"):
        date_str = getattr(entry, date_field, None)
        if date_str:
            try:
                return parsedate_to_datetime(date_str)
            except Exception:
                pass
    # Try parsed tuple formats
    for tuple_field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, tuple_field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _is_within_days(pub_date: Optional[datetime], days: int = 7) -> bool:
    """Check if a publication date is within the last N days."""
    if pub_date is None:
        return True  # Include if we can't determine date
    now = datetime.now(timezone.utc)
    # Ensure pub_date is timezone-aware
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(days=days)
    return pub_date >= cutoff


def _should_exclude(title: str, summary: str) -> bool:
    """Return True if the article should be excluded based on topic."""
    combined = (title + " " + summary).lower()
    for topic in EXCLUDE_TOPICS:
        if topic in combined:
            return True
    return False


def _get_summary(entry: Any) -> str:
    """Extract summary text from a feed entry."""
    # Try summary field first
    summary = getattr(entry, "summary", "") or ""
    if not summary:
        # Try content field
        content = getattr(entry, "content", None)
        if content and isinstance(content, list) and len(content) > 0:
            summary = content[0].get("value", "")
    # Strip HTML tags simply
    import re
    summary = re.sub(r"<[^>]+>", " ", summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary[:500]  # Limit to 500 chars


async def fetch_feed(outlet: str, url: str) -> List[Dict[str, Any]]:
    """Fetch and parse a single RSS feed. Returns list of news items."""
    items = []
    try:
        # feedparser is synchronous; run in thread for async compatibility
        import asyncio
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, url)

        if feed.bozo and not feed.entries:
            logger.warning(f"[{outlet}] Feed parse error: {feed.bozo_exception}")
            return []

        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            if not title:
                continue

            link = getattr(entry, "link", "") or ""
            summary = _get_summary(entry)
            pub_date = _parse_date(entry)

            # Filter by recency
            if not _is_within_days(pub_date, days=7):
                continue

            # Filter out excluded topics
            if _should_exclude(title, summary):
                continue

            items.append({
                "title": title,
                "summary": summary,
                "url": link,
                "outlet": outlet,
                "published_at": pub_date.isoformat() if pub_date else None,
            })

        logger.info(f"[{outlet}] Collected {len(items)} articles from {url}")

    except Exception as e:
        logger.error(f"[{outlet}] Failed to fetch feed from {url}: {e}")

    return items


async def collect_news() -> List[Dict[str, Any]]:
    """
    Collect news from all configured Korean media RSS feeds.
    Returns deduplicated list of news items from the last 7 days.
    """
    import asyncio

    tasks = [
        fetch_feed(outlet, url)
        for outlet, url in RSS_FEEDS.items()
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: List[Dict[str, Any]] = []
    seen_titles: set = set()

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Feed collection task failed: {result}")
            continue
        for item in result:
            # Deduplicate by title
            title_key = item["title"][:80].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                all_items.append(item)

    # Sort by priority topics: prioritized items come first
    def priority_score(item: Dict[str, Any]) -> int:
        combined = (item["title"] + " " + item["summary"]).lower()
        score = 0
        for topic in PRIORITY_TOPICS:
            if topic in combined:
                score += 1
        return score

    all_items.sort(key=priority_score, reverse=True)

    logger.info(f"Total news items collected: {len(all_items)}")
    return all_items
