"""
render.py — Wrap Synthesizer HTML output into a styled report.

Usage:
  python render.py                                    # uses sample_content.html → styled_report.html
  python render.py <input.html>                       # custom input → styled_report.html
  python render.py <input.html> <output.html>         # custom input → custom output
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
TEMPLATE_PATH = _HERE / "template.html"
DEFAULT_INPUT = _HERE / "sample_content.html"
DEFAULT_OUTPUT = _HERE / "styled_report.html"


def render(template_path, content_path, output_path):
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()

    html = template.replace("{{CONTENT}}", content)

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(html)

    print(f"Styled report written to: {output_path}")


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    output_file = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT
    render(TEMPLATE_PATH, input_file, output_file)
