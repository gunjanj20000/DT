"""Markdown to PDF and EPUB conversion with diagram and chart preservation.

Converts DeepTutor markdown responses, notes, and documents into:
1. High-fidelity vector PDFs (preserving Mermaid diagrams, Chart.js charts,
   KaTeX formulas, tables, code blocks, and callouts).
2. Screen-responsive EPUB 3 ebooks for seamless reading across all mobile
   phones, tablets, and e-reader devices.
"""

from __future__ import annotations

import base64
import html
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
import uuid

logger = logging.getLogger(__name__)

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"


class ExportConversionError(Exception):
    """Raised when document export fails."""


def find_chrome_executable() -> str | None:
    """Find a Chrome, Chromium, or Edge executable on the host system."""
    candidates = [
        os.environ.get("CHROME_BIN"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("microsoft-edge"),
        shutil.which("microsoft-edge-stable"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _clean_title(title: str) -> str:
    cleaned = (title or "").strip()
    return cleaned if cleaned else "DeepTutor Document"


def _render_markdown(markdown_text: str) -> str:
    """Render Markdown to HTML, preferring DeepTutor's built-in markdown-it-py."""
    # 1. Prefer markdown-it-py (always installed in DeepTutor core)
    try:
        from markdown_it import MarkdownIt

        md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
        return md.render(markdown_text or "")
    except Exception as exc:
        logger.debug("markdown_it render failed or not found: %s", exc)

    # 2. Fallback to mistune if available
    try:
        import mistune

        plugins = []
        for p in ["table", "strikethrough", "footnotes", "url", "task_lists"]:
            try:
                plugins.append(p)
            except Exception:
                pass
        md_mistune = mistune.create_markdown(plugins=plugins)
        return md_mistune(markdown_text or "")
    except Exception as exc:
        logger.debug("mistune render failed or not found: %s", exc)

    # 3. Plain text fallback
    escaped = html.escape(markdown_text or "")
    return f"<pre style='white-space: pre-wrap; font-family: inherit;'>{escaped}</pre>"


def _markdown_to_html_body(markdown_text: str) -> str:
    """Parse Markdown to HTML and transform rich blocks."""
    raw_html = _render_markdown(markdown_text or "")

    # 1. Transform mermaid code blocks to <div class="mermaid">
    def _replace_mermaid(match: re.Match) -> str:
        code = match.group(1)
        # Unescape HTML entities created by Markdown parser
        unescaped = html.unescape(code).strip()
        return f'<div class="mermaid-container"><pre class="mermaid">\n{unescaped}\n</pre></div>'

    raw_html = re.sub(
        r'<pre><code class="language-mermaid">([\s\S]*?)</code></pre>',
        _replace_mermaid,
        raw_html,
    )

    # 2. Transform chartjs code blocks to <canvas class="chartjs-canvas">
    def _replace_chartjs(match: re.Match) -> str:
        raw_cfg = html.unescape(match.group(1)).strip()
        cid = f"chart_{uuid.uuid4().hex[:8]}"
        escaped_cfg = html.escape(raw_cfg)
        return (
            f'<div class="chart-container">'
            f'<canvas id="{cid}" class="chartjs-canvas" data-chart="{escaped_cfg}" width="650" height="340"></canvas>'
            f"</div>"
        )

    raw_html = re.sub(
        r'<pre><code class="language-(?:chartjs|chart)">([\s\S]*?)</code></pre>',
        _replace_chartjs,
        raw_html,
    )

    # 3. Transform inline SVG code blocks to pure <div class="diagram-container"><svg...>
    def _replace_svg(match: re.Match) -> str:
        svg_content = html.unescape(match.group(1)).strip()
        return f'<div class="diagram-container">{svg_content}</div>'

    raw_html = re.sub(
        r'<pre><code class="language-svg">([\s\S]*?)</code></pre>',
        _replace_svg,
        raw_html,
    )

    # 4. Transform GitHub-style alert callouts: > [!NOTE], > [!TIP], etc.
    callout_re = re.compile(
        r'<blockquote>\s*<p>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*?)</p>\s*([\s\S]*?)</blockquote>',
        re.IGNORECASE,
    )

    def _replace_callout(match: re.Match) -> str:
        alert_type = match.group(1).upper()
        first_line = match.group(2).strip()
        rest = match.group(3).strip()
        cls = f"callout callout-{alert_type.lower()}"
        inner = f"<p>{first_line}</p>" if first_line else ""
        if rest:
            inner += f"\n{rest}"
        return f'<blockquote class="{cls}"><div class="callout-title">{alert_type}</div>{inner}</blockquote>'

    raw_html = callout_re.sub(_replace_callout, raw_html)

    # 5. Wrap tables in responsive table-container
    raw_html = re.sub(
        r"(<table>[\s\S]*?</table>)",
        r'<div class="table-container">\1</div>',
        raw_html,
    )

    return raw_html


def _get_shared_styles() -> str:
    return """
:root {
  --primary: #2563eb;
  --text-main: #1f2937;
  --text-muted: #4b5563;
  --bg-subtle: #f9fafb;
  --border-light: #e5e7eb;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--text-main);
  line-height: 1.65;
  margin: 0;
  padding: 0;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4, h5, h6 {
  color: #111827;
  font-weight: 600;
  line-height: 1.3;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  break-after: avoid;
  page-break-after: avoid;
}

h1 { font-size: 2em; border-bottom: 2px solid var(--border-light); padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid var(--border-light); padding-bottom: 0.25em; }
h3 { font-size: 1.25em; }

p {
  margin: 0.8em 0;
  word-break: break-word;
}

a {
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* Responsive Table */
.table-container {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  margin: 1.5em 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.95em;
  text-align: left;
}

th, td {
  padding: 8px 14px;
  border: 1px solid var(--border-light);
  word-break: break-word;
}

th {
  background-color: var(--bg-subtle);
  font-weight: 600;
  color: #111827;
}

tr:nth-child(even) {
  background-color: #fafbfc;
}

/* Code & Syntax */
pre {
  background-color: #f6f8fa;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.88em;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  break-inside: avoid;
  page-break-inside: avoid;
}

code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 0.88em;
  background-color: #f1f5f9;
  padding: 2px 5px;
  border-radius: 4px;
}

pre code {
  background: transparent;
  padding: 0;
  border-radius: 0;
}

/* Callouts */
blockquote {
  margin: 1.4em 0;
  padding: 12px 18px;
  background-color: #f8fafc;
  border-left: 4px solid var(--border-light);
  border-radius: 0 6px 6px 0;
  color: var(--text-muted);
  break-inside: avoid;
  page-break-inside: avoid;
}

blockquote.callout {
  border-left-width: 4px;
}
blockquote.callout .callout-title {
  font-weight: 700;
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}
blockquote.callout-note { border-left-color: #2563eb; background-color: #eff6ff; }
blockquote.callout-note .callout-title { color: #1d4ed8; }
blockquote.callout-tip { border-left-color: #16a34a; background-color: #f0fdf4; }
blockquote.callout-tip .callout-title { color: #15803d; }
blockquote.callout-important { border-left-color: #9333ea; background-color: #faf5ff; }
blockquote.callout-important .callout-title { color: #7e22ce; }
blockquote.callout-warning { border-left-color: #d97706; background-color: #fffbeb; }
blockquote.callout-warning .callout-title { color: #b45309; }
blockquote.callout-caution { border-left-color: #dc2626; background-color: #fef2f2; }
blockquote.callout-caution .callout-title { color: #b91c1c; }

/* Diagram & Visual container */
.diagram-container, .mermaid-container, .chart-container {
  width: 100%;
  max-width: 100%;
  text-align: center;
  margin: 1.8em auto;
  overflow-x: auto;
  break-inside: avoid;
  page-break-inside: avoid;
}

.diagram-container svg, .mermaid-container svg {
  max-width: 100% !important;
  height: auto !important;
  display: block;
  margin: 0 auto;
}

img, .chart-container img {
  max-width: 100% !important;
  height: auto !important;
  display: block;
  margin: 0 auto;
}

/* Math rendering */
.katex-display {
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.6em 0;
  margin: 1em 0;
  max-width: 100%;
}
"""


def _generate_intermediate_html(markdown_text: str, title: str) -> str:
    """Build a complete, standalone HTML document with local KaTeX, Mermaid, and Chart.js."""
    body_content = _markdown_to_html_body(markdown_text)
    clean_title = _clean_title(title)

    kcss_path = _VENDOR_DIR / "katex.min.css"
    kjs_path = _VENDOR_DIR / "katex.min.js"
    kauto_path = _VENDOR_DIR / "auto-render.min.js"
    mjs_path = _VENDOR_DIR / "mermaid.min.js"
    cjs_path = _VENDOR_DIR / "chart.umd.min.js"

    shared_css = _get_shared_styles()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(clean_title)}</title>
  <link rel="stylesheet" href="file://{kcss_path.resolve()}">
  <style>
    {shared_css}
    @page {{
      size: A4;
      margin: 20mm 16mm 20mm 16mm;
      @bottom-center {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 8pt;
        color: #6b7280;
        content: counter(page);
      }}
      @top-right {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 8pt;
        color: #9ca3af;
        content: "DeepTutor";
      }}
    }}
    .document-wrapper {{
      max-width: 820px;
      margin: 0 auto;
      padding: 24px;
    }}
    .document-header {{
      margin-bottom: 2rem;
      border-bottom: 2px solid #e5e7eb;
      padding-bottom: 1rem;
    }}
    .document-title {{
      font-size: 2.2rem;
      font-weight: 700;
      color: #111827;
      margin: 0 0 0.5rem 0;
    }}
    .document-badge {{
      display: inline-block;
      font-size: 0.8rem;
      font-weight: 600;
      color: #2563eb;
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      padding: 2px 8px;
      border-radius: 9999px;
    }}
  </style>
  <script src="file://{kjs_path.resolve()}"></script>
  <script src="file://{kauto_path.resolve()}"></script>
  <script src="file://{mjs_path.resolve()}"></script>
  <script src="file://{cjs_path.resolve()}"></script>
</head>
<body>
  <div class="document-wrapper">
    <header class="document-header">
      <div class="document-badge">DeepTutor Export</div>
      <h1 class="document-title">{html.escape(clean_title)}</h1>
    </header>
    <main>
      {body_content}
    </main>
  </div>
  <script>
    // 1. Render KaTeX Math
    try {{
      if (typeof renderMathInElement === 'function') {{
        renderMathInElement(document.body, {{
          delimiters: [
            {{left: '$$', right: '$$', display: true}},
            {{left: '$', right: '$', display: false}},
            {{left: '\\\\(', right: '\\\\)', display: false}},
            {{left: '\\\\[', right: '\\\\]', display: true}}
          ],
          throwOnError: false
        }});
      }}
    }} catch (e) {{
      console.error('KaTeX rendering error:', e);
    }}

    // 2. Render Chart.js Canvases & Convert to Static Images
    try {{
      if (typeof Chart === 'function') {{
        document.querySelectorAll('canvas.chartjs-canvas').forEach((canvas) => {{
          try {{
            const rawConfig = canvas.getAttribute('data-chart') || '{{}}';
            let cfg = {{}};
            try {{
              cfg = JSON.parse(rawConfig);
            }} catch (err) {{
              // Jsonish fallback
              const jsonish = rawConfig
                .replace(/([{{,]\\s*)([A-Za-z_$][\\w$]*)\\s*:/g, '$1\"$2\":')
                .replace(/'([^'\\\\]*(?:\\\\.[^'\\\\]*)*)'/g, (_m, val) => JSON.stringify(val.replace(/\\\\'/g, \"'\")))
                .replace(/,\\s*([}}\\]])/g, '$1');
              cfg = JSON.parse(jsonish);
            }}
            cfg.options = cfg.options || {{}};
            cfg.options.animation = false;
            cfg.options.responsive = false;
            new Chart(canvas, cfg);
            const dataUrl = canvas.toDataURL('image/png');
            const img = document.createElement('img');
            img.src = dataUrl;
            img.alt = 'Chart';
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            canvas.parentNode.replaceChild(img, canvas);
          }} catch (err) {{
            console.error('Failed to render chart canvas:', err);
          }}
        }});
      }}
    }} catch (e) {{
      console.error('Chart.js processing error:', e);
    }}

    // 3. Render Mermaid Diagrams
    try {{
      if (typeof mermaid === 'object' && mermaid.initialize) {{
        mermaid.initialize({{
          startOnLoad: true,
          theme: 'default',
          securityLevel: 'loose',
          fontFamily: '-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif'
        }});
      }}
    }} catch (e) {{
      console.error('Mermaid initialization error:', e);
    }}
  </script>
</body>
</html>"""


def markdown_to_pdf(markdown_text: str, title: str = "Document") -> bytes:
    """Render markdown into a vector PDF preserving all diagrams, math, and tables."""
    clean_title = _clean_title(title)
    chrome_bin = find_chrome_executable()

    if not chrome_bin:
        logger.warning("Chrome executable not found; attempting ReportLab fallback for PDF.")
        return _fallback_reportlab_pdf(markdown_text, clean_title)

    with tempfile.TemporaryDirectory(prefix="dt_pdf_") as tmpdir:
        tmp_path = Path(tmpdir)
        html_file = tmp_path / "index.html"
        pdf_file = tmp_path / "output.pdf"

        html_content = _generate_intermediate_html(markdown_text, clean_title)
        html_file.write_text(html_content, encoding="utf-8")

        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            f"--print-to-pdf={pdf_file.resolve()}",
            str(html_file.resolve()),
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExportConversionError(f"PDF generation timed out: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            raise ExportConversionError(f"Chrome PDF generation failed: {stderr}") from exc

        if not pdf_file.exists() or pdf_file.stat().st_size == 0:
            raise ExportConversionError("Chrome exited without generating output PDF file.")

        return pdf_file.read_bytes()


def _build_epub_zip(
    title: str,
    language: str,
    body_html: str,
    css: str,
    images: list[tuple[str, str, bytes]],
) -> bytes:
    """Build a valid EPUB 3 zip archive using only Python's standard library."""
    import io
    import zipfile
    from datetime import datetime, timezone

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)

        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
        zf.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

        book_id = f"urn:uuid:{uuid.uuid4()}"
        iso_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        image_manifest = []
        for img_id, img_name, _ in images:
            mime = "image/png"
            if img_name.endswith(".jpg") or img_name.endswith(".jpeg"):
                mime = "image/jpeg"
            elif img_name.endswith(".svg"):
                mime = "image/svg+xml"
            image_manifest.append(f'<item id="{img_id}" href="{img_name}" media-type="{mime}"/>')

        manifest_str = "\n    ".join(image_manifest)
        opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{html.escape(title)}</dc:title>
    <dc:language>{language}</dc:language>
    <dc:identifier id="BookID">{book_id}</dc:identifier>
    <dc:creator>DeepTutor</dc:creator>
    <meta property="dcterms:modified">{iso_now}</meta>
  </metadata>
  <manifest>
    <item id="style" href="style/nav.css" media-type="text/css"/>
    <item id="chapter1" href="chapter_1.xhtml" media-type="application/xhtml+xml"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {manifest_str}
  </manifest>
  <spine toc="toc">
    <itemref idref="chapter1"/>
  </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)

        ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
  </head>
  <docTitle><text>{html.escape(title)}</text></docTitle>
  <navMap>
    <navPoint id="navpoint-1" playOrder="1">
      <navLabel><text>{html.escape(title)}</text></navLabel>
      <content src="chapter_1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>"""
        zf.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/style/nav.css", css, compress_type=zipfile.ZIP_DEFLATED)

        xhtml = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="style/nav.css" />
</head>
<body>
  <h1>{html.escape(title)}</h1>
  {body_html}
</body>
</html>"""
        zf.writestr("OEBPS/chapter_1.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)

        for _, img_name, img_bytes in images:
            zf.writestr(f"OEBPS/{img_name}", img_bytes, compress_type=zipfile.ZIP_DEFLATED)

    return buf.getvalue()


_RESPONSIVE_EPUB_CSS = """
@namespace epub "http://www.idpf.org/2007/ops";

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
  color: #1f2937;
  padding: 4%;
  margin: 0;
  box-sizing: border-box;
}

h1, h2, h3, h4, h5, h6 {
  color: #111827;
  font-weight: 600;
  line-height: 1.3;
  margin-top: 1.4em;
  margin-bottom: 0.5em;
  page-break-after: avoid;
}

h1 { font-size: 1.85em; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.3em; }
h2 { font-size: 1.45em; border-bottom: 1px solid #f3f4f6; padding-bottom: 0.25em; }
h3 { font-size: 1.25em; }

p, ul, ol {
  margin: 0.8em 0;
  font-size: 1em;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5em 0;
  font-size: 0.9em;
  overflow-x: auto;
  display: block;
}

th, td {
  border: 1px solid #d1d5db;
  padding: 8px 12px;
  text-align: left;
}

th {
  background-color: #f3f4f6;
  font-weight: 600;
  color: #111827;
}

blockquote {
  border-left: 4px solid #2563eb;
  padding: 8px 16px;
  margin: 1.2em 0;
  background-color: #f8fafc;
  color: #334155;
  border-radius: 0 6px 6px 0;
}

blockquote.callout-tip {
  border-left-color: #10b981;
  background-color: #ecfdf5;
}

blockquote.callout-warning {
  border-left-color: #f59e0b;
  background-color: #fffbeb;
}

blockquote.callout-caution {
  border-left-color: #ef4444;
  background-color: #fef2f2;
}

.callout-title {
  font-weight: 700;
  font-size: 0.85em;
  margin-bottom: 4px;
  text-transform: uppercase;
}

pre, code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
  background-color: #f3f4f6;
  border-radius: 4px;
}

code {
  padding: 2px 5px;
}

pre {
  padding: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

img, svg {
  max-width: 100% !important;
  height: auto !important;
  display: block;
  margin: 1.5em auto;
}

.diagram-container {
  width: 100%;
  overflow-x: auto;
  margin: 1.5em 0;
  text-align: center;
}

.katex {
  font-size: 1.05em;
  line-height: 1.2;
}

.katex-display {
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.5em 0;
  margin: 1em 0;
}

@media screen and (max-width: 600px) {
  body { padding: 3% 2%; }
  h1 { font-size: 1.45em; }
  h2 { font-size: 1.2em; }
  th, td { padding: 4px 6px; font-size: 0.8em; }
  pre { padding: 8px; font-size: 0.8em; }
}
"""


def markdown_to_epub(
    markdown_text: str,
    title: str = "Document",
    language: str = "en",
) -> bytes:
    """Render markdown into a screen-responsive EPUB 3 ebook.

    Ensures all diagrams (Mermaid, SVG, charts) and math are preserved and
    formatted responsively across mobile phones, tablets, and e-readers.
    """
    clean_title = _clean_title(title)
    chrome_bin = find_chrome_executable()

    with tempfile.TemporaryDirectory(prefix="dt_epub_") as tmpdir:
        tmp_path = Path(tmpdir)
        html_file = tmp_path / "index.html"
        epub_file = tmp_path / "output.epub"

        html_content = _generate_intermediate_html(markdown_text, clean_title)
        html_file.write_text(html_content, encoding="utf-8")

        # Use Chrome to evaluate all scripts and dump the DOM with rendered SVGs & charts
        rendered_html = ""
        if chrome_bin:
            cmd = [
                chrome_bin,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--allow-file-access-from-files",
                "--run-all-compositor-stages-before-draw",
                "--dump-dom",
                str(html_file.resolve()),
            ]
            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=25,
                    check=True,
                )
                rendered_html = res.stdout
            except Exception as exc:
                logger.warning("Chrome dump-dom failed (%s); using fallback HTML for EPUB.", exc)

        if not rendered_html:
            rendered_html = html_content

        try:
            import ebooklib
            from ebooklib import epub
        except ImportError:
            ebooklib = None
            epub = None
            logger.info("ebooklib not installed; using built-in EPUB packager.")

        try:
            import bs4
            soup = bs4.BeautifulSoup(rendered_html, "html.parser")
            for tag in soup.find_all(["script", "link"]):
                tag.decompose()
            doc_header = soup.find("header", class_="document-header")
            if doc_header:
                doc_header.decompose()
        except ImportError:
            soup = None
            logger.info("beautifulsoup4 not installed; using regex parser for EPUB.")

        # Setup EbookLib EpubBook
        book = None
        if epub is not None:
            book = epub.EpubBook()
            book.set_identifier(f"urn:uuid:{uuid.uuid4()}")
            book.set_title(clean_title)
            book.set_language(language)
            book.add_author("DeepTutor")

        images_data: list[tuple[str, str, bytes]] = []

        if soup is not None:
            # Extract base64 inline images and package as EPUB image items
            img_counter = 0
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if src.startswith("data:image/"):
                    try:
                        meta, b64_data = src.split(",", 1)
                        mime_type = meta.split(";")[0].replace("data:", "")
                        ext = "png"
                        if "jpeg" in mime_type or "jpg" in mime_type:
                            ext = "jpg"
                        elif "svg" in mime_type:
                            ext = "svg"
                        img_counter += 1
                        img_filename = f"images/fig_{img_counter}.{ext}"
                        raw_bytes = base64.b64decode(b64_data)
                        images_data.append((f"img_{img_counter}", img_filename, raw_bytes))
                        img["src"] = img_filename
                    except Exception as err:
                        logger.warning("Could not extract data URL image: %s", err)

            # Ensure all SVGs are responsive
            for svg in soup.find_all("svg"):
                svg["style"] = "max-width: 100%; height: auto;"
                if not svg.parent or "diagram-container" not in (svg.parent.get("class") or []):
                    wrapper = soup.new_tag("div", attrs={"class": "diagram-container"})
                    svg.wrap(wrapper)

            # Build clean chapter content
            body_node = soup.find("main") or soup.find("body") or soup
            body_inner_html = "".join(str(c) for c in body_node.children)
        else:
            # Regex fallback when BeautifulSoup is absent
            cleaned = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", rendered_html, flags=re.IGNORECASE)
            cleaned = re.sub(r"<link\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<header class=['\"]document-header['\"][^<]*(?:(?!<\/header>)<[^<]*)*<\/header>", "", cleaned, flags=re.IGNORECASE)

            img_idx = 0

            def _extract_b64_img(m: re.Match) -> str:
                nonlocal img_idx
                mime = m.group(1)
                b64 = m.group(2)
                ext = "jpg" if ("jpeg" in mime or "jpg" in mime) else ("svg" if "svg" in mime else "png")
                img_idx += 1
                fname = f"images/fig_{img_idx}.{ext}"
                try:
                    images_data.append((f"img_{img_idx}", fname, base64.b64decode(b64)))
                    return f'<img src="{fname}" style="max-width: 100%; height: auto;"'
                except Exception:
                    return m.group(0)

            cleaned = re.sub(r'<img\b[^>]*src="data:image\/([a-zA-Z0-9+]+);base64,([a-zA-Z0-9+/=]+)"', _extract_b64_img, cleaned)
            main_match = re.search(r"<(?:main|body)[^>]*>(.*?)<\/(?:main|body)>", cleaned, flags=re.DOTALL | re.IGNORECASE)
            body_inner_html = main_match.group(1) if main_match else cleaned

        # If ebooklib is installed, use it; otherwise use built-in standard-library packager
        if epub is not None and book is not None:
            try:
                epub_css = epub.EpubItem(
                    uid="style_nav",
                    file_name="style/nav.css",
                    media_type="text/css",
                    content=_RESPONSIVE_EPUB_CSS,
                )
                book.add_item(epub_css)

                for img_id, img_name, img_bytes in images_data:
                    mime = "image/png"
                    if img_name.endswith(".jpg") or img_name.endswith(".jpeg"):
                        mime = "image/jpeg"
                    elif img_name.endswith(".svg"):
                        mime = "image/svg+xml"
                    epub_img = epub.EpubImage(
                        uid=img_id,
                        file_name=img_name,
                        media_type=mime,
                        content=img_bytes,
                    )
                    book.add_item(epub_img)

                chapter = epub.EpubHtml(
                    title=clean_title,
                    file_name="chapter_1.xhtml",
                    lang=language,
                )
                chapter.content = f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{html.escape(clean_title)}</title>
  <link rel="stylesheet" type="text/css" href="style/nav.css" />
</head>
<body>
  <h1>{html.escape(clean_title)}</h1>
  {body_inner_html}
</body>
</html>"""
                book.add_item(chapter)
                book.toc = (epub.Link("chapter_1.xhtml", clean_title, "chap_1"),)
                book.add_item(epub.EpubNcx())
                book.add_item(epub.EpubNav())
                book.spine = ["nav", chapter]

                epub.write_epub(str(epub_file.resolve()), book)
                return epub_file.read_bytes()
            except Exception as exc:
                logger.warning("ebooklib write failed (%s); using built-in packager.", exc)

        return _build_epub_zip(clean_title, language, body_inner_html, _RESPONSIVE_EPUB_CSS, images_data)


def _fallback_reportlab_pdf(markdown_text: str, title: str) -> bytes:
    """Pure-python fallback to render a clean PDF when Chrome is absent."""
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise ExportConversionError(
            "Neither Chrome nor ReportLab is available for PDF generation."
        ) from exc

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        out_path = f.name

    try:
        doc = SimpleDocTemplate(out_path, pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=HexColor("#111827"),
            spaceAfter=15,
        )
        h2_style = ParagraphStyle(
            "DocH2",
            parent=styles["Heading2"],
            fontSize=15,
            leading=18,
            textColor=HexColor("#1f2937"),
            spaceBefore=12,
            spaceAfter=8,
        )
        body_style = ParagraphStyle(
            "DocBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=HexColor("#374151"),
            spaceAfter=8,
        )

        elements: list[Any] = [Paragraph(html.escape(title), title_style), Spacer(1, 10)]

        for line in markdown_text.splitlines():
            line_str = line.strip()
            if not line_str:
                elements.append(Spacer(1, 6))
            elif line_str.startswith("# "):
                elements.append(Paragraph(html.escape(line_str[2:]), title_style))
            elif line_str.startswith("## ") or line_str.startswith("### "):
                elements.append(Paragraph(html.escape(line_str.lstrip("#").strip()), h2_style))
            else:
                elements.append(Paragraph(html.escape(line_str), body_style))

        doc.build(elements)
        with open(out_path, "rb") as rf:
            return rf.read()
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)
