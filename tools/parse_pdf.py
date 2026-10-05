"""
PyMuPDF + Tesseract OCR hybrid PDF -> HTML parser.

Strategy:
  1. Fast font scan: detect MHeiHK CID fonts across all pages
  2. If MHeiHK found -> OCR path (slow, ~2.3s/page for those pages)
  3. If no MHeiHK -> text-only path (fast, ~30s total)
  4. Output clean HTML with page markers

Usage:
    python tools/parse_pdf.py <pdf_path> [--output <html_path>]
    python tools/parse_pdf.py input/pdfs/DemoElectronics 2025 AR_EN.pdf  # fast
    python tools/parse_pdf.py input/pdfs/示例汽车2024.pdf        # slow (OCR)
"""

import sys
import io
import time
import html as html_mod
from pathlib import Path

import fitz  # PyMuPDF


def _scan_mheihk_pages(doc: fitz.Document) -> set:
    """
    Fast scan using doc.get_page_fonts() - no text parsing needed.
    Returns set of page indices (0-based) that use MHeiHK fonts.
    """
    mheihk = set()
    for i in range(len(doc)):
        fonts = doc.get_page_fonts(i)
        for font in fonts:
            # font tuple: (xref, type, font_type, name, ...) - name at index 3
            font_name = font[3] if len(font) > 3 else str(font)
            if "MHeiHK" in font_name:
                mheihk.add(i)
                break
    return mheihk


def _ocr_page(page: fitz.Page) -> str:
    """Render page to image and run Tesseract OCR."""
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = (
        r"C:/Program Files/Tesseract-OCR/tesseract.exe"
    )

    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    return pytesseract.image_to_string(
        img,
        lang="chi_sim+eng",
        config="--tessdata-dir C:/Users/CinnamonDarkBlue/.tessdata --psm 4",
    )


def parse_pdf(pdf_path: str, output_path: str | None = None) -> str:
    """Parse PDF to HTML. Returns output file path."""
    src = Path(pdf_path)
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {src}")

    if output_path is None:
        output_path = src.parent.parent / "parsed" / f"{src.stem}_final.html"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(src))
    total = len(doc)

    # --- Step 1: Fast font scan ---
    t0 = time.time()
    print(f"Scanning {total} pages for CJK font issues...")
    mheihk_pages = _scan_mheihk_pages(doc)
    elapsed = time.time() - t0

    if mheihk_pages:
        est_min = len(mheihk_pages) * 2.5 / 60
        print(
            f"  {len(mheihk_pages)}/{total} pages use MHeiHK fonts -> OCR required"
        )
        print(f"  Estimated time: ~{est_min:.0f} min (scan took {elapsed:.0f}s)")
    else:
        print(f"  No MHeiHK fonts found -> fast text mode (~30s)")

    # --- Step 2: Extract ---
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="zh">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html_mod.escape(src.stem)}</title>",
        "<style>",
        "  body { font-family: 'Consolas', 'Microsoft YaHei', 'SimHei', monospace;",
        "         max-width: 1000px; margin: 0 auto; padding: 20px;",
        "         line-height: 1.5; background: #fff; color: #1a1a1a; }",
        "  .page-text { white-space: pre-wrap; font-size: 14px; margin: 0 0 8px 0;",
        "              padding: 12px 16px; background: #fafafa;",
        "              border-left: 3px solid #1F4E79; line-height: 1.6; }",
        "  .page-text.ocr { border-left-color: #e67e22; }",
        "  .page-marker { color: #1F4E79; font-weight: bold; font-size: 0.9em;",
        "                margin: 24px 0 4px 0;",
        "                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; }",
        "  .page-marker.ocr { color: #e67e22; }",
        "  h1 { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; }",
        "  .meta { color: #888; font-size: 0.85em;",
        "          font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{html_mod.escape(src.stem)}</h1>",
        f"<p class='meta'>Pages: {total} | OCR: {len(mheihk_pages)} | Method: {'hybrid' if mheihk_pages else 'text'}</p>",
    ]

    for i in range(total):
        is_ocr = i in mheihk_pages
        marker_cls = "page-marker ocr" if is_ocr else "page-marker"
        pre_cls = "page-text ocr" if is_ocr else "page-text"
        label = "OCR" if is_ocr else "text"

        html_parts.append(
            f'<p class="{marker_cls}" id="page-{i+1}">--- Page {i+1} [{label}] ---</p>'
        )

        try:
            text = _ocr_page(doc[i]) if is_ocr else doc[i].get_text("text")
            html_parts.append(f'<pre class="{pre_cls}">{html_mod.escape(text)}</pre>')
        except Exception as e:
            print(f"  [warn] Page {i+1} failed: {e}")
            html_parts.append(
                f'<pre class="{pre_cls}">[Error: {html_mod.escape(str(e))}]</pre>'
            )

        if (i + 1) % 50 == 0:
            elapsed_since = time.time() - t0
            print(f"  ... {i+1}/{total} ({elapsed_since:.0f}s)")

    html_parts.extend(["</body>", "</html>"])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    doc.close()

    total_time = time.time() - t0
    size_kb = output_path.stat().st_size / 1024
    print(f"\n[OK] {src.name} -> {output_path.name}")
    print(f"     Pages: {total} | OCR: {len(mheihk_pages)} | Size: {size_kb:.0f} KB | Time: {total_time:.0f}s")

    return str(output_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/parse_pdf.py <pdf_path> [--output <html_path>]")
        print("Example: python tools/parse_pdf.py input/pdfs/示例汽车2024.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[3] if len(sys.argv) >= 4 and sys.argv[2] == "--output" else None

    parse_pdf(pdf_path, output_path)
