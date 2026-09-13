# `sync_run` table

**Status: designed, not implemented.** The layering will be
`view → services/SyncRunService.py → repository/SyncRunRepository.py →
services/DatabaseService.py`: all SQL for this table lives in the repository,
`DatabaseService` only hands out connections, and `SyncRunService` owns opening
a run, closing it, and reading the history back. The screen is
`view/admin/screens/library_sync_view.py`, which is the only screen that starts
a run and the only one that reads this table. It renders four things from it:
the "Last run summary" panel (`_summary`), the scan strip (`_scan_strip`), the
result tiles (`_counts`) and the "Last reset" row of the confirm panel
(`_confirm`).

Third table of the SQLite database. Scope: one row per pipeline run — a scan,
an update, or a reset — with what it did and how it ended. Nothing per-file;
that is `sync_run_file`, the last table.

The project-wide column convention is in
[`settings-table.md`](settings-table.md#project-wide-column-convention), with
the naming rule from [`file-table.md`](file-table.md): **every timestamp column
ends `_date`**, so the audit columns here are `created_date` and `updated_date`.

---

## Append-only, so it cannot go stale

[`file-table.md`](file-table.md#this-table-is-a-record-not-the-source-of-truth)
carries a warning: its rows describe live state, so a cached row must never
drive a decision. **This table has the opposite property and needs no such
warning.** A run happened at a point in time; nothing about the world can make
"the update at 10:24 embedded 17 documents" untrue later.

That is what makes it safe to read straight onto the screen. Today the summary
panel renders from `portal.state["sync_result"]` (`view/admin/screens/library_sync_view.py`),
which is session state — close the window and the record of what you just did
is gone. A row here survives that, and can never mislead the way a stale
`file.status` could.

Rows are **written, then closed, and never revised again.**

---

## DDL

```sql
CREATE TABLE sync_run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type        TEXT    NOT NULL CHECK (run_type IN ('scan', 'update', 'reset')),
    outcome         TEXT    NOT NULL DEFAULT 'running'
                            CHECK (outcome IN ('running', 'completed', 'cancelled', 'failed')),
    started_date    TEXT    NOT NULL,
    finished_date   TEXT,
    walked_count    INTEGER NOT NULL DEFAULT 0,
    selected_count  INTEGER NOT NULL DEFAULT 0,
    converted_count INTEGER NOT NULL DEFAULT 0,
    added_count     INTEGER NOT NULL DEFAULT 0,
    updated_count   INTEGER NOT NULL DEFAULT 0,
    removed_count   INTEGER NOT NULL DEFAULT 0,
    failed_count    INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    created_date    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_date    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
```

| column | holds |
| --- | --- |
| `run_type` | `scan`, `update` or `reset` — matches the three things the screen can start |
| `outcome` | `running` until the run closes, then `completed` / `cancelled` / `failed` |
| `started_date` | when the worker was dispatched |
| `finished_date` | when it closed. `NULL` while running, and permanently `NULL` if the app died mid-run |
| `walked_count` | how many files the run looked at — the scan strip's "Files walked" |
| `selected_count` | how many files you ticked. 0 for a scan, all of them for a reset |
| `converted_count` | files reconverted to `.txt` |
| `added_count` / `updated_count` / `removed_count` | documents upserted or deleted in Chroma |
| `failed_count` | files that raised and were skipped |
| `error` | the exception text when `outcome = 'failed'`, otherwise `NULL` |

`run_type` is named to match `file.file_type` — `kind` is not used as a column
name anywhere in this schema.

No natural key, so nothing is `UNIQUE`: two runs of the same type starting in
the same second are two genuinely different runs. `id` is the only identity a
run has.

No index. The history query is `ORDER BY started_date DESC LIMIT n` over a
table that gains a handful of rows a day; SQLite will scan it faster than it
would descend an index. Revisit if a history *screen* with filters is ever
built — see [Still open](#still-open).

### Open the row before the work, close it after

```python
# dispatch, before page.run_thread
INSERT INTO sync_run (run_type, outcome, started_date, created_date, updated_date)
VALUES (?, 'running', ?, ?, ?)

# once, when the worker finishes
UPDATE sync_run
   SET outcome = ?, finished_date = ?, walked_count = ?, selected_count = ?, converted_count = ?,
       added_count = ?, updated_count = ?, removed_count = ?, failed_count = ?,
       error = ?, updated_date = ?
 WHERE id = ?
```

Two writes, not one. Inserting only on success would mean a crash leaves no
trace at all; this way a killed process leaves a visible `running` row with a
`NULL finished_date`, which is the honest record of what happened. It also
gives `sync_run_file` a parent id to hang rows off while the run is still going.

`started_date` and `finished_date` are supplied by the application through
`DatabaseService.now()` (`services/DatabaseService.py:20`), like every other
timestamp in the schema. The `DEFAULT (strftime(...))` clauses on the audit
columns stay as an insert-time safety net only.

### The counts are denormalised on purpose

They could all be derived by counting `sync_run_file` rows. They are stored
anyway, for three reasons:

- A **reset** touches every file. Deriving its counts means aggregating ~350
  child rows to render one summary card.
- `converted_count` has no per-file counterpart worth a row — an unsupported
  file that was walked and skipped is not interesting enough to persist 350
  times over.
- The child table is the first candidate for pruning (see
  [Still open](#still-open)). The summary must survive its detail being dropped.

### `walked_count` exists because two panels need it and neither can derive it

It was not in the first draft. Reading the screen back column by column found
two places with nothing behind them:

- **The scan strip** (`_scan_strip`, `library_sync_view.py:441`) shows *Scanned
  at*, *Files walked* and *Duration*. The first is `started_date`, the third is
  `finished_date − started_date`, and the second had no home — a scan ticks
  nothing and converts nothing, so every other count on the row is 0 and the
  one number a scan actually produces was unrecorded. That is what
  `mock_data.SCAN_STATS["walked"]` is standing in for today.
- **The Skipped tile** (`_counts`, `library_sync_view.py:464`) is
  `len(scan_changes) - len(picked)` — the files the run left alone. With
  `walked_count` that is `walked_count - selected_count`, so it stays derived
  rather than becoming a seventh count.

Its meaning is "how many files this run had in front of it": for a `scan`, the
files walked; for an `update`, the size of the scan result it was applied to;
for a `reset`, every source file. Same number the run's own log line already
prints — "converted: 17, skipped: 331".

**No `blocked_count`, and no per-status count beyond the four.** The pre-apply
tiles — *To add*, *To update*, *To remove*, *Blocked* — are counted off the
scan result in memory (`_counts` groups `scan_changes`), and after an apply the
same tiles switch to the run's outcome. A scan's findings live in `file.status`,
where they are refreshed in place; copying them here would be a second, ageing
copy of the same fact, and the `Blocked` group is exactly the part of a scan
that no run ever acts on.

### What `is_active` means here

Runs are never deleted, so `is_active = 0` means "hidden from the history
list" — a way to dismiss a noisy failed run without losing it. Reads for the
summary panel filter `WHERE is_active = 1`.

This is the weakest `is_active` in the schema; nothing in the current UI sets
it. It is here because the convention requires it, and dismissal is the only
sensible meaning it could carry.

---

## Seed rows

**None.** An empty table means "never run", which is a valid state the summary
panel already renders as its `empty_state`.

---

## How the screen uses it

- **On open** — `SELECT * FROM sync_run WHERE is_active = 1 ORDER BY
  started_date DESC LIMIT 1` fills the "Last run summary" panel, so it is
  populated before you do anything. Today `_summary()` renders an
  `EmptyState` reading "No run in this session" whenever `sync_stage` is
  `idle` — the wording is an admission that the panel only knows about this
  window, and it becomes "No run yet" once one row is enough to know better.
- **On dispatch** — insert, keep the returned `id` in `portal.state` for the
  duration of the run. `AdminPortal.state` already carries `sync_result`,
  `sync_progress` and `sync_error` (`view/admin/shell.py:56-60`); the run id
  joins them and is the only one of the four that outlives the window.
- **On finish** — one update. `_play()` in `library_sync_view.py` already distinguishes
  a completed run from a cancelled one, so `outcome` comes straight from its
  return value: `False` from `_play()` is `cancelled`, an exception is `failed`.
- **After a scan** — the strip needs `started_date`, `walked_count` and the
  duration; `_scan_strip()` reads them from the row the scan just closed rather
  than from `mock_data.SCAN_STATS`.
- **Before a reset** — "Last reset" in the confirm panel is hardcoded as
  "6 days ago" (`library_sync_view.py:1227`). It is
  `SELECT started_date FROM sync_run WHERE run_type = 'reset' AND outcome =
  'completed' AND is_active = 1 ORDER BY started_date DESC LIMIT 1`, rendered
  as an age. This is the one place `run_type` earns its keep as a filter rather
  than a label, and the one place the panel is asking about a run that is not
  the most recent one.
- **On a stale `running` row at startup** — leave it. It is displayed as
  "interrupted", not repaired, because there is no way to know what it did.

The two panels beside the step list — "Scanning" and "This run" — read
`setting`, not this table: input path, collection and embedding model are
configuration, deliberately not snapshotted here (see
[Decisions](#decisions-taken-while-designing)).

---

## Decisions taken while designing

- **Scans get a row too, even though a scan writes nothing.** It was tempting
  to record only runs that change something. But "when did I last scan" is
  exactly the question the review screen's cached first paint has to answer,
  and a scan can fail — a Drive credential error is worth a `failed` row with
  the exception in `error`. `run_type` exists precisely so the summary panel
  can tell the two apart.
- **This overlaps `file.last_scanned_date`, and that is accepted.**
  `file.last_scanned_date` answers "how fresh is *this row*"; `sync_run`
  answers "what happened *at that moment*". Deriving one from the other would
  need a join on every cached paint to render one line of text.
- **`outcome` and `error` rather than a boolean `is_success`.** `cancelled` is
  a first-class result here — the plan makes Cancel co-operative, stopping at
  the next file boundary, so a cancelled run has done real work and its counts
  are meaningful. A boolean would force it to be recorded as a failure.
- **No `duration` column.** `finished_date - started_date`, and storing a
  derived value that can disagree with its inputs is the same mistake
  `file-table.md` avoids with the mtimes.
- **No `collection` or `model` column.** Tempting for "which collection did
  this run write to", but they live in `setting` and would be a snapshot that
  silently goes stale against it. If run-time configuration ever needs
  capturing, it should be captured deliberately and completely, not two columns
  at a time.

## Still open

1. **Retention.** Nothing prunes this. One row per run is slow growth, but
   there is no story for it, and `sync_run_file` grows ~350× faster.
2. **A history screen.** One row is all the summary panel needs, so there is no
   list UI and therefore no index. A "recent runs" view would want
   `INDEX (started_date DESC)` and a reason for `is_active` to exist.
3. **Interrupted runs are never reconciled.** A `running` row with a `NULL
   finished_date` stays that way forever. Marking them `failed` on the next
   startup would be tidier, but it asserts something the app cannot actually
   know.
4. **Concurrent runs.** The screen refuses a second run in one window — the
   mode switch is disabled while `sync_stage` is `scanning` or `updating`, and
   the run button becomes Cancel — but two windows would each open a row.
   Harmless for the record; the damage, if any, is in the pipeline, not here.
5. **`run_type = 'reset'` has no writer yet.** `_confirmed()` still calls
   `not_implemented("Reset library")` (`library_sync_view.py:1273`), so the
   reset path is a confirmation flow with nothing behind it. The "Last reset"
   row above therefore reads from a value that only a future reset will write
   — it renders "never" until then, and that is the correct first behaviour,
   not a bug to paper over with a seed row.

---

## Build order

1. `plans/sync-run-table.md` → this document.
2. `repository/SyncRunRepository.py` → the DDL and every statement: `initialise`
   (create only, no seed), `open_run`, `close_run`, `find_latest_active`. Like
   `SettingRepository`, it returns what it could not do rather than raising
   domain errors.
3. `services/SyncRunService.py` → opens and closes runs, maps the counts dict
   returned by `SyncPlannerService.apply()` onto columns.
4. `view/admin/screens/library_sync_view.py` → `_scan()` and `_update()` open
   the run before dispatching, and close it in a `finally` around `_play()`, so
   a crash still records `failed` with the exception text. There is no
   `run_worker()` and no worker module: the shell (`view/admin/shell.py`) only
   navigates and re-renders, and the run is driven from the screen itself.
5. `view/admin/screens/library_sync_view.py` → `_summary()` reads the latest row on open
   instead of starting blank.

Then, last: `plans/sync-run-file-table.md`, the per-file detail of a run,
joining `sync_run` to `file`.
