from datetime import date
from decimal import Decimal

from .base import ImportedTransactionData, ImporterInputType
from .csv_base import BaseCsvImporter


class AmazonCsvImporter(BaseCsvImporter):
    """Intake adapter for Amazon order history and refund CSV exports."""

    importer_id: str = "amazon_csv"
    source_name: str = "amazon_csv"
    display_name: str = "Amazon Transactions CSV"
    description: str = "Imports Amazon orders and refunds from an exported Amazon transactions CSV file."
    input_type: ImporterInputType = ImporterInputType.FILE
    accepted_file_types: list[str] = [".csv"]
    supports_mark_imported: bool = False
    REQUIRED_COLUMNS: tuple[str, ...] = (
        "date",
        "order ids",
        "order urls",
        "vendor",
        "card_details",
        "amount",
    )
    SKIP_ZERO_AMOUNT_ROWS: bool = False

    def parse_row(self, row: dict[str, str], row_number: int) -> ImportedTransactionData | None:
        raw_date = row.get("date", "").strip()
        raw_order_id = row.get("order ids", "").strip()

        # Duplicate Header Row Detection
        if raw_date.lower() == "date" or raw_order_id.lower() == "order ids":
            return None

        # Date Parsing
        tx_date: date | None = None
        if raw_date:
            try:
                tx_date = self.parse_iso_or_common_date(raw_date)
            except ValueError:
                tx_date = None

        # Description: Amazon transactions CSV leaves description blank for user review
        description: str | None = None

        # Amount Parsing & Sign Inversion: charges (-) become positive (+), refunds (+) become negative (-)
        raw_amount = row.get("amount", "").strip()
        total_amount: Decimal | None = None
        if raw_amount:
            try:
                parsed_amount = self.parse_amount(raw_amount)
                if parsed_amount == Decimal("0"):
                    total_amount = None
                else:
                    total_amount = (-parsed_amount).quantize(Decimal("0.01"))
            except ValueError:
                total_amount = None

        # External ID: Composite key formed from order ID, date, and amount
        if raw_order_id:
            date_str = tx_date.isoformat() if tx_date is not None else "nodate"
            amount_str = str(total_amount) if total_amount is not None else "noamount"
            external_id: str | None = f"{raw_order_id}_{date_str}_{amount_str}"
        else:
            external_id = None

        return ImportedTransactionData(
            external_id=external_id,
            date=tx_date,
            description=description,
            total_amount=total_amount,
            currency_code="CAD",
            receipt=None,
        )
