"""Document Export Tool for DeepTutor.

Allows the AI assistant and users to export notes, answers, explanations, and
markdown documents to PDF or EPUB format, preserving all original diagrams
(Mermaid), charts (Chart.js), formulas (LaTeX/KaTeX), and tables.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import re
from typing import Any
import uuid

from deeptutor.core.tool_protocol import (
    BaseTool,
    ToolDefinition,
    ToolParameter,
    ToolPromptHints,
    ToolResult,
)
from deeptutor.export.converter import (
    ExportConversionError,
    markdown_to_epub,
    markdown_to_pdf,
)

logger = logging.getLogger(__name__)


def _slug(title: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "-", title.strip()).strip(" .")
    words = re.findall(r"[\w-]+", cleaned)
    stem = "_".join(words[:6])[:50]
    return stem or fallback


def _run_dir(injected: str | None, *, workspace_id: str = "") -> tuple[Path, str]:
    if injected and workspace_id:
        base = Path(injected)
    else:
        try:
            from deeptutor.services.workspace import get_content_workspace_service

            runtime = get_content_workspace_service().create_runtime_context(
                capability="chat",
                session_id="direct",
                turn_id="export_doc",
            )
            base = Path(runtime.output_dir) / "export"
            workspace_id = runtime.workspace_id
        except Exception:
            base = Path("data/user/workspace/outputs/export")
            workspace_id = "default"
    run = base / f"export_{uuid.uuid4().hex[:12]}"
    run.mkdir(parents=True, exist_ok=True)
    return run, workspace_id


class ExportDocumentTool(BaseTool):
    """Export markdown text, answers, or notes into PDF or screen-responsive EPUB files."""

    def get_prompt_hints(self, language: str = "en") -> ToolPromptHints:
        try:
            from deeptutor.tools.prompting import load_prompt_hints

            hints = load_prompt_hints(self.name, language=language)
            if hints.short_description:
                return hints
        except Exception:
            pass

        if str(language).lower().startswith("zh"):
            return ToolPromptHints(
                short_description="将 Markdown 内容、笔记或解答导出为精美排版的 PDF 或响应式 EPUB 文件（完美保留 Mermaid 图表、Chart.js 图表、LaTeX 公式及表格）。",
                when_to_use="当用户要求将内容导出、下载或保存为 PDF 或 EPUB 电子书时调用此工具。",
            )
        return ToolPromptHints(
            short_description="Export markdown notes, answers, or reports into beautifully formatted PDF or screen-responsive EPUB files, preserving Mermaid diagrams, charts, LaTeX math, and tables.",
            when_to_use="Use when the user asks to export, download, or save explanations, notes, or solutions as PDF or EPUB format.",
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="export_document",
            description=(
                "Export markdown text, notes, or explanations into a publication-quality PDF "
                "or screen-responsive EPUB file. Preserves all Mermaid diagrams, charts, "
                "LaTeX math equations, and tables."
            ),
            parameters=[
                ToolParameter(
                    name="content",
                    type="string",
                    description="The Markdown content to export.",
                    required=True,
                ),
                ToolParameter(
                    name="format",
                    type="string",
                    description="The target file format: 'pdf' or 'epub'.",
                    required=True,
                    enum=["pdf", "epub"],
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="The title of the document or note.",
                    required=False,
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="Language code for document metadata (e.g. 'en', 'zh', 'fr').",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        content = str(kwargs.get("content") or "").strip()
        if not content:
            return ToolResult(content="Error: 'content' parameter is required for export.", success=False)

        fmt = str(kwargs.get("format") or "pdf").strip().lower()
        if fmt not in ("pdf", "epub"):
            return ToolResult(content=f"Error: Unsupported format '{fmt}'. Supported formats are 'pdf' and 'epub'.", success=False)

        title = str(kwargs.get("title") or "").strip() or "DeepTutor Document"
        language = str(kwargs.get("language") or "en").strip()

        try:
            if fmt == "pdf":
                file_bytes = await asyncio.to_thread(markdown_to_pdf, content, title)
                ext = "pdf"
                mime = "application/pdf"
            else:
                file_bytes = await asyncio.to_thread(markdown_to_epub, content, title, language)
                ext = "epub"
                mime = "application/epub+zip"
        except ExportConversionError as exc:
            logger.warning("Document export error: %s", exc)
            return ToolResult(content=f"Export failed: {exc}", success=False)
        except Exception as exc:
            logger.exception("Unexpected error during document export")
            return ToolResult(content=f"Export error: {exc}", success=False)

        workspace_id = str(kwargs.get("_workspace_id") or "")
        run_dir, workspace_id = _run_dir(kwargs.get("_workspace_dir"), workspace_id=workspace_id)

        stem = _slug(title, "document")
        out_filename = f"{stem}.{ext}"
        out_path = run_dir / out_filename
        out_path.write_bytes(file_bytes)

        url = f"/api/workspace/files/{out_path.name}"
        try:
            from deeptutor.services.sandbox.artifacts import SandboxArtifact

            artifact = SandboxArtifact(
                filename=out_filename,
                url=url,
                path=str(out_path.resolve()),
                mime_type=mime,
                size_bytes=len(file_bytes),
            )
            from deeptutor.services.sandbox.artifacts import render_artifacts_for_tool

            summary = render_artifacts_for_tool([artifact], already_presented=not bool(workspace_id))
            return ToolResult(
                content=f"Successfully exported document '{title}' to {fmt.upper()}.\n\n{summary}",
                sources=[
                    {
                        "type": "artifact",
                        "filename": out_filename,
                        "url": url,
                        "path": str(out_path.resolve()),
                        "mime_type": mime,
                        "size_bytes": len(file_bytes),
                    }
                ],
                metadata={
                    "format": fmt,
                    "title": title,
                    "filename": out_filename,
                    "size_bytes": len(file_bytes),
                    "path": str(out_path.resolve()),
                },
            )
        except Exception:
            return ToolResult(
                content=f"Successfully exported document to {out_path.resolve()}",
                metadata={
                    "format": fmt,
                    "title": title,
                    "filename": out_filename,
                    "size_bytes": len(file_bytes),
                    "path": str(out_path.resolve()),
                },
            )


__all__ = ["ExportDocumentTool"]
