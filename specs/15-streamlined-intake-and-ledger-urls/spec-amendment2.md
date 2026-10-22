---
status: Implemented
subsystems:
  - Staging Layer
  - Frontend UI/UX
amendments: []
supersedes: null
superseded_by: null
---

# Specification Amendment 2: Front-Loading Allocation Column Following Row Actions

**Target Specification:** [`specs/15-streamlined-intake-and-ledger-urls/spec.md`](file:///D:/src/personal/wrangler/specs/15-streamlined-intake-and-ledger-urls/spec.md)  
**Status:** Implemented  
**Subsystems:** Staging Layer & Frontend UI/UX  
**Date:** 2026-10-22  

---

## 1. Context & Motivation

In [`specs/15-streamlined-intake-and-ledger-urls/spec-amendment1.md`](file:///D:/src/personal/wrangler/specs/15-streamlined-intake-and-ledger-urls/spec-amendment1.md), the staging table triage column sequence was established as:

`[Select, URL, Actions, Date, Description, Amount, Allocation, Receipt]`

While this front-loaded the URL and primary triage actions (`[👤 Mark Personal]`, `[✏️ Edit]`), the read-only **Allocation** status badge remained positioned near the right edge of the table (between `Amount` and `Receipt`). 

This created visual discontinuity:
- The user performed triage actions on the left (in the `Actions` column), but had to look across `Date`, `Description`, and `Amount` to the right to verify the resulting allocation state badge.
- Entity attribution is a core routing concern in Wrangler (alongside order investigation and editing).

This amendment relocates the `Allocation` column to position 4, immediately following `Actions`.

---

## 2. Summary of Changes

| Column Position | Spec Amendment 1 | Spec Amendment 2 (Amended) | Purpose |
| :---: | :--- | :--- | :--- |
| **1** | `select` | `select` | Batch selection checkbox |
| **2** | `url` | `url` | External investigation link |
| **3** | `actions` | `actions` | One-click `[👤 Mark Personal]` toggle and `[✏️ Edit]` dialog trigger |
| **4** | `date` | **`allocations`** | **Entity status badge (`Personal`, `Company (100%)`, `Splits`, `Unallocated`) + readiness icon** |
| **5** | `description` | `date` | Transaction date |
| **6** | `total_amount` | `description` | Description / payee and source chip |
| **7** | `allocations` | `total_amount` | Transaction total amount |
| **8** | `receipt` | `receipt` | Receipt attachment viewer button |

---

## 3. Component & Test Updates

1. **Table Column Definition (`web/src/views/importView.ts`):**
   - Reordered `stagingTableColumns` array so that the `allocations` column definition immediately follows `actions`.
2. **Template Structure (`web/src/views/ImportView.vue`):**
   - Moved `<template #body-cell-allocations="props">` to immediately follow `<template #body-cell-actions="props">` to maintain alignment between column config and template order.
3. **Spec Verification (`web/src/views/__tests__/importView.spec.ts`):**
   - Test verifies exact column array sequence:
     `["select", "url", "actions", "allocations", "date", "description", "total_amount", "receipt"]`.
