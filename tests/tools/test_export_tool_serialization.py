"""Test ExportDocumentTool serialization and prompt hints."""

import pytest

from deeptutor.api.routers.tools import _build_tool_payload, _serialise_hints
from deeptutor.core.tool_protocol import ToolPromptHints
from deeptutor.tools.export_tool import ExportDocumentTool


def test_export_document_tool_prompt_hints():
    tool = ExportDocumentTool()
    hints_en = tool.get_prompt_hints(language="en")
    assert isinstance(hints_en, ToolPromptHints)
    assert len(hints_en.short_description) > 0

    hints_zh = tool.get_prompt_hints(language="zh")
    assert isinstance(hints_zh, ToolPromptHints)
    assert len(hints_zh.short_description) > 0


def test_serialise_hints_tolerates_strings_and_none():
    payload_none = _serialise_hints(None)
    assert payload_none.short_description == ""

    payload_str = _serialise_hints("raw description string")
    assert payload_str.short_description == "raw description string"

    payload_obj = _serialise_hints(ToolPromptHints(short_description="custom desc", when_to_use="now"))
    assert payload_obj.short_description == "custom desc"
    assert payload_obj.when_to_use == "now"


def test_build_tool_payload_for_export_document_tool():
    tool = ExportDocumentTool()
    payload = _build_tool_payload(tool, enabled_optional=set())
    assert payload.name == "export_document"
    assert "en" in payload.hints
    assert "zh" in payload.hints
    assert len(payload.hints["en"].short_description) > 0
