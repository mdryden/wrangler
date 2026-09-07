import { describe, it, expect } from "vitest"
import { formatCurrency, getAllocationBadgeInfo, getAllocationLabel, getSingleAllocationCompany } from "../src/views/ledger"
import type { Company } from "../src/types/company"
import type { Transaction } from "../src/types/transaction"

describe("Ledger Allocations Display & Currency Formatting (ledger.ts)", () => {
  const sampleCompanies: Company[] = [
    { id: "comp-1", name: "Alpha Consulting LLC" },
    { id: "comp-2", name: "Beta Ventures" },
  ]

  const companyMap = new Map([
    ["comp-1", "Alpha Consulting LLC"],
    ["comp-2", "Beta Ventures"],
  ])

  describe("getAllocationLabel", () => {
    it("displays the company name when transaction is single-allocated to a known company", () => {
      const tx: Transaction = {
        id: "tx-1",
        source: "manual",
        external_id: null,
        date: "2026-09-01",
        description: "Software Subscription",
        total_amount: "50.00",
        currency_code: "USD",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-1",
            transaction_id: "tx-1",
            amount: "50.00",
            is_personal: false,
            company_id: "comp-1",
            sync_status: "PENDING",
          },
        ],
      }

      // Test with Company[] array
      expect(getAllocationLabel(tx, sampleCompanies)).toBe("Alpha Consulting LLC")
      expect(getAllocationBadgeInfo(tx, sampleCompanies)).toBe("Alpha Consulting LLC")
      expect(getSingleAllocationCompany(tx, sampleCompanies)).toBe("Alpha Consulting LLC")

      // Test with Map<string, string>
      expect(getAllocationLabel(tx, companyMap)).toBe("Alpha Consulting LLC")
      expect(getSingleAllocationCompany(tx, companyMap)).toBe("Alpha Consulting LLC")
    })

    it("falls back to '1 splits' when single-allocated to an unknown company ID", () => {
      const tx: Transaction = {
        id: "tx-2",
        source: "manual",
        external_id: null,
        date: "2026-09-02",
        description: "Office Supplies",
        total_amount: "30.00",
        currency_code: "USD",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-2",
            transaction_id: "tx-2",
            amount: "30.00",
            is_personal: false,
            company_id: "comp-unknown",
            sync_status: "PENDING",
          },
        ],
      }

      expect(getAllocationLabel(tx, sampleCompanies)).toBe("1 splits")
      expect(getSingleAllocationCompany(tx, sampleCompanies)).toBeNull()
    })

    it("displays 'Personal' when single-allocated to personal expense", () => {
      const tx: Transaction = {
        id: "tx-3",
        source: "bank",
        external_id: null,
        date: "2026-09-03",
        description: "Groceries",
        total_amount: "75.20",
        currency_code: "USD",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-3",
            transaction_id: "tx-3",
            amount: "75.20",
            is_personal: true,
            company_id: null,
            sync_status: "PENDING",
          },
        ],
      }

      expect(getAllocationLabel(tx, sampleCompanies)).toBe("Personal")
      expect(getSingleAllocationCompany(tx, sampleCompanies)).toBeNull()
    })

    it("displays 'X splits' when transaction has multiple allocations", () => {
      const tx: Transaction = {
        id: "tx-4",
        source: "manual",
        external_id: null,
        date: "2026-09-04",
        description: "Shared Cloud Hosting",
        total_amount: "100.00",
        currency_code: "USD",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-4a",
            transaction_id: "tx-4",
            amount: "60.00",
            is_personal: false,
            company_id: "comp-1",
            sync_status: "PENDING",
          },
          {
            id: "alloc-4b",
            transaction_id: "tx-4",
            amount: "40.00",
            is_personal: false,
            company_id: "comp-2",
            sync_status: "PENDING",
          },
        ],
      }

      expect(getAllocationLabel(tx, sampleCompanies)).toBe("2 splits")
      expect(getSingleAllocationCompany(tx, sampleCompanies)).toBeNull()
    })

    it("displays '0 splits' when transaction has empty or undefined allocations", () => {
      const txEmpty: Transaction = {
        id: "tx-5",
        source: "manual",
        external_id: null,
        date: "2026-09-05",
        description: "Unallocated",
        total_amount: "10.00",
        currency_code: "USD",
        receipt_file_path: null,
        allocations: [],
      }

      expect(getAllocationLabel(txEmpty, sampleCompanies)).toBe("0 splits")
      expect(getAllocationLabel(null, sampleCompanies)).toBe("0 splits")
      expect(getAllocationLabel(undefined, sampleCompanies)).toBe("0 splits")
    })

    it("accepts an array of Allocation objects directly", () => {
      const allocations = [
        {
          id: "alloc-6",
          transaction_id: "tx-6",
          amount: "120.00",
          is_personal: false,
          company_id: "comp-2",
          sync_status: "PENDING" as const,
        },
      ]

      expect(getAllocationLabel(allocations, sampleCompanies)).toBe("Beta Ventures")
    })
  })

  describe("formatCurrency", () => {
    it("formats standard amounts with currency symbols", () => {
      expect(formatCurrency(45.99)).toBe("$45.99")
      expect(formatCurrency("1250.50")).toBe("$1,250.50")
      expect(formatCurrency("0")).toBe("$0.00")
      expect(formatCurrency(0)).toBe("$0.00")
    })

    it("formats negative amounts", () => {
      expect(formatCurrency(-25.5)).toBe("-$25.50")
      expect(formatCurrency("-50.00")).toBe("-$50.00")
    })

    it("handles invalid number values gracefully", () => {
      expect(formatCurrency("invalid")).toBe("$0.00")
      expect(formatCurrency("")).toBe("$0.00")
    })
  })
})
