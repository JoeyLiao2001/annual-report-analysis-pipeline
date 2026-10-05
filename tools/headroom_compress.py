#!/usr/bin/env python3
"""
headroom_compress.py — Compress annual report HTML before LLM ingestion.

Two modes:
  1. headroom (SmartCrusher) — content-aware: keeps table structure + metrics,
     drops boilerplate. Requires: pip install headroom-ai
  2. fallback (built-in) — strips HTML tags, removes page boilerplate,
     keeps only substantive text + table data. No dependencies beyond stdlib.

headroom mode saves 60-92% tokens; fallback mode saves ~40-60%.

Usage:
  python tools/headroom_compress.py <input.html> <output.txt> [--mode headroom|fallback]
"""

import re
import sys
from pathlib import Path

# ── Headroom imports (optional) ──
try:
    from headroom import compress, SmartCrusher
    HEADROOM_AVAILABLE = True
except ImportError:
    HEADROOM_AVAILABLE = False


# ── Regex patterns for boilerplate removal ──
# Chinese annual reports have highly repetitive page-level boilerplate
PAGE_NUMBER_PATTERN = re.compile(r'<!-- PAGE \d+ -->')
HEADER_FOOTER_PATTERNS = [
    re.compile(r'第\s*\d+\s*页\s*共\s*\d+\s*页'),  # Page X of Y
    re.compile(r'\d+/\d+'),                          # X/Y
    re.compile(r'年度报告\s*\d{4}'),                  # 年度报告 2024
    re.compile(r'[A-Za-z]+\s+Annual\s+Report\s+\d{4}'),
    re.compile(r'股票代码[：:]\s*\d+'),               # Stock code header
    re.compile(r'公告编号[：:].*?(?=\n|$)'),           # Announcement number
]

# Patterns for content that's worth keeping
FINANCIAL_TABLE_START = re.compile(
    r'(合并资产负债|合并利润|合并现金流量|合并所有者权益|财务报表附注|'
    r'consolidated\s+(balance\s+sheet|income\s+statement|cash\s+flow|'
    r'statement\s+of\s+financial\s+position))',
    re.IGNORECASE
)

# Boilerplate paragraphs that repeat in every annual report
BOILERPLATE_PATTERNS = [
    re.compile(r'本公司董事会[及、与].*?保证.*?不存在.*?虚假记载[、，].*?误导性陈述.*?重大遗漏'),
    re.compile(r'公司全体董事出席董事会会议'),
    re.compile(r'本报告所涉及[的]未来计划[、，].*?不构成.*?承诺'),
    re.compile(r'公司已在本报告中详细描述.*?风险[，。]'),
    re.compile(r'经董事会审议通过[的].*?利润分配'),
    re.compile(r'The\s+Board\s+of\s+Directors.*?hereby\s+confirms'),
]


def compress_fallback(html_text: str, keep_structure: bool = True) -> str:
    """Built-in HTML compression for annual reports.

    Strategy (in order):
      1. Remove page markers (<!-- PAGE N -->)
      2. Strip HTML tags, keep text content
      3. Remove page headers/footers (repeated every page)
      4. Remove legal boilerplate paragraphs
      5. Collapse whitespace
      6. If keep_structure: preserve table data blocks with row markers

    Returns compressed text. Typically 40-60% reduction from raw HTML.
    """
    text = html_text

    # Step 1: Remove page markers
    text = PAGE_NUMBER_PATTERN.sub('', text)

    # Step 2: Strip HTML tags
    # Remove style/script entirely
    text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level tags with newlines
    text = re.sub(r'</?(div|p|tr|table|h[1-6]|li|br|hr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Replace td/th with tabs (table structure)
    if keep_structure:
        text = re.sub(r'</?(td|th)[^>]*>', '\t', text, flags=re.IGNORECASE)
    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Step 3: Remove page-level headers/footers
    for pattern in HEADER_FOOTER_PATTERNS:
        text = pattern.sub('', text)

    # Step 4: Remove legal boilerplate
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub('[BOILERPLATE REMOVED]', text)

    # Step 5: Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)          # Collapse spaces/tabs
    text = re.sub(r'\n{3,}', '\n\n', text)       # Collapse multiple blank lines
    text = re.sub(r'^\s*\n', '', text, flags=re.MULTILINE)  # Remove blank lines

    # Step 6: Deduplicate repeated lines (common in page headers/footers)
    lines = text.split('\n')
    seen = set()
    unique_lines = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) < 3:
            continue  # Skip near-empty lines
        if stripped not in seen:
            seen.add(stripped)
            unique_lines.append(line)
        # Allow repeats if line is >80 chars (likely actual content)
        elif len(stripped) > 80:
            unique_lines.append(line)

    return '\n'.join(unique_lines)


def compress_headroom(html_text: str, context_label: str = "") -> str:
    """Compress using Headroom's message-list compression.

    Headroom's compress() operates on LLM-format messages [{"role":..., "content":...}],
    not raw text. We wrap the HTML as a single user message, then compress.
    The compression uses a small/fast model to summarize the content while
    preserving key information.

    This is different from SmartCrusher (which compresses lists of search results).
    For annual reports, message compression extracts the financial narrative
    while preserving numbers and table structure.
    """
    if not HEADROOM_AVAILABLE:
        raise RuntimeError("headroom not installed. Run: pip install headroom-ai")

    # Build messages: system prompt tells compressor this is an annual report
    messages = [
        {
            "role": "system",
            "content": (
                "You are compressing a Chinese company annual report HTML for a financial analyst. "
                "PRESERVE: all numerical values (RMB amounts, percentages, ratios), table structures, "
                "financial terminology, company names, subsidiary names, country names. "
                "REMOVE: HTML markup, page headers/footers, legal boilerplate, repetitive disclaimers, "
                "page number markers, navigation text."
            )
        },
        {
            "role": "user",
            "content": html_text[:500000]  # Truncate to 500K chars if needed
        }
    ]

    # Compress using headroom's default model
    result = compress(
        messages=messages,
        model="claude-haiku-4-5",  # Fast/cheap model for compression
        model_limit=200000,        # Max tokens for compressed output
        optimize=True,
    )

    # result.compressed_messages contains the compressed version
    if hasattr(result, 'compressed_messages'):
        compressed = result.compressed_messages[-1]["content"] if result.compressed_messages else ""
    elif isinstance(result, dict):
        compressed = result.get("compressed_messages", [{}])[-1].get("content", "") if result.get("compressed_messages") else ""
    else:
        compressed = str(result)

    return compressed


def compress_file(input_path: Path, output_path: Path, mode: str = "headroom",
                  context_label: str = "") -> dict:
    """Compress an HTML file and write the result.

    Args:
        input_path: Path to the _final.html file.
        output_path: Where to write compressed output.
        mode: "headroom" or "fallback".
        context_label: Label for SmartCrusher context tracking.

    Returns:
        dict with stats: original_bytes, compressed_bytes, reduction_pct, mode.
    """
    html_text = input_path.read_text(encoding="utf-8")

    original_bytes = len(html_text.encode("utf-8"))

    if mode == "headroom" and HEADROOM_AVAILABLE:
        compressed = compress_headroom(html_text, context_label)
    else:
        if mode == "headroom" and not HEADROOM_AVAILABLE:
            print(f"[headroom_compress] headroom not installed, using fallback mode",
                  file=sys.stderr)
        compressed = compress_fallback(html_text)

    compressed_bytes = len(compressed.encode("utf-8"))
    reduction_pct = round((1 - compressed_bytes / original_bytes) * 100, 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(compressed, encoding="utf-8")

    return {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "reduction_pct": reduction_pct,
        "mode": mode if (mode == "headroom" and HEADROOM_AVAILABLE) else "fallback",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python headroom_compress.py <input.html> <output.txt> [--mode headroom|fallback]")
        print(f"  headroom available: {HEADROOM_AVAILABLE}")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    mode = "headroom"
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        mode = sys.argv[idx + 1]

    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    stats = compress_file(input_path, output_path, mode=mode)
    print(f"  Input:      {stats['input_file']}")
    print(f"  Output:     {stats['output_file']}")
    print(f"  Original:   {stats['original_bytes']:,} bytes")
    print(f"  Compressed: {stats['compressed_bytes']:,} bytes")
    print(f"  Reduction:  {stats['reduction_pct']}%")
    print(f"  Mode:       {stats['mode']}")
