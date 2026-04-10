# Auth and RBAC Target Model

Date: 2026-04-10
Scope: Target design only (no implementation in this phase)

## User Model (Target)
- user_id (UUID)
- email (unique)
- display_name
- status: active, suspended, invited
- auth_provider: local, sso, oidc
- created_at, updated_at, last_login_at

## Role Model (Target)
- role_id (UUID)
- role_code: admin, project_owner, engineer, viewer
- description
- is_system_role

## Project Membership Model
- membership_id (UUID)
- user_id
- project_id
- role_id
- status: active, pending, revoked
- created_at, updated_at

## Permission Matrix (Draft)
- Admin: manage users, manage projects, manage cases, run sizing, view all runs, manage parameters, export reports.
- Project Owner: manage project, manage cases, run sizing, view all runs in project, export reports.
- Engineer: create cases, run sizing, view runs in project, export reports.
- Viewer: view projects and runs, export reports (read-only).

## Authorization Boundaries
- Project-level authorization gates all Case/Run access.
- Parameter management is restricted to Admin only.
- Artifact publish (reports/diagrams/layout) requires Project Owner or Admin.

## Login and Page Access Control (Target Behavior)
- All page entry points check auth context and project membership.
- Public or unauthenticated mode is explicitly configured and defaults to off in production.
- The UI can still run in a local developer mode with auth disabled and a mock user.

## Audit Requirements
- Every auth-relevant action logs actor_id, action, entity, and timestamp.
- Audit log should store permission denials for traceability.
