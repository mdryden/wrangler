import datetime
import io
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pypdf
import pytest

from core.config import settings
from services.ai.base import BaseReceiptParserProvider, ReceiptParseResult
from services.ai.factory import get_receipt_parser
from services.ai.mock_provider import MockReceiptParser
from services.ai.openai_provider import OpenAIReceiptParser


def create_blank_pdf(num_pages: int = 1) -> bytes:
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_receipt_parse_result_model():
    result = ReceiptParseResult(
        merchant="Staples",
        date=datetime.date(2026, 3, 1),
        total_amount=Decimal("42.50"),
        description="Staples - Paper supplies",
    )
    assert result.merchant == "Staples"
    assert result.date == datetime.date(2026, 3, 1)
    assert result.total_amount == Decimal("42.50")
    assert result.description == "Staples - Paper supplies"

    dump = result.model_dump()
    assert dump["total_amount"] == Decimal("42.50")
    assert dump["date"] == datetime.date(2026, 3, 1)

    # Optional fields default to None
    empty_result = ReceiptParseResult()
    assert empty_result.merchant is None
    assert empty_result.date is None
    assert empty_result.total_amount is None
    assert empty_result.description is None

    # Decimal coercing from float and str
    from_float = ReceiptParseResult.model_validate({"total_amount": 19.99})
    assert from_float.total_amount == Decimal("19.99")

    from_str = ReceiptParseResult.model_validate({"total_amount": "19.99"})
    assert from_str.total_amount == Decimal("19.99")


@pytest.mark.anyio
async def test_mock_receipt_parser_deterministic_amounts():
    parser = MockReceiptParser()
    assert parser.provider_id == "mock"
    assert isinstance(parser, BaseReceiptParserProvider)

    # Pattern: amount with dot
    res1 = await parser.parse_receipt(b"dummy", "receipt_87.45.jpg", "image/jpeg")
    assert res1.total_amount == Decimal("87.45")
    assert res1.merchant == "Sample Store"
    assert res1.date == datetime.date.today()
    assert res1.description == "Sample Store - Office supplies"

    # Pattern: amount with underscore
    res2 = await parser.parse_receipt(b"dummy", "invoice_120_50.png", "image/png")
    assert res2.total_amount == Decimal("120.50")

    # Fallback default when no amount pattern matches
    res3 = await parser.parse_receipt(b"dummy", "scan_random_receipt.pdf", "application/pdf")
    assert res3.total_amount == Decimal("45.99")


@pytest.mark.anyio
async def test_mock_receipt_parser_special_cues_and_errors():
    parser = MockReceiptParser()

    # Missing total cue
    res = await parser.parse_receipt(b"dummy", "receipt_missing_total.jpg", "image/jpeg")
    assert res.total_amount is None
    assert res.merchant == "Sample Store"

    # Corrupt document simulation
    with pytest.raises(ValueError, match="Corrupt or unreadable document"):
        await parser.parse_receipt(b"dummy", "receipt_corrupt.png", "image/png")

    with pytest.raises(ValueError, match="Corrupt or unreadable document"):
        await parser.parse_receipt(b"dummy", "invoice_fail.pdf", "application/pdf")

    with pytest.raises(ValueError, match="Corrupt or unreadable document"):
        await parser.parse_receipt(b"dummy", "sample_invalid.jpg", "image/jpeg")

    # Timeout simulation
    with pytest.raises(RuntimeError, match="AI provider request timed out"):
        await parser.parse_receipt(b"dummy", "document_timeout.png", "image/png")


def test_openai_receipt_parser_init_validation():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        OpenAIReceiptParser(api_key="")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        OpenAIReceiptParser(api_key="   ")

    parser = OpenAIReceiptParser(api_key="sk-test-key", model="gpt-4o", base_url="https://api.openai.com/v1/")
    assert parser.provider_id == "openai"
    assert parser.api_key == "sk-test-key"
    assert parser.model == "gpt-4o"
    assert parser.base_url == "https://api.openai.com/v1"
    assert parser.timeout_seconds == 60
    assert parser.max_pdf_pages == 10


@pytest.mark.anyio
async def test_openai_receipt_parser_unsupported_mime():
    parser = OpenAIReceiptParser(api_key="sk-test")
    with pytest.raises(ValueError, match="Unsupported MIME type: application/zip"):
        await parser.parse_receipt(b"content", "file.zip", "application/zip")


@pytest.mark.anyio
async def test_openai_receipt_parser_corrupt_pdf():
    parser = OpenAIReceiptParser(api_key="sk-test")
    with pytest.raises(ValueError, match="Corrupt or unreadable PDF document"):
        await parser.parse_receipt(b"not a valid pdf", "receipt.pdf", "application/pdf")


@pytest.mark.anyio
async def test_openai_receipt_parser_pdf_page_limit_enforced():
    parser = OpenAIReceiptParser(api_key="sk-test", max_pdf_pages=2)
    pdf_bytes = create_blank_pdf(num_pages=3)

    with pytest.raises(ValueError, match="PDF page count exceeds maximum allowed limit of 2 pages"):
        await parser.parse_receipt(pdf_bytes, "long_receipt.pdf", "application/pdf")


@pytest.mark.anyio
async def test_openai_receipt_parser_raster_image_success():
    parser = OpenAIReceiptParser(api_key="sk-test", model="gpt-4o-mini")
    image_bytes = b"\x89PNG\r\n\x1a\nfakeimagebytes"

    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "merchant": "Home Depot",
                            "date": "2026-06-15",
                            "total_amount": 54.20,
                            "description": "Home Depot - Lumber and nails",
                        }
                    )
                }
            }
        ]
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await parser.parse_receipt(image_bytes, "receipt.png", "image/png")

        assert result.merchant == "Home Depot"
        assert result.date == datetime.date(2026, 6, 15)
        assert result.total_amount == Decimal("54.20")
        assert result.description == "Home Depot - Lumber and nails"

        assert mock_post.await_count == 1
        _, kwargs = mock_post.await_args
        payload = kwargs["json"]
        assert payload["model"] == "gpt-4o-mini"
        assert payload["response_format"]["type"] == "json_schema"

        user_content = payload["messages"][1]["content"]
        assert user_content[1]["type"] == "image_url"
        assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.anyio
async def test_openai_receipt_parser_pdf_success():
    parser = OpenAIReceiptParser(api_key="sk-test", max_pdf_pages=5)
    pdf_bytes = create_blank_pdf(num_pages=2)

    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "merchant": "Best Buy",
                            "date": "2026-07-20",
                            "total_amount": 299.99,
                            "description": "Best Buy - Monitor",
                        }
                    )
                }
            }
        ]
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await parser.parse_receipt(pdf_bytes, "invoice.pdf", "application/pdf")

        assert result.merchant == "Best Buy"
        assert result.date == datetime.date(2026, 7, 20)
        assert result.total_amount == Decimal("299.99")
        assert result.description == "Best Buy - Monitor"

        _, kwargs = mock_post.await_args
        payload = kwargs["json"]
        user_content = payload["messages"][1]["content"]
        assert user_content[1]["type"] == "file"
        assert user_content[1]["file"]["filename"] == "invoice.pdf"
        assert user_content[1]["file"]["file_data"].startswith("data:application/pdf;base64,")


@pytest.mark.anyio
async def test_openai_receipt_parser_upstream_errors():
    parser = OpenAIReceiptParser(api_key="sk-test")

    # HTTP 401 error
    err_resp = MagicMock()
    err_resp.is_error = True
    err_resp.status_code = 401
    err_resp.text = "Incorrect API key provided"

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=err_resp):
        with pytest.raises(RuntimeError, match="OpenAI API request failed \\(401\\)"):
            await parser.parse_receipt(b"data", "test.jpg", "image/jpeg")

    # Network connection failure
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(RuntimeError, match="Failed to connect to OpenAI API"):
            await parser.parse_receipt(b"data", "test.jpg", "image/jpeg")

    # Malformed content in OpenAI response
    malformed_resp = MagicMock()
    malformed_resp.is_error = False
    malformed_resp.status_code = 200
    malformed_resp.json.return_value = {"choices": []}

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=malformed_resp):
        with pytest.raises(RuntimeError, match="Malformed response received from OpenAI API"):
            await parser.parse_receipt(b"data", "test.jpg", "image/jpeg")


def test_get_receipt_parser_factory(monkeypatch):
    # Mock provider
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    parser_mock = get_receipt_parser()
    assert isinstance(parser_mock, MockReceiptParser)
    assert parser_mock.provider_id == "mock"

    # OpenAI provider
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-live-key")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-4o")
    parser_openai = get_receipt_parser()
    assert isinstance(parser_openai, OpenAIReceiptParser)
    assert parser_openai.provider_id == "openai"
    assert parser_openai.model == "gpt-4o"

    # Unsupported provider
    monkeypatch.setattr(settings, "AI_PROVIDER", "claude_anthropic")
    with pytest.raises(ValueError, match="Unsupported AI_PROVIDER: 'claude_anthropic'"):
        get_receipt_parser()
