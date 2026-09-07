import csv
import io
import uuid
from collections.abc import Sequence

from models.allocation import Allocation


def generate_wave_csv(
    allocations: Sequence[Allocation],
    company_id: uuid.UUID | None = None,
) -> str:
    """
    Generate an RFC 4180 compliant CSV string formatted for Wave transaction imports.

    Header: Date,Description,Amount
    - Date: ISO 8601 (YYYY-MM-DD) from parent Transaction.date
    - Description: Parent Transaction.description (properly escaped per RFC 4180)
    - Amount: Two decimal places with leading minus sign for negative amounts/refunds
    - Excludes personal allocations (is_personal == True) and non-matching company allocations
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["Date", "Description", "Amount"])

    for alloc in allocations:
        if alloc.is_personal:
            continue
        if company_id is not None and alloc.company_id != company_id:
            continue

        date_str = alloc.transaction.date.isoformat()
        description_str = alloc.transaction.description
        amount_str = f"{alloc.amount:.2f}"

        writer.writerow([date_str, description_str, amount_str])

    return output.getvalue()
