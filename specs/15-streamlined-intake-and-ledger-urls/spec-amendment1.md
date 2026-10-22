---
status: Implemented
subsystems:
  - Staging Layer
  - Frontend UI/UX
amendments: []
supersedes: null
superseded_by: null
---

# Specification Amendment 1: Front-Loaded Staging Triage Layout & One-Click Personal Allocation

**Target Specification:** [`specs/15-streamlined-intake-and-ledger-urls/spec.md`](file:///D:/src/personal/wrangler/specs/15-streamlined-intake-and-ledger-urls/spec.md)  
**Status:** Implemented  
**Subsystems:** Staging Layer & Frontend UI/UX  
**Date:** 2026-10-22  

---

## 1. Context & Motivation

In Section 5.1 of [`specs/15-streamlined-intake-and-ledger-urls/spec.md`](file:///D:/src/personal/wrangler/specs/15-streamlined-intake-and-ledger-urls/spec.md#L232-L253), the staging review table interaction model relied on:
1. An inline `<q-select>` quick-allocate dropdown embedded in each table row.
2. An external investigation URL link nested inside the Description column (which sat to the right of the allocation selector).
3. An in-row Dismiss action button positioned directly adjacent to the Edit button in the table actions column.
4. An interactive paperclip icon button in the Receipt column that triggered the edit dialog.

During real-world triage of high-volume Amazon intake streams, this design exhibited ergonomic friction:
- **Right-to-Left Backtracking:** Because Amazon imports lack initial descriptions, users had to scan right to the Description column to click the order URL, determine what was purchased in a browser tab, and then navigate back left to select "Personal" from the dropdown.
- **Heavy Inline Data Entry:** The `<q-select>` dropdown required multiple clicks (open dropdown, find/scroll, click) for what is overwhelmingly a single binary decision for unlabelled Amazon orders (Personal). Meanwhile, company allocations strictly require a description and receipt under backend invariants anyway, meaning company transactions cannot be finalized via the inline dropdown alone.
- **Accidental Dismissal Hazard:** The in-row Dismiss button sat 4px away from the Edit button with no confirmation prompt, posing a severe misclick risk.
- **Redundant Affordances:** The paperclip icon in the Receipt column simply opened the edit dialog, adding visual noise to rows with no receipts attached.

This amendment defines the architectural changes that convert the staging table into a fast, front-loaded left-to-right triage workstation.

---

## 2. Summary of Architectural & UI Changes

| Area | Prior Architecture (Spec 15) | Amended Architecture (Amendment 1) |
| :--- | :--- | :--- |
| **Column Order** | `[Select, Date, Allocations, Description, Amount, Receipt, Actions]` | `[Select, URL, Actions, Date, Description, Amount, Allocation, Receipt]` |
| **External URL Link** | Icon button nested in Description column next to source chip. | Dedicated, centered, 44px column placed immediately after the selection checkbox. |
| **Personal Allocation** | Multi-click `<q-select>` quick-assign dropdown. | One-click `[👤 Mark Personal]` toggle button in the Actions column. |
| **Row Actions Cluster** | Edit, Dismiss, Restore located on far right edge of table. | Focused `[👤 Mark Personal] [✏️ Edit]` cluster at position 3; `[🔄 Restore]` for dismissed rows. |
| **Dismissal Workflow** | Unconfirmed in-row click directly adjacent to Edit button. | Handled safely via selection checkbox + batch toolbar `Dismiss (X)` with modal confirmation. |
| **Allocation Display** | Full interactive `<q-select>` with split button. | Compact, read-only status badge (`Personal`, `Company (100%)`, `Splits`, `Unallocated`) with readiness checkmark. Click opens edit dialog. |
| **Receipt Column** | View receipt button when present; paperclip attach button when absent. | Streamlined: primary view button when present; subtle dash (`—`) when absent. |
| **Row Double-Click** | Set active row state only. | Opens Staged Transaction Edit Dialog (`@row-dblclick="(_evt, row) => openEditDialog(row)"`). |

---

## 3. Detailed Component Specifications

### 3.1 Staging Review Table Columns (`web/src/views/importView.ts`)

The `stagingTableColumns` definition is updated to:

```typescript
export const stagingTableColumns: QTableColumn[] = [
  { name: "select", label: "", align: "center", field: (row: StagedTransaction) => row.id, sortable: false, style: "width: 48px", headerStyle: "width: 48px" },
  { name: "url", label: "", align: "center", field: (row: StagedTransaction) => row.url ?? "", sortable: false, style: "width: 44px", headerStyle: "width: 44px" },
  { name: "actions", label: "Actions", align: "left", field: () => "", sortable: false, style: "width: 80px", headerStyle: "width: 80px" },
  { name: "date", required: true, label: "Date", align: "left", field: (row: StagedTransaction) => row.date, sortable: false, style: "width: 95px", headerStyle: "width: 95px" },
  { name: "description", required: true, label: "Description", align: "left", field: (row: StagedTransaction) => row.description, sortable: false, style: "min-width: 240px", headerStyle: "min-width: 240px" },
  { name: "total_amount", required: true, label: "Amount", align: "right", field: (row: StagedTransaction) => row.total_amount, sortable: false, style: "width: 95px", headerStyle: "width: 95px" },
  { name: "allocations", label: "Allocation", align: "left", field: (row: StagedTransaction) => row.id, sortable: false, style: "width: 150px", headerStyle: "width: 150px" },
  { name: "receipt", label: "Receipt", align: "center", field: (row: StagedTransaction) => (row.receipt_file_path ? "Yes" : "No"), sortable: false, style: "width: 80px", headerStyle: "width: 80px" },
]
```

### 3.2 Triage Interaction Flow (`web/src/views/ImportView.vue`)

1. **Left-to-Right Review Loop:**
   - **Step 1:** User reviews incoming row (or selects checkbox for batch actions).
   - **Step 2:** User clicks the `open_in_new` button in the dedicated **URL** column to inspect the order details in an external tab.
   - **Step 3 (Personal):** If identified as personal, the user clicks the adjacent **`[👤 Mark Personal]`** button. The transaction updates to 100% Personal, turns `is_ready = true`, and reflects the green checkmark badge.
   - **Step 4 (Company):** If identified as a company expense, the user clicks the adjacent **`[✏️ Edit]`** button (or double-clicks the row). In the dialog, the user sets the company, provides the mandatory business description, and attaches the receipt.
   - **Step 5:** Move down to the next row without visual jumping across screen boundaries.
2. **Safe Dismissal Flow:**
   - To dismiss unneeded or duplicate staged transactions, the user checks the row checkbox and clicks the **`Dismiss (X)`** button in the batch toolbar.
   - An explicit confirmation modal prompts: `"Are you sure you want to dismiss N staged transaction(s)?"` before performing the action.
3. **Receipt Viewer:**
   - The Receipt column solely serves as a viewer for durable attachments. Rows with attached files render the primary `receipt` icon button opening the file in a new tab; unreceipted rows render a dash (`—`).

---

## 4. Verification & Validation

1. **DOM Structure & Test Suite (`web/src/views/__tests__/importView.spec.ts`):**
   - Asserts column sequence: `["select", "url", "actions", "date", "description", "total_amount", "allocations", "receipt"]`.
   - Verifies `btn-mark-personal-` and `btn-action-edit` are present in row actions.
   - Asserts `btn-action-dismiss` is absent from table cells, while `btn-dismiss-selected` is present in the toolbar.
   - Verifies `isRowPersonal` helper correctly identifies 100% personal allocations.
   - Verifies double-click affordance on table rows.
2. **Monorepo Linting & Formatting:**
   - `pnpm lint` and `pnpm format` pass with zero regressions.
