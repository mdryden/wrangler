import type { QTableColumn } from "quasar"
import type { StagedTransaction } from "../types/staging"

/**
 * Formats a staged amount or string into simplified currency format without redundant 'CA$' prefix for CAD.
 */
export function formatStagedAmount(amount: string | number | null | undefined, currencyCode = "CAD"): string {
  if (amount === null || amount === undefined || amount === "") {
    return "$0.00"
  }
  const num = typeof amount === "string" ? parseFloat(amount) : amount
  if (Number.isNaN(num)) {
    return "$0.00"
  }
  const isNegative = num < 0
  const absFormatted = Math.abs(num).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  const sign = isNegative ? "-" : ""
  const code = (currencyCode || "CAD").toUpperCase()

  if (code === "CAD") {
    return `${sign}$${absFormatted}`
  }
  return `${sign}${code} ${absFormatted}`
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
