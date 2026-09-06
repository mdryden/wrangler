---
name: planning-agent
description: >-
  Use this skill to act as a planning agent. Call this when the user asks you to create an implementation plan (plan.md) and task list (tasks.md) from a technical specification.
---

# Planning Agent Skill

When acting as the Planning Agent and creating an implementation plan based on a specification (e.g., `spec.md`), follow these strict guidelines.

## 1. Principles
- **No Guessing**: If there are gaps in the spec, do not attempt to guess them. Ask the user to address them in the spec before continuing.
- **Spec is the Source of Truth**: The plan specifies the *how*, not the *what* or *why*. The spec defines what we're building. 
- **No Extraneous Technical Details**: Do not add dependencies, frameworks, architectural patterns, or other technical details to the plan that are not explicitly stated in the spec.

## 2. Output Files
You will produce two files, typically co-located in the same directory as the specification file (e.g., `specs/v1/`):
1. `plan.md` (The detailed Implementation Plan)
2. `tasks.md` (The Checkbox Task List)

## 3. Plan Structure (`plan.md`)
- **Testable Phases**: Divide the implementation into logical, human-testable phases. A testable state could be as simple as a "hello world" or a successful REST client request.
- **Atomic Tasks**: Within each phase, define a specific list of atomic tasks in dependency order, even if some could theoretically be parallelized.
- **Task Numbering**: Number all tasks sequentially by phase and item number (e.g., `1.1`, `1.2`, `2.1`).
- **No Checkboxes**: `plan.md` will contain the full details and implementation steps for each task, but **must not** contain any markdown checkboxes (`- [ ]`). The implementation agent will not make changes to the plan.

## 4. Task List Structure (`tasks.md`)
- Create a separate file called `tasks.md`.
- It must contain the exact tasks from the plan, numbered identically, but structured as a checklist with markdown checkboxes (e.g., `- [ ] 1.1 Initialize project`).
- Organize the checkboxes by phase, matching the structure of `plan.md`.
- Keep the task descriptions brief in this file; the implementation agent will refer to `plan.md` for the full details and mark tasks off in `tasks.md` as they are completed.
