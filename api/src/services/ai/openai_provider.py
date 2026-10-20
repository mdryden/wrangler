import base64
import datetime
import io
import json
from decimal import Decimal

import httpx
import pypdf

from .base import BaseReceiptParserProvider, ReceiptParseResult


class OpenAIReceiptParser(BaseReceiptParserProvider):
    """OpenAI multi-modal vision receipt parser using structured outputs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 60,
        max_pdf_pages: int = 10,
    ) -> None:
        if not api_key or not api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_pdf_pages = max_pdf_pages

    @property
    def provider_id(self) -> str:
        return "openai"

    async def parse_receipt(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> ReceiptParseResult:
        normalized_mime = mime_type.lower().strip()

        if normalized_mime == "application/pdf":
            try:
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                page_count = len(reader.pages)
            except Exception as exc:
                raise ValueError(f"Corrupt or unreadable PDF document: {exc}") from exc

            if page_count > self.max_pdf_pages:
                raise ValueError(f"PDF page count exceeds maximum allowed limit of {self.max_pdf_pages} pages")

            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            content_block = {
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{b64_str}",
                },
            }
        elif normalized_mime in ("image/jpeg", "image/png", "image/webp"):
            b64_str = base64.b64encode(file_bytes).decode("utf-8")
            content_block = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{normalized_mime};base64,{b64_str}",
                },
            }
        else:
            raise ValueError(f"Unsupported MIME type: {mime_type}")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Canadian/North American expense accountant. "
                    "Analyze the provided receipt document and extract the following information:\n"
                    "- merchant: Identify the clean name of the merchant or store (e.g., 'Costco Wholesale' -> 'Costco').\n"
                    "- date: Extract the transaction date formatted strictly as 'YYYY-MM-DD'.\n"
                    "- total_amount: Extract the final settled total amount charged as a decimal number.\n"
                    "- description: Concise description formatted as '{Merchant} - {Summary of items purchased}' "
                    "(e.g., 'Costco - Groceries and cleaning supplies'). Sanitize line item noise.\n"
                    "If any field cannot be determined, set it to null."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Please parse this receipt: {filename}",
                    },
                    content_block,
                ],
            },
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "receipt_extraction",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "merchant": {"type": ["string", "null"]},
                            "date": {"type": ["string", "null"], "description": "YYYY-MM-DD format"},
                            "total_amount": {"type": ["number", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                        "required": ["merchant", "date", "total_amount", "description"],
                        "additionalProperties": False,
                    },
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.is_error:
                    raise RuntimeError(f"OpenAI API request failed ({response.status_code}): {response.text}")
                data = response.json()
        except httpx.RequestError as exc:
            raise RuntimeError(f"Failed to connect to OpenAI API: {exc}") from exc
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Unexpected error communicating with OpenAI API: {exc}") from exc

        try:
            content_str = data["choices"][0]["message"]["content"]
            parsed_json = json.loads(content_str)
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError(f"Malformed response received from OpenAI API: {exc}") from exc

        try:
            return ReceiptParseResult.model_validate(parsed_json)
        except Exception:
            parsed_date = None
            if parsed_json.get("date"):
                try:
                    parsed_date = datetime.date.fromisoformat(parsed_json["date"])
                except ValueError:
                    parsed_date = None

            total_amt = None
            if parsed_json.get("total_amount") is not None:
                try:
                    total_amt = Decimal(str(parsed_json["total_amount"]))
                except Exception:
                    total_amt = None

            return ReceiptParseResult(
                merchant=parsed_json.get("merchant"),
                date=parsed_date,
                total_amount=total_amt,
                description=parsed_json.get("description"),
            )
