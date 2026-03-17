"""
URL content extraction module for Open Brain.
Detects URLs in text, fetches their content, and returns enriched text
with the actual page/tweet/video content for meaningful memory storage.

Supports:
- X/Twitter posts (via oEmbed API)
- YouTube videos (via oEmbed API + meta tags)
- General websites (HTML parsing: title, meta description, Open Graph, article text)
"""
import re
import json
from typing import Optional
from urllib.parse import urlparse

import requests
from lxml import html as lxml_html


# Regex for detecting URLs in text
_URL_RE = re.compile(
    r'https?://[^\s<>\[\](){}\'"]+',
    re.IGNORECASE,
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = 15


def detect_urls(text: str) -> list[str]:
    """Find all URLs in a text string."""
    return _URL_RE.findall(text)


def extract_url_content(url: str) -> dict:
    """
    Extract content from a URL. Returns:
    {
        "url": str,
        "title": str,
        "content": str,       # Main text content
        "author": str,         # If available
        "platform": str,       # "x_twitter", "youtube", "web"
        "error": str | None,
    }
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")

    try:
        # Platform-specific extractors
        if domain in ("x.com", "twitter.com"):
            return _extract_x_twitter(url)
        elif domain in ("youtube.com", "youtu.be", "m.youtube.com"):
            return _extract_youtube(url)
        else:
            return _extract_general(url)
    except Exception as e:
        return {
            "url": url,
            "title": "",
            "content": "",
            "author": "",
            "platform": "web",
            "error": str(e),
        }


def enrich_text_with_urls(text: str) -> str:
    """
    Detect URLs in text, extract their content, and return enriched text.
    Original text is preserved; extracted content is appended.
    Returns the original text unchanged if no URLs or extraction fails.
    """
    urls = detect_urls(text)
    if not urls:
        return text

    enrichments = []
    for url in urls:
        result = extract_url_content(url)
        if result.get("error") or not result.get("content"):
            continue

        parts = []
        platform = result.get("platform", "web")
        title = result.get("title", "")
        author = result.get("author", "")
        content = result.get("content", "")

        if platform == "x_twitter":
            header = "X/Twitter post"
            if author:
                header += f" by {author}"
            parts.append(f"[{header}]")
        elif platform == "youtube":
            header = "YouTube video"
            if author:
                header += f" by {author}"
            parts.append(f"[{header}]")
        else:
            header = "Web page"
            if title:
                header += f": {title}"
            parts.append(f"[{header}]")

        parts.append(content.strip())
        enrichments.append("\n".join(parts))

    if not enrichments:
        return text

    # Build enriched text: original message + extracted content
    enriched_parts = [text.strip()]
    for e in enrichments:
        enriched_parts.append(f"\n---\n{e}")

    return "\n".join(enriched_parts)


# ---------------------------------------------------------------------------
# Platform-specific extractors
# ---------------------------------------------------------------------------

def _extract_x_twitter(url: str) -> dict:
    """Extract tweet content using X/Twitter oEmbed API."""
    oembed_url = f"https://publish.twitter.com/oembed?url={url}&omit_script=true"
    resp = requests.get(oembed_url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    # oEmbed returns HTML; strip tags to get plain text
    raw_html = data.get("html", "")
    tweet_text = _strip_html_tags(raw_html)
    author = data.get("author_name", "")

    return {
        "url": url,
        "title": f"Post by {author}" if author else "X post",
        "content": tweet_text,
        "author": f"@{data.get('author_url', '').split('/')[-1]}" if data.get("author_url") else author,
        "platform": "x_twitter",
        "error": None,
    }


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    parsed = urlparse(url)
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/").split("/")[0]
    if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            return params.get("v", [None])[0]
        if parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
            return parsed.path.split("/")[2]
    return None


def _get_youtube_transcript(video_id: str) -> Optional[str]:
    """Fetch YouTube transcript/captions using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        lines = [snippet.text for snippet in transcript.snippets]
        return " ".join(lines)
    except Exception:
        return None


def _summarize_text(text: str, context: str = "YouTube video transcript") -> str:
    """Use the text LLM to summarize a long text."""
    try:
        from llm import get_client
        text_client, text_model = get_client("text")
        resp = text_client.chat.completions.create(
            model=text_model,
            messages=[
                {"role": "system", "content": (
                    f"Summarize the following {context} concisely. "
                    "Include the key topics, main points, and any actionable takeaways. "
                    "Keep it under 500 words."
                )},
                {"role": "user", "content": text[:8000]},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        # Fallback: truncate
        return text[:1500] + ("..." if len(text) > 1500 else "")


def _extract_youtube(url: str) -> dict:
    """Extract YouTube video info: title, author, transcript, and LLM summary."""
    # oEmbed for title and author
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    title = ""
    author = ""
    try:
        resp = requests.get(oembed_url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        title = data.get("title", "")
        author = data.get("author_name", "")
    except Exception:
        pass

    # Try to get the actual video transcript
    transcript_text = None
    video_id = _extract_video_id(url)
    if video_id:
        transcript_text = _get_youtube_transcript(video_id)

    # Build content
    content_parts = []
    if title:
        content_parts.append(f"Title: {title}")
    if author:
        content_parts.append(f"Channel: {author}")

    if transcript_text:
        # Summarize long transcripts with LLM
        if len(transcript_text) > 2000:
            summary = _summarize_text(transcript_text, f"YouTube video '{title}' transcript")
            content_parts.append(f"Summary: {summary}")
        else:
            content_parts.append(f"Transcript: {transcript_text}")
    else:
        # Fallback to meta description
        try:
            page_resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            page_resp.raise_for_status()
            description = _extract_meta_description(page_resp.text)
            if description:
                content_parts.append(f"Description: {description}")
        except Exception:
            pass

    content_parts.append(f"Source: {url}")

    return {
        "url": url,
        "title": title,
        "content": "\n".join(content_parts) if content_parts else "",
        "author": author,
        "platform": "youtube",
        "error": None if len(content_parts) > 1 else "Could not extract YouTube content",
    }


def _extract_general(url: str) -> dict:
    """Extract content from a general website using HTML parsing."""
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()

    # Check content type — skip binary
    ct = resp.headers.get("content-type", "")
    if "text/html" not in ct and "application/xhtml" not in ct:
        return {
            "url": url, "title": "", "content": "",
            "author": "", "platform": "web",
            "error": f"Non-HTML content type: {ct}",
        }

    page_html = resp.text
    tree = lxml_html.fromstring(page_html)

    # Title: <title> or og:title
    title = ""
    og_title = tree.xpath('//meta[@property="og:title"]/@content')
    html_title = tree.xpath('//title/text()')
    if og_title:
        title = og_title[0].strip()
    elif html_title:
        title = html_title[0].strip()

    # Author
    author = ""
    og_author = tree.xpath('//meta[@name="author"]/@content')
    if og_author:
        author = og_author[0].strip()

    # Description: og:description or meta description
    description = ""
    og_desc = tree.xpath('//meta[@property="og:description"]/@content')
    meta_desc = tree.xpath('//meta[@name="description"]/@content')
    if og_desc:
        description = og_desc[0].strip()
    elif meta_desc:
        description = meta_desc[0].strip()

    # Main content: try <article>, then <main>, then all <p> tags
    body_text = ""
    for selector in ['//article', '//main', '//div[@role="main"]']:
        nodes = tree.xpath(selector)
        if nodes:
            body_text = _get_text_content(nodes[0])
            if len(body_text) > 100:
                break

    if len(body_text) < 100:
        # Fallback: collect all <p> tags
        paragraphs = tree.xpath('//p')
        p_texts = [p.text_content().strip() for p in paragraphs if p.text_content().strip()]
        body_text = "\n\n".join(p_texts)

    # Combine: description first (concise), then body (longer)
    content_parts = []
    if description:
        content_parts.append(description)
    if body_text and body_text != description:
        # Truncate very long articles
        if len(body_text) > 3000:
            body_text = body_text[:3000] + "..."
        content_parts.append(body_text)

    content = "\n\n".join(content_parts) if content_parts else ""

    return {
        "url": url,
        "title": title,
        "content": content,
        "author": author,
        "platform": "web",
        "error": None if content else "Could not extract content from page",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html_tags(html_str: str) -> str:
    """Remove HTML tags from a string, returning plain text."""
    try:
        tree = lxml_html.fromstring(f"<div>{html_str}</div>")
        return tree.text_content().strip()
    except Exception:
        return re.sub(r'<[^>]+>', '', html_str).strip()


def _extract_meta_description(page_html: str) -> str:
    """Extract meta description or og:description from HTML."""
    try:
        tree = lxml_html.fromstring(page_html)
        og_desc = tree.xpath('//meta[@property="og:description"]/@content')
        if og_desc:
            return og_desc[0].strip()
        meta_desc = tree.xpath('//meta[@name="description"]/@content')
        if meta_desc:
            return meta_desc[0].strip()
    except Exception:
        pass
    return ""


def _get_text_content(node) -> str:
    """Extract clean text from an lxml node, collapsing whitespace."""
    raw = node.text_content()
    # Collapse whitespace but preserve paragraph breaks
    lines = [line.strip() for line in raw.split('\n') if line.strip()]
    return "\n\n".join(lines)
