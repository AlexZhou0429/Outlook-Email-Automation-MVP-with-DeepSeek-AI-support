from __future__ import annotations

import re
from html import escape

from bs4 import BeautifulSoup


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clip(text: str, max_chars: int) -> str:
    text = text or ""
    return text if len(text) <= max_chars else text[:max_chars] + "\n\n[TRUNCATED]"


def draft_text_to_html(text: str) -> str:
    safe = escape(text or "")
    safe = safe.replace("\n", "<br>")
    return f"<div>{safe}</div>"
