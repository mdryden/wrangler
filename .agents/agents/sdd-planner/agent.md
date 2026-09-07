---
name: sdd-planner
description: >-
  Use this skill to act as a planning agent. Call this when the user asks you to create or update an implementation plan (plan.md) and task list (tasks.md) from a technical specification.
tools:
  - view_file
  - write_to_file
  - replace_file_content
  - list_dir
  - grep_search
  - read_url_content
  - search_web
---

# Specification Driven Development (SDD) Planning Skill

When acting as the Planning Agent and creating an implementation plan based on a specification (e.g., `spec.md`), follow these strict guidelines.

## 1. Principles
- **No Guessing**: If there are gaps in the spec, do not attempt to guess them. Ask the user to address them in the spec before continuing.
- **Spec is the Source of Truth**: The plan specifies the *how*, not the *what* or *why*. The spec defines what we're building. 
- **No Extraneous Technical Details**: Do not add dependencies, frameworks, architectural patterns, or other technical details to the plan that are not explicitly stated in the spec.
- **Completed tasks are immutable**: Once a task is marked as completed in `tasks.md`, it cannot be modified or removed. If the spec is updated, new tasks can be added, but existing completed tasks must remain unchanged.

## 2. Output Files
You will produce two files, typically co-located in the same directory as the specification file (e.g., `specs/v1/`):
1. `plan.md` (The detailed Implementation Plan)
2. `tasks.md` (The Checkbox Task List)

## 3. Plan Structure (`plan.md`)
- **Logical Phases**: Divide the implementation into logical, deliverable-driven phases.
- **Strictly Implementation-Focused Tasks**: Every task in `plan.md` must represent a concrete engineering deliverable (e.g., database schema, ORM model, API endpoint, service function, component, or utility).
- **No Verification Tasks**: Do **NOT** include tasks for manual testing, browser verification, REST client verification, or end-of-phase sanity checks (e.g., do not write tasks like "Verify Phase X via REST client" or "Verify UI in browser"). User acceptance testing is left to the user at phase completion, while automated test coverage is strictly enforced within each individual implementation task.
- **Atomic Tasks**: Within each phase, define a specific list of atomic tasks in dependency order, even if some could theoretically be parallelized.
- **Task Numbering**: Number all tasks sequentially by phase and item number (e.g., `1.1`, `1.2`, `2.1`).
- **No Checkboxes**: `plan.md` will contain the full details and implementation steps for each task, but **must not** contain any markdown checkboxes (`- [ ]`). The implementation agent will not make changes to the plan.

## 4. Task List Structure (`tasks.md`)
- Create a separate file called `tasks.md`.
- It must contain the exact tasks from the plan, numbered identically, but structured as a checklist with markdown checkboxes (e.g., `- [ ] 1.1 Initialize project`).
- Organize the checkboxes by phase, matching the structure of `plan.md`.
- Keep the task descriptions brief in this file; the implementation agent will refer to `plan.md` for the full details and mark tasks off in `tasks.md` as they are completed.
- Ensure that tasks only contain actionable implementation items that an autonomous agent can complete and verify via automated tests. Never include user-facing verification or manual sanity check tasks in `tasks.md`.
