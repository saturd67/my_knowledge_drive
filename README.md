# MyKnowledgeDrive

MyKnowledgeDrive turns a folder of personal notes on Google Drive (docx files,
screenshots, code snippets, cheat sheets, etc.) into a locally searchable
knowledge base. It converts everything to plain text, embeds it into a local
vector database, and gives you a small desktop app to semantically search
across it — picking a result jumps straight to the file on Google Drive.

It's a single-user, local-first tool: everything runs on your machine, the
only network calls are to the Google Drive API to resolve file IDs.

## How it works

The pipeline has three stages, plus a Flet desktop UI with two "portals" on top:

```
resources/files/          resources/converted_files/    resources/my_chroma_store/
(local mirror of a             (plain .txt per              (Chroma vector DB,
 Drive folder)                  source file)                 one embedding/file)

   DocFile (.docx)   ──┐
   ImageFile (image)  ─┼──  FileConverterService  ──►  TextEmbedderService  ──►  query()
   OtherFile (code/    │      (components/                (sentence-transformers        │
    text/config)      ─┘       FileManager.py)              "all-MiniLM-L6-v2")          │
   UnknownFile (skip)                                                                    ▼
                                                                                    user portal UI
FileFetcherService walks the Drive folder (read-only) to map                     search → pick file
each local file to its Drive file ID + relative path, so                          → opens in Drive
Chroma document IDs double as "open in Drive" links.
```

1. **Convert** — `resources/files/` is a local mirror of a specific Google
   Drive folder (same folder/file names and structure). `FileConverterService`
   walks it and converts every file to plain text under
   `resources/converted_files/`, dispatching by type via
   `OutputFileFactory` in `components/FileManager.py`:
   - `.docx` → HTML (via `mammoth`) → text. Embedded images are dropped, never
     read out as text.
   - images (`image/*`) → not converted, so never embedded.
   - code/config/text files (`.py`, `.js`, `.json`, `.html`, `.xml`, `.txt`,
     `.bat`, `.java`, `.iml`, `.gitignore`) → read as-is.
   - anything else is skipped. `existing_file_types` documents which MIME
     types fall into which bucket.
2. **Fetch IDs** — `FileFetcherService` recursively lists a Drive folder
   (via a read-only service account) and returns each file's Drive ID plus
   its relative path, so local converted files can be matched back to a
   Drive ID and a "open this file" link.
3. **Embed** — `TextEmbedderService` embeds every converted `.txt` with
   `sentence-transformers` (`all-MiniLM-L6-v2`) into a persistent local
   `chromadb` collection (`resources/my_chroma_store/`), using the matched Drive file
   ID as the Chroma document ID and the relative path as label metadata.

## Project layout

```
my_knowledge_base_portal.py  Flet entry point for the desktop UI (both portals)
view/
  main.py                 Front door: `main` (Flet target) and `start(page, portal)`
  theme.py                Palette, spacing/radius tokens, the Flet theme (light only)
  portal_rail.py          Far-left rail that swaps between the admin and user portals
  widgets.py              Shared presentational controls (cards, pills, log console, ...)
  mock_data.py            Placeholder data the screens render from
  admin/                  Admin shell + Library/Library Sync/Settings screens
  user/                   User shell + search screen
components/
  FileManager.py          OutputFile subclasses (DocFile/ImageFile/OtherFile/UnknownFile) + factory
constant/
  paths.py                BASE_DIR (install root) and DB_PATH
  settings.py             Setting keys and the values the database is seeded with
repository/
  SettingRepository.py    Every SQL statement for the setting table
services/
  DatabaseService.py      SQLite connection and pragmas (no SQL of its own)
  SettingService.py       Setting lookups, caching and path resolution
                          (shared `settings` instance)
  FileFetcherService.py   Google Drive API: recursive (id, relative path) listing
  FileConverterService.py Orchestrates resources/files -> resources/converted_files
  TextEmbedderService.py  Chroma collection: embed / reset / check / query
resources/
  files/                  Local mirror of the Drive folder (gitignored, input)
  converted_files/        Converted plain-text output (gitignored, generated)
  my_chroma_store/        Chroma's persistent vector DB files (gitignored, generated)
  knowledge_drive.db      SQLite database (gitignored, generated on first run)
existing_file_types       Reference notes: MIME type -> conversion pipeline
run_user_portal_ui.bat    Windows launcher for my_knowledge_base_portal.py
plans/                    Design docs, one per table/feature (settings-table.md is implemented)
```

## Prerequisites

- Python 3.12 (a `.venv` is already set up in the repo).
- A Google Cloud **service account** with read-only access to the target
  Drive folder, with its JSON key saved at
  `C:/secrets/my_knowledge_drive_service_account.json`. That path and the
  target folder id are settings — seeded into `resources/knowledge_drive.db`
  on first run and editable from the admin portal's Settings screen.
- `flet==0.28.3` and `flet-desktop==0.28.3` (already installed in `.venv`) —
  required to run the app.

## Usage

```
run_user_portal_ui.bat
```

**Settings is wired to the database; every other screen is still presentation
only** — they render from `view/mock_data.py`, and their actions show a "not
wired up yet" toast marked with a `TODO` pointing at the service call they
should eventually make.

One launcher covers both portals: it opens on the user portal, and a narrow
rail down the far-left edge switches to the admin portal in place.

- **Admin UI** — sidebar with three screens: *Library* (stat cards plus a
  filterable, paginated table of `id`/`label`), *Library Sync* (one screen with
  a mode switch — sync shows the step list, run summary and log; reset swaps in
  the danger banner, impact breakdown, type-`RESET`-to-confirm gate and
  confirmation dialog), *Settings* (reads and writes the `setting` table —
  editable paths, Drive config and results-per-query, with per-section
  Save/Revert; model and collection name are shown read-only).
- **User UI** — a search-history sidebar on the left, a centred landing screen,
  and the query field docked along the bottom; submitting swaps the landing
  screen for a ranked result list showing relevance and cosine distance,
  alongside a detail panel with the Drive id, converted-text preview and an
  "Open in Google Drive" action.

The *Library Sync* screen carries a small **Preview** dropdown so the idle /
running / completed states can be reviewed while the actions are still stubs —
remove it once the real logic is wired in.
The search screen has "searching" and "no results" states built in
(`view/user/search_view.py`) that are unreachable until the query is wired up.

### The operations behind the admin screens

These are implemented in the services layer and are what the *Library Sync*
and *Library* screens need to be wired to:

- **Sync** — the everyday option. `FileConverterService.sync_convert_files()`
  reconverts only files whose local mtime is newer than their existing
  converted `.txt` (or that have no converted `.txt` yet), then
  `TextEmbedderService.sync_collection()` diffs the Drive listing against the
  Chroma collection by `modifiedTime` to add new files, upsert changed ones,
  and delete ones no longer on Drive. Logs a summary of added/updated/
  removed/unchanged counts.
- **Reset** — `FileConverterService.start_convert_files()` plus
  `TextEmbedderService.reset_collection()` and `embed_collection()` wipe
  `resources/converted_files/` and the Chroma collection, then reconvert every
  file in `resources/files/` and re-embed from scratch. Use this for a clean
  rebuild (e.g. first run, or if the collection is suspected to be out of sync).
- **Check** — `TextEmbedderService.check_total_collection()` and
  `check_collection(page)` give the total embedded document count and a
  paginated list of `id: label` entries.
- **Search** — `TextEmbedderService.query(text)` returns the top matches; each
  result's id is a Drive file id, so `https://drive.google.com/file/d/<id>`
  opens the source file.

## Known limitations

- `resources/files/` must be kept in sync with the Drive folder manually
  (e.g. via Google Drive for Desktop) — nothing in this repo downloads file
  content from Drive, only metadata (id + path). **Sync** only
  detects changes already present in `resources/files/` and on Drive; it
  doesn't pull new file content from Drive itself.
