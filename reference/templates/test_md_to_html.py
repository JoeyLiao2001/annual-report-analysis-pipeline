"""
Prototype: Markdown-to-HTML converter for Synthesizer output.
No external dependencies — regex only. Handles the specific patterns used.
"""
from pathlib import Path
import re

def md_to_html(md_text: str) -> str:
    """Convert Synthesizer Markdown to HTML fragments."""
    lines = md_text.split('\n')
    result = []
    i = 0
    in_table = False
    in_thead = False
    table_rows = []

    def flush_paragraph(buf):
        if buf:
            result.append(f"<p>{' '.join(buf)}</p>")
            buf.clear()

    def flush_table():
        nonlocal in_table, in_thead, table_rows
        if not table_rows:
            return
        html = ['<table>']
        for ri, row in enumerate(table_rows):
            tag = 'th' if ri == 0 else 'td'
            html.append('<tr>')
            for cell in row:
                html.append(f'<{tag}>{cell.strip()}</{tag}>')
            html.append('</tr>')
        html.append('</table>')
        result.extend(html)
        table_rows = []
        in_table = False
        in_thead = False

    para_buf = []

    while i < len(lines):
        line = lines[i]

        # Horizontal rule
        if line.strip() == '---':
            flush_paragraph(para_buf)
            flush_table()
            result.append('<hr />')
            i += 1
            continue

        # Table
        if '|' in line and line.strip().startswith('|'):
            flush_paragraph(para_buf)
            cells = [c.strip() for c in line.strip().split('|')[1:-1]]
            # Skip separator row
            if all(re.match(r'^[-:]+$', c) for c in cells):
                i += 1
                continue
            table_rows.append(cells)
            in_table = True
            i += 1
            continue

        # End of table
        if in_table and line.strip() == '':
            flush_table()
            i += 1
            continue

        # Headings
        heading_match = re.match(r'^(#{1,4})\s+(.+)$', line)
        if heading_match:
            flush_paragraph(para_buf)
            flush_table()
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            # Clean anchor IDs from heading text
            text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text)
            result.append(f'<h{level}>{text}</h{level}>')
            i += 1
            continue

        # Blank line — paragraph break
        if line.strip() == '':
            flush_paragraph(para_buf)
            flush_table()
            i += 1
            continue

        # Bold conversion
        processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)

        # Regular text line
        para_buf.append(processed)
        i += 1

    # Flush remaining
    flush_paragraph(para_buf)
    flush_table()

    return '\n'.join(result)


if __name__ == '__main__':
    # Test with GWM Synthesizer output
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    with open(str(Path(__file__).resolve().parent / "sample_content.html"),
              'r', encoding='utf-8') as f:
        html = f.read()

    # Extract markdown-like content from the existing HTML
    # The existing file is already HTML (converted by md_to_html)
    # For testing, let's use a sample of actual Synthesizer markdown
    sample_md = """# a wholesale banking division | Corporate Insight & Supply Chain Advisory Report

**Client Corporate Profile:** DemoMotor Company Limited (示例汽车股份有限公司)
**Sector Vertical Alignment:** Industrials (Automotive Sub-Sector)
**Fiscal Assessment Period:** FY 2022 — FY 2024 (Multi-Year Review)
***

# The bank Lending Opportunity Summary — Executive Primer

## Company Pain Points & the bank Lending Thesis

**Pain Point #1: Global Expansion Capex and Refinancing Needs** - **What the company disclosed:** The company has a gearing ratio of **193.79%** (FY2023). - **Why this creates a the bank opportunity:** The company's high leverage creates demand for competitive term loans.

**Pain Point #2: ASEAN Market Entry** - **What the company disclosed:** The company has a full manufacturing base in **Thailand** and signed CKD assembly cooperation agreements in **Malaysia** and **Vietnam** in FY2024.

## Three-Year Financial Health at a Glance

| Metric | FY 2022 | FY 2023 | FY 2024 | Trend |
|--------|---------|---------|---------|-------|
| Revenue (RMB billion) | 137.3 | 173.2 | 202.2 | Strong growth |
| Gross Margin % | 19.37% | 18.73% | 19.51% | Stable |

### 0.1 Revenue & Profitability Trajectory

DemoMotor delivered robust revenue growth across the three-year period, expanding from **RMB137.3 billion** in FY2022 to **RMB173.2 billion** in FY2023 (**26.1% YoY growth**).

The revenue growth was driven by both domestic and overseas expansion. Overseas revenue surged from **RMB26.4 billion** in FY2022 to **RMB81.1 billion** in FY2024.
"""

    result = md_to_html(sample_md)
    print("=== MD to HTML Conversion ===")
    print(result[:2000])
    print("...")

    # Validate: check key conversions
    checks = [
        ('<h1>', 'H1 conversion'),
        ('<h2>', 'H2 conversion'),
        ('<h3>', 'H3 conversion'),
        ('<strong>', 'Bold conversion'),
        ('<table>', 'Table conversion'),
        ('<hr />', 'HR conversion'),
        ('<p>', 'Paragraph conversion'),
    ]
    print("\n=== Validation ===")
    for pattern, desc in checks:
        status = 'PASS' if pattern in result else 'FAIL'
        print(f'  {status}: {desc}')
