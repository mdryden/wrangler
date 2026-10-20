import type { QTableColumn } from "quasar"
import type { StagedTransaction } from "../types/staging"
import { formatCurrency } from "./ledger"

/**
 * Formats a staged amount or string into standard CAD currency format ($X,XXX.XX or -$X,XXX.XX).
 */
export function formatStagedAmount(amount: string | number | null | undefined): string {
  return formatCurrency(amount)
}

export const stagingTableColumns: QTableColumn[] = [
  {
    name: "select",
    label: "",
    align: "center",
    field: (row: StagedTransaction) => row.id,
    sortable: false,
    style: "width: 48px",
    headerStyle: "width: 48px",
  },
  {
    name: "date",
    required: true,
    label: "Date",
    align: "left",
    field: (row: StagedTransaction) => row.date,
    sortable: false,
    style: "width: 95px",
    headerStyle: "width: 95px",
  },
  {
    name: "description",
    required: true,
    label: "Description",
    align: "left",
    field: (row: StagedTransaction) => row.description,
    sortable: false,
    style: "min-width: 280px",
    headerStyle: "min-width: 280px",
  },
  {
    name: "total_amount",
    required: true,
    label: "Amount",
    align: "right",
    field: (row: StagedTransaction) => row.total_amount,
    sortable: false,
    style: "width: 95px",
    headerStyle: "width: 95px",
  },
  {
    name: "allocations",
    label: "Allocation Status / Summary",
    align: "left",
    field: (row: StagedTransaction) => row.id,
    sortable: false,
    style: "width: 260px",
    headerStyle: "width: 260px",
  },
  {
    name: "receipt",
    label: "Receipt",
    align: "center",
    field: (row: StagedTransaction) => (row.receipt_file_path ? "Yes" : "No"),
    sortable: false,
    style: "width: 80px",
    headerStyle: "width: 80px",
  },
  {
    name: "actions",
    label: "Actions",
    align: "right",
    field: () => "",
    sortable: false,
    style: "width: 80px",
    headerStyle: "width: 80px",
  },
]

/**
 * Determines whether the importer summary notification should be a warning
 * (when files failed or duplicates were skipped) or positive success.
 */
export function getImportNotificationType(result: { failed_files?: string[]; skipped_duplicates: number }): "warning" | "positive" {
  if ((result.failed_files && result.failed_files.length > 0) || result.skipped_duplicates > 0) {
    return "warning"
  }
  return "positive"
}
