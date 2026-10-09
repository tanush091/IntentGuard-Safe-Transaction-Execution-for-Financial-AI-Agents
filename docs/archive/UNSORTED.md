# Unsorted

Items found during the 2026-10-09 restructure that were not clearly current or legacy. None of
these were deleted.

| Item | Tracked by git | Notes |
|---|---|---|
| `docs/presentation/IntentGuard_Project_Review.pptx` | No | A presentation deck. Its contents were not reviewed against the measured results. Left in place, untracked |
| `intentguard.db` (repository root) | No (gitignored) | Database of the earlier prototype (incompatible schema; `scripts/start.bat` mentions it). Safe to delete locally |
| `intentguard_gateway.db*`, `paysim_state.json` (repository root) | No (gitignored) | Local state from running the services at the root before the move. Services now keep state in `backend/` |
