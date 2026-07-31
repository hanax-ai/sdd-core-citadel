# GOAL-AWF-DASHBOARD-001

## Create the Program Roadmap and RAID Management Dashboard, using frontend design skill and schadcn

**Status:** Draft for Agent Zero review
**Target repository:** `hanax-ai/sdd-core-agent-workflow`
**Authority:** This goal authorizes specification and planning only. Implementation requires completion of the canonical SDD lifecycle and explicit Gate 2 approval from Agent Zero.

## 1. Goal

Design, build, validate, and prepare for deployment a visual web dashboard that provides Agent Zero with a current, traceable, and actionable view of the three-project program roadmap across:

* SDD-Core
* CENTCOM Dashboard
* SDD-Core Agent Workflow

The dashboard shall enable authorized users to monitor roadmap execution, identify blockers and dependencies, manage RAID items, assign accountable owners and resolvers, track remediation through closure, and retain a complete audit trail.

The dashboard shall serve as the portfolio execution-control interface for Agent Workflow. It shall not replace project constitutions, approved specifications, GitHub records, human approval gates, or repository-local implementation authority.

## 2. Preconditions

Codex shall not begin dashboard planning until:

1. The accepted Program Architecture Decision, detailed roadmap, and RAID workbook have been committed to GitHub.
2. Their canonical repository, commit SHA, path, version, and digest have been established.
3. The Agent Workflow repository has adopted its project-local governance and pinned SDD-Core methodology version.
4. SQLite has been formally established as Agent Workflow’s operational system of record.
5. Agent Zero has approved this goal for specification.

If source documents conflict, contain missing identifiers, or leave an authoritative source ambiguous, Codex shall stop and ask Agent Zero. Codex shall not infer or silently reconcile governance decisions.

## 3. Required SDD Route

Codex shall execute this goal through the canonical SDD-Core feature lifecycle:

`Scaffold → Specify + Clarify → Plan → Tasks → Gate 2 → Execute → Validate`

Required feature artifacts include:

* `spec.md`
* `plan.md`
* `tasks.md`
* Data model and migration design
* UX design and dashboard wireframes
* Test and acceptance strategy
* Traceability matrix
* Deployment and operations runbook
* Final implementation and validation report

Goals authorize and bound the work. They do not replace these deliverables.

## 4. Intended Operational Outcomes

The completed dashboard shall allow Agent Zero and authorized program participants to:

1. See overall implementation health across all three projects.
2. Monitor progress by project, roadmap phase, milestone, goal, work package, and task.
3. Identify critical-path items, dependencies, blocked work, overdue work, and upcoming decisions.
4. Review all Risks, Assumptions, Issues, and Dependencies in one filterable register.
5. Assign each actionable RAID item to an accountable owner and designated resolver.
6. Establish due dates, priorities, mitigation or resolution actions, and closure criteria.
7. Track each item from identification through acceptance and closure.
8. Link roadmap and RAID records to their governing specification, GitHub issue, pull request, commit, decision, evidence, or deliverable.
9. See what changed, who changed it, when it changed, and under what authority.
10. Produce leadership-ready status views without manually rebuilding the roadmap or RAID workbook.

## 5. Required Dashboard Views

### 5.1 Executive Overview

Display, at minimum:

* Overall program health
* Progress by project and phase
* Completed, active, blocked, overdue, and not-started work
* Open critical and high-priority RAID items
* Unassigned RAID items
* Items awaiting Agent Zero decision or acceptance
* Upcoming milestones and due dates
* Recently resolved items
* Data freshness and last successful synchronization

### 5.2 Roadmap View

Provide:

* Timeline or Gantt-style phase and milestone visualization
* Goal, work-package, and task hierarchy
* Dependency and critical-path visibility
* Status, owner, planned date, actual date, and percent-complete tracking
* Filters for project, phase, owner, status, priority, and date
* Direct navigation from roadmap items to related RAID records and evidence

### 5.3 RAID Management View

Provide a filterable and sortable RAID register with type-specific fields:

* **Risk:** likelihood, impact, exposure, mitigation, contingency, trigger, and review date
* **Assumption:** validation method, validation owner, due date, and validation outcome
* **Issue:** severity, root cause, corrective action, resolver, and target resolution date
* **Dependency:** provider, consumer, prerequisite, need-by date, and dependency status

Each record shall also include:

* Stable identifier
* Project and roadmap relationship
* Title and description
* Priority and current status
* Accountable owner
* Assigned resolver
* Created, updated, due, and closed dates
* Recommended action
* Closure criteria
* Evidence references
* Complete change history

Decisions contained in the existing workbook shall be retained as linked decision records rather than misclassified as dependencies.

### 5.4 Assignment and Resolution View

Authorized users shall be able to:

* Assign or reassign accountable owners and resolvers
* Establish due dates and priorities
* Record mitigation or resolution actions
* Add progress updates and evidence
* Request acceptance of a proposed resolution
* Return insufficient resolutions for further work
* Close an item only after its closure criteria and required evidence are satisfied

The proposed common workflow is:

`Open → Triaged → Assigned → In Progress → Pending Acceptance → Closed`

Exceptions such as `Deferred`, `Accepted Risk`, `Invalidated`, or `Reopened` must be explicitly defined in the specification.

### 5.5 Audit and Traceability View

Provide immutable visibility into:

* Record creation
* Field changes
* Status transitions
* Assignments and reassignments
* Due-date changes
* Resolution submissions
* Acceptance or rejection decisions
* Evidence references
* Import and synchronization events

Records shall be archived or superseded, not silently deleted.

## 6. Data Authority and Integration Rules

1. GitHub remains authoritative for governed documents, specifications, plans, source code, pull requests, commits, and durable evidence.
2. Agent Workflow SQLite becomes authoritative for live roadmap execution state, RAID state, assignments, workflow transitions, and audit-event metadata after an approved cutover.
3. The initial import shall be explicit, repeatable, and reconciled against the source documents.
4. Every imported record shall retain its source repository, commit, path, version, and digest.
5. Missing or ambiguous source values shall be flagged for resolution; they shall never be guessed.
6. The import shall preserve all existing roadmap records and RAID entries without duplication or silent loss.
7. There shall be no indefinite dual-authority period between the GitHub source artifacts and SQLite.
8. All SQLite writes shall pass through one Agent Workflow application-service boundary.
9. The dashboard shall not directly read or write CENTCOM’s PostgreSQL/Supabase database.
10. The dashboard shall not write to another project’s repository or operational database.
11. GitHub issue or pull-request creation, assignment, or synchronization shall require separately specified permissions and Agent Zero approval.

## 7. Authority and Governance Rules

* Agent Zero remains the human approval authority.
* Dashboard status changes cannot grant planning approval, Gate 2 authority, merge authority, release authority, or deployment authority.
* Agents may propose assignments, updates, mitigations, and resolutions only within their authorized scope.
* Only authorized roles may assign work, accept resolutions, close governed items, or change milestone commitments.
* Every material action must retain actor identity, timestamp, authority basis, and evidence.
* The dashboard must preserve the independent governance and release lifecycle of each project.
* SDD-Core methodology changes must occur in SDD-Core.
* CENTCOM implementation changes must occur in CENTCOM.
* Agent Workflow and dashboard implementation changes must occur in Agent Workflow.

## 8. Visual and Usability Requirements

The interface shall:

* Present leadership information first and detailed evidence on demand.
* Use clear status language: `On Track`, `At Risk`, `Blocked`, `Awaiting Decision`, and `Complete`.
* Avoid relying on color as the sole status indicator.
* Support desktop use and a readable tablet layout.
* Provide search, sorting, saved filters, and drill-down navigation.
* Preserve stable URLs or identifiers for individual roadmap and RAID records.
* Clearly display data freshness, source provenance, and unresolved synchronization errors.
* Avoid decorative metrics that do not support a decision or action.

## 9. Minimum Acceptance Criteria

The goal is complete only when:

1. All canonical roadmap phases, goals, work packages, tasks, dependencies, and existing RAID entries are imported and reconciled with zero unexplained omissions or duplicates.
2. Users can view progress across all three projects and drill down to the source record.
3. Authorized users can create, triage, assign, update, resolve, accept, close, and reopen RAID items.
4. Every actionable RAID item supports an accountable owner, resolver, due date, recommended action, and closure criteria.
5. Blocked roadmap items can be linked directly to the RAID item or dependency causing the block.
6. Overdue, unassigned, high-priority, and decision-pending items are automatically surfaced.
7. All record and assignment changes persist correctly and appear in the audit history.
8. Role and authority controls prevent unauthorized approvals, closures, or administrative changes.
9. Import validation proves that the GitHub source artifacts and resulting SQLite records reconcile.
10. Automated tests cover data import, state transitions, assignments, permissions, audit history, migrations, and recovery.
11. Backup and restore procedures are successfully demonstrated.
12. Accessibility, responsive layout, error states, and empty states are validated.
13. The application passes the project’s CI and governed review process.
14. Agent Zero accepts the final demonstration and implementation evidence.
15. No production deployment occurs without a separate explicit deployment authorization.

## 10. Required Deliverables

* Approved `spec.md`, `plan.md`, and `tasks.md`
* Clarification and decision log
* Data dictionary and entity-relationship model
* SQLite schema and versioned migrations
* Source-import and reconciliation design
* UX wireframes and visual design specification
* Implemented dashboard
* Automated test suite
* Source-to-dashboard traceability matrix
* Security and permissions assessment
* Backup, recovery, and migration procedures
* User and administrator guide
* Deployment runbook
* Demonstration dataset
* Final validation and acceptance report
* Deliverables index

## 11. Out of Scope

Unless separately approved, this goal does not authorize:

* Changes to the SDD-Core constitution or methodology
* Changes to the CENTCOM application or database
* Replacement of GitHub as the governed artifact repository
* Automated approval, merge, release, or deployment decisions
* Direct cross-project database access
* A general-purpose enterprise project-management platform
* Bidirectional GitHub synchronization
* Production deployment
* Multi-host or high-concurrency database architecture
* Removal or rewriting of historical roadmap, RAID, or audit evidence

## 12. Recommended Delivery Sequence

1. Verify and pin all GitHub source artifacts.
2. Create and clarify the feature specification.
3. Define the data model, authority boundaries, and import/cutover process.
4. Design and approve the dashboard user experience.
5. Produce the implementation plan and lowest-level ordered tasks.
6. Obtain Agent Zero’s Gate 2 authorization.
7. Build a read-only roadmap and RAID dashboard.
8. Validate source import and reconciliation.
9. Add controlled assignment and resolution workflows.
10. Add audit, permissions, backup, and recovery controls.
11. Complete integration, usability, and acceptance testing.
12. Present the final demonstration and request release authorization.

## 13. Operating Direction to Codex

Proceed slowly and sequentially. Reduce each activity to its lowest independently verifiable task. Make no assumptions and do not guess missing requirements, ownership, authority, source locations, or state. When evidence conflicts or a decision is required, stop and ask Agent Zero.

Do not modify `main`, deploy the application, change another project, or initiate external assignments without explicit authorization.
