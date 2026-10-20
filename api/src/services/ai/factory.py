from core.config import settings

from .base import BaseReceiptParserProvider
from .mock_provider import MockReceiptParser
from .openai_provider import OpenAIReceiptParser


def get_receipt_parser() -> BaseReceiptParserProvider:
    """Factory function to resolve and instantiate configured AI receipt parser."""
    provider = settings.AI_PROVIDER.lower().strip()
    if provider == "openai":
        return OpenAIReceiptParser(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            base_url=settings.OPENAI_BASE_URL,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
            max_pdf_pages=settings.AI_MAX_PDF_PAGES,
        )
    elif provider == "mock":
        return MockReceiptParser()
    else:
        raise ValueError(f"Unsupported AI_PROVIDER: '{provider}'")
