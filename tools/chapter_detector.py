"""Chapter detector for parsed HTML annual reports.

Extracts heading structure from PyMuPDF HTML output for the semantic router,
then merges chapter content by tag for downstream extraction agents.

PyMuPDF HTML uses <pre class="page-text"> blocks with text-based headings —
not HTML heading tags. This module detects headings from text patterns
within those blocks.
"""

import re
from pathlib import Path


def extract_headings(html_path: str) -> list[dict]:
    """Extract heading candidates from parsed HTML.

    Scans both HTML tags (h1-h4) and text patterns within <pre> blocks.
    Returns list of {tag, text, line_number} sorted by line_number.
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    headings = []
    in_pre = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Detect <pre> block boundaries
        if stripped.startswith('<pre'):
            in_pre = True
            # Check if heading-like text is on the same line as <pre>
            inner = re.search(r'<pre[^>]*>(.*)', line, re.IGNORECASE)
            if inner:
                text = re.sub(r'<[^>]+>', '', inner.group(1)).strip()
                if _is_heading_like(text):
                    headings.append({"tag": "text", "text": text, "line_number": i})
            continue
        if stripped.startswith('</pre>'):
            in_pre = False
            continue

        # HTML heading tags
        if not in_pre:
            h_match = re.search(r'<(h[1-4])[^>]*>(.*?)</\1>', line, re.IGNORECASE)
            if h_match:
                tag = h_match.group(1).lower()
                text = re.sub(r'<[^>]+>', '', h_match.group(2)).strip()
                if text and len(text) > 1:
                    headings.append({"tag": tag, "text": text, "line_number": i})
                continue

        # Text-based heading detection within <pre> blocks
        if in_pre:
            text = re.sub(r'<[^>]+>', '', stripped)
            if _is_heading_like(text):
                headings.append({"tag": "text", "text": text, "line_number": i})

    return headings


def _is_heading_like(text: str) -> bool:
    """Check if a text line looks like a chapter/section heading.

    Matches patterns commonly found in Chinese and English annual reports:
    - "Section 1" / "Section 1.1"
    - "第X节" / "第X章" / "第X部分"
    - Roman numerals: "I.", "II.", "III.", "IV.", "V."
    - Chinese numbered: "一、" through "十、"
    - Arabic numbered: "1." / "1、" at line start
    - ALL CAPS titles (3+ words, all uppercase)
    """
    if not text or len(text) < 2:
        return False

    # Section N / Section N.N
    if re.match(r'^Section\s+\d+(\.\d+)?\b', text, re.IGNORECASE):
        return True

    # 第X节 / 第X章 / 第X部分 (Chinese chapter/section markers)
    if re.match(r'^第[一二三四五六七八九十百\d]+[节章部分编]', text):
        return True

    # Roman numeral headings: I. II. III. IV. V. VI. etc.
    if re.match(r'^[IVX]+\.\s+\S', text) and len(text) < 80:
        return True

    # Chinese numbered: 一、二、三、...十、
    if re.match(r'^[一二三四五六七八九十]+、', text) and len(text) < 80:
        return True

    # Arabic numbered: 1. / 1、at line start (but not page numbers)
    if re.match(r'^\d{1,2}[\.、]\s+\S', text) and len(text) < 80 and len(text) > 3:
        return True

    # ALL CAPS titles (3+ words) — common in English reports
    words = text.split()
    if len(words) >= 3 and all(w.isupper() or w in ('&', '-', '/', ',', 'AND', 'OF', 'THE', 'IN', 'FOR') for w in words):
        return True

    return False


def merge_chapters(route_json: list[dict], html_path: str) -> dict[str, str]:
    """Merge HTML content by tag based on router output.

    route_json format:
    [{"chapter_name": "xxx", "heading_pattern": "text to search for",
      "next_chapter_heading": "text of next chapter heading",
      "tags": ["finance", "strategy"]}, ...]

    heading_pattern and next_chapter_heading are literal text strings that
    should appear verbatim in the HTML. The function searches the full
    text content (not just headings) to find these patterns.

    Returns dict mapping tag -> merged text content.
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip HTML tags for text search (keep line structure)
    # Simple approach: search in raw content, <pre> preserves text literally
    tagged_content = {tag: [] for tag in ["strategy", "finance", "entities", "events"]}

    for chapter in route_json:
        tags = chapter.get("tags", [])
        if not tags:
            continue

        heading = chapter.get("heading_pattern", "")
        next_heading = chapter.get("next_chapter_heading", "")

        # Find start position of heading pattern in content
        start_pos = content.find(heading) if heading else -1
        if start_pos == -1:
            continue

        # Find end position (start of next chapter)
        if next_heading and next_heading != "END_OF_DOCUMENT":
            # Search for next heading AFTER the current heading
            end_pos = content.find(next_heading, start_pos + len(heading))
            if end_pos == -1:
                end_pos = len(content)
        else:
            end_pos = len(content)

        chapter_text = content[start_pos:end_pos]

        for tag in tags:
            if tag in tagged_content:
                tagged_content[tag].append(
                    f"<!-- CHAPTER: {chapter['chapter_name']} -->\n{chapter_text}"
                )

    # Merge: join chapters with separator and strip HTML tags from merged content
    result = {}
    for tag, chunks in tagged_content.items():
        if chunks:
            merged = "\n\n".join(chunks)
            # Strip HTML tags for cleaner output to extraction agents
            merged = _strip_html_tags(merged)
            result[tag] = merged
        else:
            result[tag] = ""

    return result


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags from text, preserving whitespace and content."""
    # Remove style/script blocks
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br> with newline
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


if __name__ == "__main__":
    import sys
    html = sys.argv[1] if len(sys.argv) > 1 else "input/parsed/示例汽车2024_final.html"
    print(f"Extracting headings from: {html}")
    headings = extract_headings(html)
    print(f"\nFound {len(headings)} heading candidates:")
    for h in headings[:50]:
        print(f"  L{h['line_number']:>6d} [{h['tag']:>4s}] {h['text'][:100]}")
    if len(headings) > 50:
        print(f"  ... and {len(headings) - 50} more")
