import fs from "fs"
import path from "path"
import { describe, it, expect } from "vitest"
import {
  canDeleteTransaction,
  DELETE_LOCKED_TOOLTIP,
  formatCurrency,
  getAllocationBadgeInfo,
  getAllocationItemLabel,
  getAllocationLabel,
  getSingleAllocationCompany,
  getTextWeightClass,
  getTransactionLockBadge,
  getTransactionLockStatus,
  hasLockedAllocations,
  isTransactionFullyLocked,
  isTransactionPartiallyLocked,
  UNLOCK_WARNING_MESSAGE,
} from "../src/views/ledger"
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
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-1",
            transaction_id: "tx-1",
            amount: "50.00",
            is_personal: false,
            company_id: "comp-1",
            is_locked: false,
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
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-2",
            transaction_id: "tx-2",
            amount: "30.00",
            is_personal: false,
            company_id: "comp-unknown",
            is_locked: false,
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
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-3",
            transaction_id: "tx-3",
            amount: "75.20",
            is_personal: true,
            company_id: null,
            is_locked: false,
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
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-4a",
            transaction_id: "tx-4",
            amount: "60.00",
            is_personal: false,
            company_id: "comp-1",
            is_locked: false,
          },
          {
            id: "alloc-4b",
            transaction_id: "tx-4",
            amount: "40.00",
            is_personal: false,
            company_id: "comp-2",
            is_locked: false,
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
          is_locked: false,
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
      expect(formatCurrency(null)).toBe("$0.00")
      expect(formatCurrency(undefined)).toBe("$0.00")
    })
  })

  describe("Visual Lock Indicators & Row Action Guards (Task 16.3)", () => {
    const unlockedTx: Transaction = {
      id: "tx-u1",
      source: "manual",
      external_id: null,
      date: "2026-09-10",
      description: "Unlocked Transaction",
      total_amount: "45.00",
      receipt_file_path: "tx-u1.pdf",
      allocations: [
        {
          id: "alloc-u1",
          transaction_id: "tx-u1",
          amount: "45.00",
          is_personal: false,
          company_id: "comp-1",
          is_locked: false,
        },
      ],
    }

    const partiallyLockedTx: Transaction = {
      id: "tx-p1",
      source: "manual",
      external_id: null,
      date: "2026-09-11",
      description: "Partially Locked Transaction",
      total_amount: "100.00",
      receipt_file_path: null,
      allocations: [
        {
          id: "alloc-p1",
          transaction_id: "tx-p1",
          amount: "60.00",
          is_personal: false,
          company_id: "comp-1",
          is_locked: true,
        },
        {
          id: "alloc-p2",
          transaction_id: "tx-p1",
          amount: "40.00",
          is_personal: false,
          company_id: "comp-2",
          is_locked: false,
        },
      ],
    }

    const fullyLockedTx: Transaction = {
      id: "tx-f1",
      source: "manual",
      external_id: null,
      date: "2026-09-12",
      description: "Fully Locked Transaction",
      total_amount: "80.00",
      receipt_file_path: "tx-f1.pdf",
      allocations: [
        {
          id: "alloc-f1",
          transaction_id: "tx-f1",
          amount: "80.00",
          is_personal: false,
          company_id: "comp-1",
          is_locked: true,
        },
      ],
    }

    it("accurately classifies unlocked, partially locked, and fully locked transactions", () => {
      expect(getTransactionLockStatus(unlockedTx)).toBe("unlocked")
      expect(isTransactionFullyLocked(unlockedTx)).toBe(false)
      expect(isTransactionPartiallyLocked(unlockedTx)).toBe(false)
      expect(hasLockedAllocations(unlockedTx)).toBe(false)

      expect(getTransactionLockStatus(partiallyLockedTx)).toBe("partially_locked")
      expect(isTransactionFullyLocked(partiallyLockedTx)).toBe(false)
      expect(isTransactionPartiallyLocked(partiallyLockedTx)).toBe(true)
      expect(hasLockedAllocations(partiallyLockedTx)).toBe(true)

      expect(getTransactionLockStatus(fullyLockedTx)).toBe("fully_locked")
      expect(isTransactionFullyLocked(fullyLockedTx)).toBe(true)
      expect(isTransactionPartiallyLocked(fullyLockedTx)).toBe(false)
      expect(hasLockedAllocations(fullyLockedTx)).toBe(true)

      // Empty or null allocations default to unlocked
      expect(getTransactionLockStatus([])).toBe("unlocked")
      expect(getTransactionLockStatus(null)).toBe("unlocked")
    })

    it("returns appropriate lock badge metadata for each lock status", () => {
      expect(getTransactionLockBadge(unlockedTx)).toEqual({
        status: "unlocked",
        label: "Unlocked",
        icon: "lock_open",
        color: "grey-6",
      })
      expect(getTransactionLockBadge(partiallyLockedTx)).toEqual({
        status: "partially_locked",
        label: "Partially Locked",
        icon: "lock_open",
        color: "orange-7",
      })
      expect(getTransactionLockBadge(fullyLockedTx)).toEqual({
        status: "fully_locked",
        label: "Locked",
        icon: "lock",
        color: "amber-9",
      })
    })

    it("disables deletion when any allocation on the transaction is locked", () => {
      expect(canDeleteTransaction(unlockedTx)).toBe(true)
      expect(canDeleteTransaction(partiallyLockedTx)).toBe(false)
      expect(canDeleteTransaction(fullyLockedTx)).toBe(false)
      expect(DELETE_LOCKED_TOOLTIP).toContain("Unlock")
    })

    it("exposes the required external accounting system unlock warning message", () => {
      expect(UNLOCK_WARNING_MESSAGE).toBe(
        "If this transaction has already been imported into an external accounting system, you must also adjust or remove it there manually.",
      )
    })

    it("resolves individual allocation labels for per-split lock menu", () => {
      expect(getAllocationItemLabel(partiallyLockedTx.allocations[0], companyMap)).toBe("Alpha Consulting LLC")
      expect(getAllocationItemLabel(partiallyLockedTx.allocations[1], sampleCompanies)).toBe("Beta Ventures")
      expect(
        getAllocationItemLabel(
          {
            id: "alloc-pers",
            transaction_id: "tx-1",
            amount: "10.00",
            is_personal: true,
            company_id: null,
            is_locked: false,
          },
          companyMap,
        ),
      ).toBe("Personal")
      expect(getAllocationItemLabel(null, companyMap)).toBe("Unassigned")
    })

    it("resolves dynamic font weight class: text-weight-regular when locked, text-weight-bold when unlocked", () => {
      // Locked transactions should render with normal font weight
      expect(getTextWeightClass(fullyLockedTx)).toBe("text-weight-regular")

      // Unlocked transactions should render with bold font weight to emphasize unsynced items
      expect(getTextWeightClass(unlockedTx)).toBe("text-weight-bold")
      expect(getTextWeightClass(partiallyLockedTx)).toBe("text-weight-bold")
      expect(getTextWeightClass(null)).toBe("text-weight-bold")
      expect(getTextWeightClass([])).toBe("text-weight-bold")
    })
  })

  describe("LedgerView Component Column Layout & Lock Status (LedgerView.vue)", () => {
    const viewPath = path.resolve(__dirname, "../src/views/LedgerView.vue")
    const viewContent = fs.readFileSync(viewPath, "utf-8")

    it("includes an unlabeled lock column in the first position to preserve date alignment", () => {
      // First column definition should be the unlabeled lock column
      const columnsBlock = viewContent.match(/const columns = computed<QTableColumn\[\]>\(\(\) => (\[[\s\S]*?\])\)/)
      expect(columnsBlock).not.toBeNull()
      expect(columnsBlock![1]).toMatch(/\{\s*name:\s*"lock",\s*label:\s*"",\s*align:\s*"center"/)

      // Template should define lock slot templates
      expect(viewContent).toContain('<template #header-cell-lock="props">')
      expect(viewContent).toContain('<template #body-cell-lock="props">')
      expect(viewContent).toContain('data-testid="icon-row-fully-locked"')
      expect(viewContent).toContain('data-testid="icon-row-partially-locked"')
    })

    it("renders date column without internal lock icons to maintain vertical alignment", () => {
      const dateTemplateMatch = viewContent.match(/<!-- Date Column -->[\s\S]*?<template #body-cell-date="props">([\s\S]*?)<\/template>/)
      expect(dateTemplateMatch).not.toBeNull()
      const dateSlot = dateTemplateMatch![1]
      expect(dateSlot).not.toContain("icon-row-fully-locked")
      expect(dateSlot).not.toContain("icon-row-partially-locked")
      expect(dateSlot).toContain("getTextWeightClass(props.row)")
      expect(dateSlot).toContain("props.row.date")
    })

    it("applies dynamic font weight across column cells", () => {
      expect(viewContent).toContain('<span :class="getTextWeightClass(props.row)">{{ props.row.description }}</span>')
      expect(viewContent).toContain("getTextWeightClass(props.row)")
      expect(viewContent).toContain("getTextWeightClass")
    })

    it("renders external link button in description cell when row has url", () => {
      expect(viewContent).toContain('data-testid="btn-ledger-open-url"')
      expect(viewContent).toContain('v-if="props.row.url"')
      expect(viewContent).toContain(':href="props.row.url"')
      expect(viewContent).toContain('target="_blank"')
      expect(viewContent).toContain('rel="noopener noreferrer"')
      expect(viewContent).toContain("<q-tooltip>Open Source URL</q-tooltip>")
    })
  })
})
