# Phase Final Acceptance Checklist

This checklist closes Phase F. All items must be verified on the target branch before release.

## Preconditions

- [ ] Database migrations applied (`alembic upgrade head`)
- [ ] Excel dictionary imported at least once
- [ ] Initial admin user created and login works
- [ ] CALB_DATABASE_URL points to the intended environment

## Sizing Runtime Chain

- [ ] Project can be created
- [ ] Case can be created under the Project
- [ ] DC sizing produces a new `run_id`
- [ ] `run_id` persists Project / Case / Run / Input Snapshot / Output Snapshot
- [ ] Run History lists runs under the current Case
- [ ] Run can be restored by `run_id` after refresh

## Auth And RBAC

- [ ] Login works for admin
- [ ] Login works for normal_user
- [ ] Admin can see all projects
- [ ] normal_user can only access assigned projects
- [ ] Admin-only pages are blocked for normal_user
- [ ] Audit logs record actor for write operations

## Deterministic Diagrams

- [ ] SLD plugin renders from `run_id`
- [ ] Layout plugin renders from `run_id`
- [ ] Artifacts are registered in DB with plugin metadata
- [ ] Views do not assemble diagram spec directly

## External AI Layout Workflow

- [ ] Prompt payload and prompt text can be generated from `run_id`
- [ ] External AI image can be uploaded
- [ ] Review decision supports approve/reject/request_revision
- [ ] Approved AI artifact is stored without replacing deterministic artifacts

## Tests

Run the full test suite:

```bash
pytest -q
```

Optional focused groups:

```bash
pytest tests/unit -q
pytest tests/integration -q
```

Record the result summary here:

- [ ] All tests green
- [ ] Failures triaged and resolved

## Release Readiness

- [ ] README updated with DB/init/login/run/diagram/AI workflow steps
- [ ] Architecture snapshot updated
- [ ] Next-phase backlog recorded
