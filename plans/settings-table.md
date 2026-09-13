# `setting` table

**Status: implemented.** The layering is
`view → services/SettingService.py → repository/SettingRepository.py →
services/DatabaseService.py`: all SQL for this table lives in the repository,
`DatabaseService` only hands out connections, and `SettingService` owns
caching, path resolution and errors. Keys and seed values are in
`constant/settings.py`; the screen is `view/admin/screens/settings_view.py`.

First table of the SQLite database. Scope: hold the configuration values the
Settings screen (`view/admin/screens/settings_view.py`) shows and edits. Nothing else.

Settings is one of the three admin screens, all under `view/admin/screens/` and
wired up in `view/admin/shell.py`: **Library** (`library_view.py`), **Library
Sync** (`library_sync_view.py`) and **Settings**. The other two read this table
on every render but never write to it — see
[How the screens use it](#how-the-screens-use-it).

DB file: `resources/knowledge_drive.db`, exposed as `DB_PATH` in
`constant/paths.py`. Gitignored like the rest of `resources/`.

---

## Project-wide column convention

Every table in this project carries these four columns, whatever else it holds:

| column | type | notes |
| --- | --- | --- |
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | surrogate key, even when a natural key exists |
| `created_at` | `TEXT` | ISO-8601 UTC, set by the application on insert |
| `updated_at` | `TEXT` | ISO-8601 UTC, set by the application on every update |
| `is_active` | `INTEGER` 0/1 | soft delete — rows are deactivated, never `DELETE`d |

The order is fixed: `id` first, then the table's own columns, then
`created_at`, `updated_at`, `is_active` as the last three. A natural key like
`setting.key` becomes a `UNIQUE` constraint rather than the primary key.

---

## The table is the source of truth

There is no fallback to a constant in code. Every setting exists as a row,
inserted once when the database is created; reading a setting is reading its
row, and that is the only place the value lives.

Two consequences worth being explicit about, because they are the whole cost of
this decision:

- **The seed is mandatory.** If a row is missing the app has nothing to fall
  back on, so bootstrap must insert every key when it creates the database, and
  a missing key at read time is a hard error (a clear "settings not
  initialised" message), not a silent default.
- **The services must actually read from the DB.** `constant/paths.py` is
  imported as module-level constants by `FileConverterService`,
  `TextEmbedderService` and `components/FileManager.py`. While that is true,
  editing a path in the UI changes a row that nothing reads. This refactor is
  no longer optional the way it was when code held the defaults — it is the
  work that makes the table mean anything.

In exchange, the design gets simpler: no merge of overrides over defaults, no
"reset to default" concept (the screen only has Save and Revert anyway), and
saving is a plain `UPDATE` rather than an upsert — which also removes the
collision between soft delete and `UNIQUE (key)` entirely.

---

## DDL

```sql
CREATE TABLE setting (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT    NOT NULL UNIQUE,
    value      TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
```

No extra index: `UNIQUE (key)` already gives the lookup index, and the table
holds ~10 rows, so an index on `is_active` would only be overhead.

`value` is stored as text; the caller converts where needed
(`int(get("embedding.results_per_query"))`).

### Timestamps are the application's job

No triggers. The `DEFAULT (strftime(...))` clauses stay as an insert-time
safety net, but the application supplies both values explicitly:

```python
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# insert (bootstrap only)
INSERT INTO setting (key, value, created_at, updated_at) VALUES (?, ?, ?, ?)

# update (Save)
UPDATE setting SET value = ?, updated_at = ? WHERE key = ? AND is_active = 1
```

Worth centralising that `now` helper in `DatabaseService` from the start, so
every later table stamps the identical format instead of each call site
inventing its own.

### What `is_active` means here

Rows are never deleted, but a settings row also never *needs* deactivating
during normal use — every key is one the app reads. Its real use is retirement:
when a setting is dropped from the app, its row is deactivated rather than
removed, so the history of what was configured survives. Reads filter
`WHERE is_active = 1` regardless.

---

## Seed rows

Inserted once, when the database is created:

| key | seed value | shown as |
| --- | --- | --- |
| `paths.input_dir` | `resources\files` | editable |
| `paths.output_dir` | `resources\converted_files` | editable |
| `paths.chroma_store` | `resources\my_chroma_store` | editable |
| `drive.folder_id` | `1VWtBJ4KClTf7v8ULab7VN-45QK-au0DO` | editable |
| `drive.service_account_file` | `C:/secrets/my_knowledge_drive_service_account.json` | editable |
| `drive.scope` | `https://www.googleapis.com/auth/drive.readonly` | read-only |
| `embedding.model` | `all-MiniLM-L6-v2` | read-only |
| `embedding.collection` | `my_knowledge_drive` | read-only |
| `embedding.results_per_query` | `5` | editable |

"Editable" vs "read-only" is a UI decision (`widgets.EditableRow` vs
`widgets.KvRow`, both in `view/widgets/blocks.py`), not a column — the table
stores all nine the same way.

**The three paths are seeded relative to the project root**, not as the absolute
strings `constant/paths.py` builds today. `BASE_DIR` is computed from
`__file__`, so an absolute seed would bake this machine's install location into
the database and break if the folder ever moves. `BASE_DIR` therefore stays in
code as "where the app is installed" — it is not configuration — and the app
resolves `BASE_DIR / value` at read time. That also means `paths.base_dir`
leaves the Settings screen as an editable row and becomes a plain
`widgets.KvRow` (`settings_view.py:198`).

---

## How the screens use it

**Settings** — the only writer:

- **Load** — `SELECT key, value FROM setting WHERE is_active = 1`.
- **Save** — one `UPDATE ... SET value, updated_at WHERE key = ?` per changed
  field, in a single transaction.
- **Revert** — no DB call. It discards unsaved edits in the form, so it just
  re-renders from the last loaded values.

**Library** and **Library Sync** — readers, through the cached
`settingService.get(...)`, not through SQL of their own:

| where | key | rendered as |
| --- | --- | --- |
| `library_view.py:46` | `embedding.collection` | the page subtitle, "N documents embedded in ..." |
| `library_sync_view.py:991,1007` | `embedding.collection` | the "Collection" row of the scan / run panel |
| `library_sync_view.py:1008,1226` | `embedding.model` | the "Embedding model" row of the run and confirm panels |
| `library_sync_view.py:1146` | `embedding.collection` | "Chroma collection ..." in the reset impact list |

Every one of those is read **inside `build()`**, so a saved setting shows up on
the other screens the next time they render, with no invalidation step. That is
the payoff of `SettingService` holding one process-wide cache, and it is why
`_wipes()` is a method rather than a module constant (`library_sync_view.py:1141`)
— a module constant would have frozen the collection name at import time.

---

## Decisions taken while building

- **Changing `paths.output_dir` or `embedding.collection`** saves normally but
  raises a warning toast telling you to run a reset, rather than blocking the
  edit. `DESTRUCTIVE_KEYS` in `settings_view.py` drives it.
- **Validation** rejects empty values and a non-numeric or below-1
  results-per-query, before anything reaches the database. It does *not* check
  that a directory or the service-account JSON exists — a missing credentials
  file now fails when `FileFetcherService` is constructed, which is a clear
  enough failure and keeps the settings screen usable while you fix the path.
- **`FileFetcherService` credentials moved from class level to `__init__`.**
  They were loaded at import time, which would have read a setting before the
  database was open, and made a missing key file break the import rather than
  the run.
- **`SettingService.initialise()` is explicit, called once per process at the
  top of the entry point** (`main.py:14`, before `ft.app()`), not a lazy check
  inside every `get`/`set`.
  The first design checked `self._initialised` on every `get_all()` and
  `set_many()` call; that meant every future DB-touching method would have to
  remember the same check, and paid for a branch that is only ever false after
  startup. Reading before `initialise()` now fails loudly
  (`sqlite3.OperationalError: no such table: setting`) instead of silently
  creating the table on first use - a clearer failure than a maintenance
  burden spread across every method.

## Still open

1. **Should the screen's grouping and labels come from the DB too?** Rendering
   Settings entirely from the table would need `group`, `label` and
   `display_order` columns. `settings_view.py` hardcodes all three today, which
   is fine while the set of settings is fixed.
2. **~~`ui.page_size`~~ — closed by the Library rewrite.** The 10/25/50
   dropdown it referred to no longer exists: the Library is a folder tree you
   drill into, not a paged list, so there is no page size to persist. What
   replaced it is genuinely session state — `library_filter` and
   `library_folders_open` in `AdminPortal.state` (`view/admin/shell.py:29-32`)
   — and it stays there. A filter that survived a restart would silently hide
   documents on the next open, and remembering which folders were expanded is
   not worth a table when the tree opens collapsed by design. **No UI
   preference belongs in `setting` today**; if one ever does, it wants its own
   table rather than sharing a source-of-truth table with configuration.
3. **Two portals open at once** each hold their own `SettingService` cache, so
   one will not see the other's save until it calls `reload()`. Harmless today
   (only the admin portal writes); worth revisiting if the user portal ever
   edits settings.

---

## Build order (done)

1. `constant/paths.py` → `BASE_DIR` and `DB_PATH` only; the three derived path
   constants are gone.
2. `services/DatabaseService.py` → connection context manager, pragmas and the
   `now()` helper. It holds no SQL.
3. `repository/SettingRepository.py` → the DDL and every statement:
   `initialise` (create + seed), `find_all_active`, `update_values`.
   `update_values` writes all keys or none, returning the keys it could not
   find rather than raising, so the SQL layer stays free of domain errors.
4. `constant/settings.py` + `services/SettingService.py` → keys, seed, and
   `get` / `get_int` / `get_path` / `get_all` / `set` / `set_many`, with a hard
   error on a missing key.
4. `FileConverterService`, `TextEmbedderService`, `FileFetcherService` and
   `components/FileManager.py` read through the shared `settings` instance.
5. `settings_view.py` Save/Revert wired, with unsaved edits held in
   `portal.state["settings_edits"]`.
