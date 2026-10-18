import uuid
from datetime import datetime
from decimal import Decimal

try:
    from mcp.server.fastmcp import FastMCP
except ImportError, ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP

from database import SessionLocal
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction

mcp = FastMCP("Wrangler")


def _normalize_description(source_label: str, description: str) -> str:
    cleaned = description.strip()
    # Email-style labels (e.g. "receipts@mmjm.ca") are used exactly as written; plain names are title-cased.
    prefix = f"[{source_label}]" if "@" in source_label else f"[{source_label.title()}]"
    if cleaned.startswith(prefix):
        if cleaned.startswith(f"{prefix} "):
            return cleaned
        after = cleaned[len(prefix) :].lstrip()
        return f"{prefix} {after}" if after else prefix

    if cleaned.lower().startswith(f"[{source_label}]".lower()):
        parts = cleaned.split("]", 1)
        after = parts[1].lstrip() if len(parts) > 1 else ""
        return f"{prefix} {after}" if after else prefix

    return f"{prefix} {cleaned}" if cleaned else prefix


@mcp.tool()
async def stage_transaction(
    source_label: str,
    external_id: str,
    date: str | None = None,
    total_amount: float | None = None,
    description: str | None = None,
    currency_code: str | None = None,
) -> str:
    """Stage a transaction in Wrangler for user review and allocation.

    Any value that cannot be determined should be passed as null (never guessed); the user completes it in Wrangler.

    Args:
        source_label: Intake source identifier (e.g., 'amazon', 'receipts@mmjm.ca'). Required.
        external_id: Unique order ID or transaction reference from the merchant. Required.
        date: Transaction date in ISO format (YYYY-MM-DD or ISO timestamp), or null if unknown.
        total_amount: Non-zero float; positive for purchases, negative for returns/refunds, or null if unknown.
        description: Item title, summary, or vendor notes, or null if unknown.
        currency_code: Three-letter ISO currency code, or null (defaults to 'CAD').

    Returns:
        A human-readable confirmation string detailing whether the transaction was staged
        or skipped as a duplicate.
    """
    norm_source_label = (source_label or "").strip().lower()
    if not norm_source_label:
        raise ValueError("source_label cannot be empty")

    norm_external_id = (external_id or "").strip()
    if not norm_external_id:
        raise ValueError("external_id cannot be empty")

    namespaced_external_id = f"{norm_source_label}:{norm_external_id}"

    cleaned_currency = (currency_code or "CAD").strip().upper()
    if not cleaned_currency:
        cleaned_currency = "CAD"

    amount_decimal: Decimal | None = None
    if total_amount is not None:
        amount_decimal = Decimal(f"{total_amount:.2f}")
        if amount_decimal == Decimal("0.00"):
            raise ValueError("total_amount cannot be zero")

    parsed_date = None
    cleaned_date = (date or "").strip()
    if cleaned_date:
        try:
            parsed_date = datetime.fromisoformat(cleaned_date.replace("Z", "+00:00")).date()
        except Exception as exc:
            raise ValueError(f"Invalid date format: {date}") from exc

    formatted_description: str | None = None
    if description is not None and description.strip():
        formatted_description = _normalize_description(norm_source_label, description)

    missing: list[str] = []
    if parsed_date is None:
        missing.append("date")
    if amount_decimal is None:
        missing.append("total_amount")
    if formatted_description is None:
        missing.append("description")

    session = SessionLocal()
    try:
        # Check StagedTransaction
        staged_tx = (
            session.query(StagedTransaction)
            .filter(
                StagedTransaction.source == "mcp",
                StagedTransaction.external_id == namespaced_external_id,
            )
            .first()
        )
        if staged_tx:
            return f"Transaction '[mcp] {namespaced_external_id}' already exists in Wrangler (status: {staged_tx.status}). Skipped."

        # Check Transaction
        ledger_tx = (
            session.query(Transaction)
            .filter(
                Transaction.source == "mcp",
                Transaction.external_id == namespaced_external_id,
            )
            .first()
        )
        if ledger_tx:
            return f"Transaction '[mcp] {namespaced_external_id}' already exists in Wrangler (status: LEDGER). Skipped."

        # Insert new StagedTransaction
        new_staged = StagedTransaction(
            id=uuid.uuid4(),
            source="mcp",
            external_id=namespaced_external_id,
            date=parsed_date,
            description=formatted_description,
            total_amount=amount_decimal,
            currency_code=cleaned_currency,
            status="STAGED",
            is_marked_imported=False,
            receipt_file_path=None,
        )
        session.add(new_staged)
        session.commit()

        if missing:
            desc_display = formatted_description if formatted_description is not None else "[unnamed]"
            amt_display = f"(${amount_decimal:.2f} {cleaned_currency})" if amount_decimal is not None else "(amount pending)"
            return (
                f"Successfully staged transaction: [mcp] {namespaced_external_id} - {desc_display} {amt_display}. "
                f"Needs review in Wrangler: {', '.join(missing)}."
            )
        return f"Successfully staged transaction: [mcp] {namespaced_external_id} - {formatted_description} (${amount_decimal:.2f} {cleaned_currency})."
    finally:
        session.close()


@mcp.tool()
async def check_transaction_exists(
    source_label: str,
    external_id: str,
) -> dict:
    """Check if a transaction with the given source label and external ID already exists in Wrangler.

    Args:
        source_label: Merchant identifier (e.g., 'amazon').
        external_id: Raw order ID or reference number.

    Returns:
        A dictionary containing:
        - exists (bool): True if present in staging or ledger.
        - location (str | None): 'staged' or 'ledger' if found.
        - status (str | None): 'STAGED', 'ACCEPTED', 'DISMISSED', or 'COMMITTED'.
    """
    norm_source_label = (source_label or "").strip().lower()
    norm_external_id = (external_id or "").strip()

    if not norm_source_label or not norm_external_id:
        return {"exists": False, "location": None, "status": None}

    namespaced_external_id = f"{norm_source_label}:{norm_external_id}"

    session = SessionLocal()
    try:
        staged_tx = (
            session.query(StagedTransaction)
            .filter(
                StagedTransaction.source == "mcp",
                StagedTransaction.external_id == namespaced_external_id,
            )
            .first()
        )
        if staged_tx:
            return {
                "exists": True,
                "location": "staged",
                "status": staged_tx.status,
            }

        ledger_tx = (
            session.query(Transaction)
            .filter(
                Transaction.source == "mcp",
                Transaction.external_id == namespaced_external_id,
            )
            .first()
        )
        if ledger_tx:
            return {
                "exists": True,
                "location": "ledger",
                "status": "COMMITTED",
            }

        return {
            "exists": False,
            "location": None,
            "status": None,
        }
    finally:
        session.close()
