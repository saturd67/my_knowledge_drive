# `sync_run_file` table

**Status: designed, not implemented.** It has no service of its own — it is
written and read through `services/SyncRunService.py`, because a row here is
never meaningful except as part of its run. SQL lives in
`repository/SyncRunFileRepository.py`, one module per table as usual.

Fourth and last table of the SQLite database. Scope: which files a run touched
and what happened to each. It is the join between
[`sync_run`](sync-run-table.md) and [`file`](file-table.md), and it is what
turns "12 documents updated" into "*these* 12, and this one failed because
Tesseract choked on page 4".

The project-wide column convention is in
[`settings-table.md`](settings-table.md#project-wide-column-convention), with
the naming rule from [`file-table.md`](file-table.md): **every timestamp column
ends `_date`**.

---

## DDL

```sql
CREATE TABLE sync_run_file (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_run_id  INTEGER NOT NULL REFERENCES sync_run(id),
    file_id      INTEGER NOT NULL REFERENCES file(id),
    status       TEXT    NOT NULL,
    action       TEXT    NOT NULL
                         CHECK (action IN ('converted', 'upserted', 'deleted', 'skipped', 'failed')),
    error        TEXT,
    created_date TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_date TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (sync_run_id, file_id)
);

CREATE INDEX idx_sync_run_file_file ON sync_run_file (file_id);
```

| column | holds |
| --- | --- |
| `sync_run_id` | the run this belongs to |
| `file_id` | `file.id`, **not** `file.file_key` |
| `status` | the scan status the file had *when you ticked it* — `added`, `updated`, `stale_local`, `removed` |
| `action` | what the run actually did to it |
| `error` | the exception text when `action = 'failed'`, otherwise `NULL` |

`status` records intent, `action` records outcome, and **the interesting rows
are the ones where they disagree.** A file ticked as `updated` that comes back
`skipped` means its converted text went missing between the scan and the apply;
that is a diagnosis you cannot make from either column alone.

`status` carries no `CHECK`. Its vocabulary is the scan's, listed in
`STATUS_META` (`library_sync_view.py:52`) and documented in
[`file-table.md`](file-table.md#ddl), and it will grow as the scan learns to
tell more cases apart — a constraint here would mean a migration every time. `action` is this
table's own vocabulary and is small and closed, so it is constrained.

### The two constraints

`UNIQUE (sync_run_id, file_id)` — a run touches a file at most once. It also
makes the write idempotent, so a retried batch cannot double-insert.

`INDEX (file_id)` — SQLite does **not** index foreign keys automatically. The
`UNIQUE` above gives an index led by `sync_run_id`, which covers "everything
this run did", but per-file history queries the other way round, and that is
the reason this table exists. `sync_run_id` needs no separate index; the
`UNIQUE` already serves it.

Foreign keys are enforced: `DatabaseService.connection()` sets
`PRAGMA foreign_keys = ON` (`services/DatabaseService.py`). Neither parent is
ever deleted — both use soft delete — so no `ON DELETE` clause is needed, and
omitting it means an accidental hard delete of a parent fails loudly instead of
quietly taking children with it.

### `file_id`, not `file_key`

The key is a path, and paths get renamed. `file.file_key` moving would either
strand this row or need a cascading update across every historical row.
`file.id` is a surrogate that never changes — which is exactly why the
convention mandates one even where a natural key exists.

---

## Scans write nothing here

Only `update` and `reset` runs produce child rows.

A scan is read-only over ~350 files. Recording it per file would add ~350 rows
every time you press the button, to say "we looked at it and it was fine" — the
table would be almost entirely made of non-events, and it would grow faster
from scanning than from any real work. What a scan actually found is already in
`file.status` and `file.last_scanned_date`, refreshed in place.

So: **this table records changes, not observations.** A file appears here only
when a run tried to do something to it.

A reset still writes ~350 rows, because a reset genuinely rebuilds every
document. That makes resets the dominant source of growth here, which is why
pruning is the open question below.

### What `is_active` means here

The weakest `is_active` in the schema, and it is present only because the
convention requires it. A history row has no natural retirement — it either
happened or it did not. Its one plausible use is marking rows dropped by a
future pruning job so the count of what a run touched stays honest after its
detail is discarded. Reads filter `WHERE is_active = 1` regardless.

---

## Seed rows

**None.** An empty table means nothing has been applied yet.

---

## How the screen uses it

- **During an apply** — rows are inserted in one transaction as the run closes,
  not one at a time as files complete. A cancelled run still writes rows for
  what it managed to do, since `SyncPlannerService.apply()` returns per-file
  outcomes either way.
- **Per-file history** — the payoff, and not yet designed into a screen:

  ```sql
  SELECT r.started_date, r.run_type, f.status, f.action, f.error
    FROM sync_run_file f
    JOIN sync_run r ON r.id = f.sync_run_id
   WHERE f.file_id = ? AND f.is_active = 1
   ORDER BY r.started_date DESC;
  ```

- **Failures of the last run** — `WHERE sync_run_id = ? AND action = 'failed'`,
  which is what a "3 files failed" line in the summary panel would expand into.

---

## Decisions taken while designing

- **No `duration` or per-file timing.** Interesting for spotting the one `.docx`
  with forty screenshots that dominates every run, but that is a profiling
  question, and the run log already shows it live.
- **`error` is stored per file, not only per run.** `sync_run.error` is for a
  run that died; this is for a run that completed with casualties. Both can be
  non-null in the same run.
- **The row is a fact about an attempt, never revised.** `updated_date` will
  equal `created_date` for the life of every row. It is carried because the
  convention is fixed, not because anything updates it.
- **Rows are keyed to files, not to Chroma document ids.** A `removed` file's
  Drive id is gone from Drive by definition; `file_id` still resolves, and
  `file.drive_id` holds the id that was deleted.

## Still open

1. **Pruning, and this is the one that matters.** ~350 rows per reset, forever.
   `sync_run` was deliberately given denormalised counts so its summaries
   survive this table being thinned — the mechanism is designed for, but not
   built. A "keep detail for the last N runs" job is the obvious shape.
2. **No screen reads it yet, but there is now a place to put one.** Nothing in
   `library_sync_view.py` shows per-file history; the query above is written
   but unused. What changed is the Library: each document row ends in a fixed
   88px action cluster holding two icon buttons — Copy document id and Open in
   Google Drive (`library_view.py:284-293`) — and a third, History, opening a
   panel of that file's runs is the natural first reader. It is also the only
   screen that can offer it, since Library Sync shows a *scan result*, which is
   about right now, while this table is about what happened before.

   That still does not settle whether the table is built now or with that
   panel. Until it is read, it is write-only, and a `reset` writes ~350 rows
   into it every time.
3. **`status` is unconstrained**, so a typo in the scan's vocabulary would be
   stored silently. A lookup table would fix it and is almost certainly not
   worth a fourth join.
4. **A file deactivated in `file` keeps its history**, which is correct, but
   the per-file query joins on a row you can no longer reach from the UI. A
   history screen would need a way to look up retired files.

---

## Build order

1. `plans/sync-run-file-table.md` → this document.
2. `repository/SyncRunFileRepository.py` → DDL, index, and `initialise`,
   `insert_many`, `find_for_run`, `find_for_file`.
3. `services/SyncRunService.py` → extended to write child rows as it closes a
   run. No separate service.
4. `services/SyncPlannerService.py` → `apply()` returns per-file outcomes, not
   just counts, so there is something to write.

Build it after [`sync_run`](sync-run-table.md), which owns the parent id, and
after [`file`](file-table.md), which owns `file_id`. Both foreign keys are
enforced, so neither order is optional.

---

## The schema, complete

| table | rows | purpose | read by |
| --- | --- | --- | --- |
| [`setting`](settings-table.md) | ~10 | configuration. Implemented | all three admin screens |
| [`file`](file-table.md) | ~350 | per-file registry; instant first paint | Library, Library Sync |
| [`sync_run`](sync-run-table.md) | one per run | what each run did | Library Sync |
| `sync_run_file` | ~350 per reset | which files, and what happened to each | nothing yet |

Nothing else is planned. The vector store stays in Chroma and the converted
text stays on disk; SQLite holds configuration and history, never content.
