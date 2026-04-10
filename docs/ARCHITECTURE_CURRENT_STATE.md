# Architecture Current State

This document captures the current system architecture after Phases A-E.

## Runtime Stack

- UI: Streamlit (`app.py`, `calb_sizing_tool/ui`)
- Services: pure Python services under `calb_sizing_tool/services`
- Persistence: SQLAlchemy 2.0 with Alembic migrations
- Database: SQLite for dev, PostgreSQL-compatible models
- Artifacts: stored in `outputs/` and indexed in DB

## Primary Data Flow

1. UI collects inputs and calls service layer.
2. DC pipeline computes Stage 1-3 results.
3. Run persistence writes Project, Case, Run, Input Snapshot, Output Snapshot.
4. UI returns `run_id` and can restore outputs by `run_id`.
5. Session state is UI cache only, not source of truth.

## Core Persistence Model

- Project
- SizingCase
- SizingRun
- RunInputSnapshot
- RunOutputSnapshot
- ArtifactRegistry
- AuditLog

## Auth And RBAC

- Users, roles, and project membership stored in DB.
- Admins can access all projects.
- Normal users are restricted to assigned projects.
- Audit log records the actor for write operations.

## Diagram And Layout Plugins

- Plugin registry resolves deterministic plugins for SLD and Layout.
- Views pass `run_id` and use services to build inputs from snapshots.
- Artifacts are persisted with plugin metadata in the registry.

## External AI Layout Workflow

- Prompt payload and prompt text are generated from run snapshots.
- External AI outputs are uploaded as pending review.
- Review workflow supports approve/reject/request_revision.
- Approved AI artifacts coexist with deterministic artifacts.

## Compatibility Constraints

- DC sizing math logic remains unchanged.
- AC/SLD/Layout views are thin adapters to services and plugins.
- Legacy session adapters remain only for backwards compatibility and UI cache.
