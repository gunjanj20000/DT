import io
import zipfile
import pytest
from deeptutor.export.converter import markdown_to_pdf, markdown_to_epub

SAMPLE_MD = """
# Modern Public-vs-Private Distinction

In present-day society, the scope of politics is not regarded as comprehensive. A clear line is drawn between the **public** and **private** spheres.

> [!NOTE]
> Responsive export ensures clean readability across all mobile and desktop devices.

## 1. Domain Separation

| Belongs to politics | Does not belong to politics |
| :--- | :--- |
| Decisions of cabinet and parliament | Object of faith and worship |
| Election campaigns | Content of education |
| Activities of political parties | Art and culture |
| People's movements seeking change in law | Private business enterprise |

## 2. Decision Architecture

```mermaid
graph TD
    A[Civic Demand] --> B{Public Sphere?}
    B -- Yes --> C[Legislative Process]
    B -- No --> D[Private Autonomy]
    C --> E[Public Policy & Law]
```

## 3. Mathematical Foundations

The utility optimization over public goods $G$ and private goods $X$ is given by:

$$\\max_{X, G} U(X, G) \\quad \\text{subject to} \\quad X + p_G G \\le Y$$

where $\\frac{\\partial U / \\partial G}{\\partial U / \\partial X} = p_G$ is the Samuelson condition.

## 4. Distribution Analysis

```chartjs
{
  "type": "bar",
  "data": {
    "labels": ["Civic", "Economic", "Cultural", "Religious"],
    "datasets": [{
      "label": "Public Engagement Index",
      "data": [85, 65, 40, 15],
      "backgroundColor": ["#2563eb", "#0284c7", "#059669", "#d97706"]
    }]
  }
}
```
"""


def test_markdown_to_pdf():
    pdf_bytes = markdown_to_pdf(SAMPLE_MD, title="Public vs Private Distinction")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF")


def test_markdown_to_epub():
    epub_bytes = markdown_to_epub(SAMPLE_MD, title="Public vs Private Distinction", language="en")
    assert isinstance(epub_bytes, bytes)
    assert len(epub_bytes) > 2000

    # Verify EPUB structure
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    namelist = zf.namelist()
    assert "mimetype" in namelist
    assert any("chapter_1.xhtml" in n for n in namelist)
    assert any("nav.css" in n for n in namelist)

    chap_name = [n for n in namelist if "chapter_1.xhtml" in n][0]
    chapter_content = zf.read(chap_name).decode("utf-8")
    assert "<table" in chapter_content
    # Verified Mermaid rendered into SVG
    assert "<svg" in chapter_content
    # Verified callout
    assert "callout" in chapter_content
