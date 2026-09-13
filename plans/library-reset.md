# Library reset

**Status: designed, not implemented.** The pipeline behind it is already
written and runnable; what is missing is everything between the confirm dialog
and the screen. Scope of this document: making the **Reset** mode of
`view/admin/screens/library_sync_view.py` actually run
`services/library_reset_service/library_reset_service.py`, show it running, and
survive the ways a desktop user will interfere with it.

**Out of scope:** the Sync mode (scan / diff / selective update). It needs a
`file` table and a planner service that do not exist yet; Reset needs neither,
which is why it goes first. Also out of scope: persisting a run to
`sync_run` — see [Still open](#still-open).

---

## What already exists

`LibraryResetService` is done, and it was written for exactly this call site:

```python
def start_reset(self, on_step=None, is_cancelled=None):
```

- It reads every path, the collection and the model from `settingService`
  (`library_reset_service.py:60-64`), so the screen passes nothing.
- It calls `on_step(step_number, step_name)` as each of the five steps starts
  (`library_reset_service.py:135-142`).
- It checks `is_cancelled()` at the same boundary and raises
  `LibraryResetCancelled`, leaving written work in place.
- It returns a `results` dict with seven counts: `downloaded`,
  `download_skipped`, `download_failed`, `converted`, `embedded`,
  `embed_skipped`, `embed_failed`. (`converted_images` and `convert_failed`
  went when conversion stopped reading images out as text.)
- `main()` (`library_reset_service.py:145`) already drives the whole thing from
  a terminal. **That is the reference implementation for this screen** — the UI
  version is the same sequence with the progress drawn instead of printed.

All three workers it drives log through the stdlib `logging` module and nothing
else — no `print`, no callbacks. That fact decides how the Run log is filled
(see [The run log](#the-run-log-is-a-logging-handler-not-a-new-callback)).

## What is missing

| where | today |
| --- | --- |
| `library_sync_view.py:100-101` | "Yes, reset" calls `page.pop_dialog()` and nothing else |
| `library_sync_view.py:311` `ResetStepsSection` | every card drawn pending, pill hardcoded `Idle` |
| `step_card.py:33-37` | icon and pill are literals — a card has no status to render |
| `library_sync_view.py:338` `RunLogSection` | permanent `EmptyState` |
| `library_sync_view.py:52-54` | `SOURCE_FILE_COUNT = 348`, `EMBEDDING_MODEL = "all-MiniLM-L6-v2"` — stand-ins |
| `library_sync_view.py:173` | "Last reset" hardcoded to "6 days ago" |
| — | no cancel, no error surface, no result summary |

---

## The central problem: a screen lives for one build

This is the thing to settle before writing any of the above, because it decides
where the state goes.

`AdminPortal._fill_reader()` (`admin_portal.py:55-59`) does:

```python
self.body_container.content = view_class().build()
```

A fresh `LibrarySyncView` on every navigation, and `BaseView`'s docstring is
explicit that "an instance lives for exactly one `build()`"
(`base_view.py:3-6`). A reset takes minutes. So:

> Click Reset, then click **Library** in the sidebar. The `LibrarySyncView` that
> started the run is discarded, but the worker thread is still holding a
> reference to it and still calling `.update()` on controls that are no longer
> in the page.

At best that raises; at worst it silently updates a detached tree and the run
appears to have vanished. Note that `LibrarySyncView.select_mode()` already
redraws in place rather than rebuilding the instance, so the mode switch is
safe — it is only *navigation* that drops the screen.

### The fix: the run belongs to the portal, not the screen

Introduce a small object that owns one run and outlives any screen:

```python
class LibraryResetRunner:
    """One reset, from dispatch to result. Owned by AdminPortal, so it
    outlives the screen that started it."""

    def __init__(self):
        self.status = "idle"        # idle | running | done | cancelled | failed
        self.step_number = 0        # 0 before step 1, 5 while the last runs
        self.results = None         # the dict start_reset returned
        self.error = None           # exception text when status == "failed"
        self.lines = []             # the run log, capped
        self.cancel_requested = False
        self.on_change = None       # the live screen's redraw, or None
```

`AdminPortal` holds one (`self.reset_runner = LibraryResetRunner()`), the same
way it already holds `self.index`. `LibrarySyncView` gets the portal passed in
and **renders from the runner** rather than owning any run state.

That requires one change to the shell: `_fill_reader()` builds screens with
`view_class()`, so either every screen accepts the portal, or `LibrarySyncView`
is special-cased. Prefer the former — `AdminSidebar` already takes the portal
(`admin_sidebar.py`), and `SearchSidebar` takes its `SearchView` for the same
reason. **`view_class(self).build()`, and `BaseView.__init__` accepts and stores
`portal`.** Three screens change signature; nothing else does.

`on_change` is the screen re-attaching itself:

- `LibrarySyncView.build()` sets `runner.on_change = self.refresh`.
- `AdminPortal._fill_reader()` sets `self.reset_runner.on_change = None`
  *before* building the new screen, so a navigated-away run keeps working with
  nowhere to draw and picks the screen back up when you return to it.

Navigating back mid-run then shows the run in progress, which is the behaviour
a user will expect and the reason to do it this way rather than by blocking
navigation.

---

## Threading

`page.run_thread(handler, *args)` exists in flet 0.86.5 and is the right tool —
`start_reset()` is blocking, synchronous, CPU- and IO-heavy, and must not be on
the UI thread.

```python
def _confirmed(self, page):
    page.pop_dialog()
    runner = self.portal.reset_runner
    if runner.status == "running":
        return                      # belt and braces; the button is disabled
    runner.begin()
    page.run_thread(self._run, page)

def _run(self, page):
    runner = self.portal.reset_runner
    handler = runner.attach_log_handler()
    try:
        results = LibraryResetService().start_reset(
            on_step=runner.step_started,
            is_cancelled=lambda: runner.cancel_requested,
        )
        runner.finish(results)
    except LibraryResetCancelled:
        runner.cancelled()
    except Exception as error:
        runner.failed(error)
    finally:
        runner.detach_log_handler(handler)
```

Every `runner.*` method sets state and then calls `on_change` if it is not
`None` — so there is exactly one place that touches flet from the worker
thread, rather than that concern being spread through the run.

`LibraryResetService()` is constructed **inside** the thread, not at dispatch:
its `__init__` only reads settings, but `FileEmbedderService.__init__`
(constructed at `library_reset_service.py:90`) builds a chroma client and loads
the SentenceTransformer model, which is seconds of work. Keeping the whole
pipeline behind the one boundary means nothing slow is ever on the UI thread.

---

## The run log is a logging handler, not a new callback

The three workers already log everything worth showing — entering a folder,
each failure, each batch of embeddings. Adding an `on_log` parameter to
`start_reset` would mean touching all three services to call it, and would
duplicate what `logging` already carries.

Instead the runner attaches a handler for the duration of the run:

```python
LOGGED_MODULES = "services"
MAX_LINES = 500

class RunnerLogHandler(logging.Handler):
    def emit(self, record):
        self.runner.log(self.format(record))
```

- Attach to the `services` logger, not the root — the root would pull in
  chromadb, urllib3 and googleapiclient chatter that says nothing about the
  run. All three workers use `logging.getLogger(__name__)` under `services.*`,
  so one `getLogger("services")` catches exactly the right set.
- Level `INFO`. The workers put per-file noise at `DEBUG` deliberately
  (`file_embedder_service.py:89`); a "Log
  level: verbose" toggle can lower it later if anyone wants it.
- **Cap `lines` at `MAX_LINES` with a `collections.deque(maxlen=...)`.** An
  unbounded list over a run that touches ~350 files across five steps is a leak,
  and nobody scrolls back 4,000 lines.
- Detach in a `finally`. A handler left on a module logger survives the run and
  would keep appending to a dead runner.

Rendering: replace the `EmptyState` in `RunLogSection` with a
`ft.ListView(auto_scroll=True)` of `Mono` lines when there are any, keeping the
`EmptyState` for `status == "idle"`. `auto_scroll` is what makes it feel live.

**Redraw rate is the risk here.** Calling `on_change` per log line means a full
screen rebuild hundreds of times a second during embedding. Two ways out:
have `runner.log()` append without firing `on_change`, and let a
`ft.Timer`-style periodic refresh pick lines up; or have the log view own its
own `update()` and leave `on_change` for step transitions only. **Prefer the
second** — it keeps the expensive rebuild tied to the five step boundaries,
where it is genuinely cheap, and the log is the only control that needs to move
between them.

---

## Step cards need a status

`StepCard.__init__(index, name, description, span)` renders a fixed pending
icon and a `Pill("pending", "neutral")` (`step_card.py:19,33-37`). Add a
`status` parameter, defaulting to `"pending"` so the Sync screen's
`ScanStepsSection` is unaffected:

| status | icon | pill | tone |
| --- | --- | --- | --- |
| `pending` | `RADIO_BUTTON_UNCHECKED_ROUNDED` | pending | neutral |
| `running` | `ft.ProgressRing(width=18, height=18)` | running | primary |
| `done` | `CHECK_CIRCLE_ROUNDED` | done | success |
| `failed` | `ERROR_ROUNDED` | failed | danger |
| `skipped` | `REMOVE_CIRCLE_OUTLINE_ROUNDED` | skipped | neutral |

The icon slot has to accept a control, not just an icon name, for the running
spinner. `ResetStepsSection` then derives each card's status from
`runner.step_number` and `runner.status`: below it `done`, equal to it
`running`, above it `pending`; `failed` on the current step when the run
failed, and everything above the current step `skipped` when it cancelled.

`skipped` exists so a cancelled run does not leave three cards sitting on
`pending`, which reads as "about to happen".

The section's `trailing` pill follows the run: `Idle` → `Running` (primary) →
`Done` (success) / `Cancelled` (neutral) / `Failed` (danger).

### Two drift traps to close while in here

1. **`RESET_STAGES` (`library_sync_view.py:43-50`) and
   `LibraryResetService.STEPS` (`library_reset_service.py:52-58`) are the same
   five names, written twice.** `on_step` hands the screen a `step_name` from
   the service, which the screen ignores in favour of its own copy. Same shape
   as the `SCREENS`/`NAV_ITEMS` alignment trap that was merged in
   `admin_sidebar.py`. Fix: `RESET_STAGES` keeps only the descriptions and
   zips them against `LibraryResetService.STEPS`, so the service names the
   steps and the screen only explains them.
2. **The descriptions hardcode `resources\files` and `resources\converted_files`**
   — both are editable settings. They should read
   `settingService.get(PATHS_INPUT_DIR)` at build time, the way
   `settings_view.py` does. A user who repoints `paths.output_dir` and is then
   told the reset will clear a folder it will not touch is being actively
   misled.

---

## Cancellation is co-operative, and honest about it

`is_cancelled()` is only checked at the *start* of each step
(`library_reset_service.py:137`). That has two consequences the UI must not
paper over:

- **Cancel does not stop the current step.** Pressing it during "Download from
  Drive" — realistically the longest step of the five — does nothing until the
  download finishes. A button that appears to do nothing for two minutes is
  worse than one that says what it is waiting for.
- **Cancel during the last step never takes effect at all**, because step 5 is
  the last thing `_start_step` guards. The run completes normally.

So: while `status == "running"` the reset button becomes **Cancel** (ghost,
danger tone). Pressing it sets `cancel_requested = True`, and the button then
renders disabled reading **"Cancelling…"** with the sub-text *"stops after the
current step"*. Do not fake responsiveness by flipping the status to
`cancelled` immediately — the work really is still running, and the screen
should say so.

Finer-grained cancellation means passing `is_cancelled` down into the three
workers' per-file loops. That is a service change, and it is deliberately not
in this plan — see [Still open](#still-open).

---

## The confirm dialog's four rows

All four are stand-ins today (`library_sync_view.py:139-178`):

| row | today | becomes |
| --- | --- | --- |
| Files to convert | `SOURCE_FILE_COUNT = 348` | count files under `settingService.get_path(PATHS_INPUT_DIR)`, computed when the dialog opens |
| Estimated duration | `"~5 min"` | drop it, or derive from the count — see below |
| Embedding model | `EMBEDDING_MODEL = "all-MiniLM-L6-v2"` | `settingService.get(EMBEDDING_MODEL)` — the constant shadows the setting key of the same name, which is its own bug |
| Last reset | `"6 days ago"` | needs `sync_run`; until that exists, render **"never"** |

**"Estimated duration" should be removed rather than guessed.** It depends on
Drive throughput and on how many source files there are to fetch, neither of
which is known before the run. (It used to hinge on images to OCR as well;
conversion no longer reads images, so the download dominates.) A number invented at ±10× is worse
than no row. Reinstate it once `sync_run` records real durations and it can be
"last reset took 6m 20s".

**"Files to convert" is a walk of the input folder on the UI thread.** ~350
files is fast enough to do inline when the dialog opens; if the folder is
missing, render "unknown" rather than raising — the dialog is not the place to
discover a bad path, and the run will report it properly.

`SOURCE_FILE_COUNT` and `EMBEDDING_MODEL` (`library_sync_view.py:52-54`) are
both deleted by this work. The second especially: `EMBEDDING_MODEL` is also the
name of the settings *key* imported from `constant/settings.py` elsewhere in
the codebase, so leaving a module constant with that name in a view is a
collision waiting to be imported by accident.

---

## Failure

`start_reset` has no internal error handling — the workers count their own
per-file failures into `results` and keep going, but anything structural
(missing service-account JSON, no network, an unwritable output folder, a
chroma error) propagates out. The `except Exception` in `_run` is therefore
load-bearing, not defensive padding.

On `failed`: the current step card goes `failed`, later cards `skipped`, the
section pill goes `Failed`, and the message goes in a **`NoticeBar` above the
step section**, matching what Settings now does per card. The log lines are
already in the runner and stay on screen — for a reset, the last twenty log
lines are usually more diagnostic than the exception text.

One known sharp edge worth a note in the code: `reset_collection()`
(`file_embedder_service.py:116`) calls `chroma_client.delete_collection()`,
which raises if the collection does not exist. On a genuinely first run —
which is exactly what the Reset screen advertises itself for, *"use it for a
first run"* (`library_sync_view.py:228`) — step 4 can fail on a store that has
never been written. **Verify this before implementing;** if it holds, the fix
belongs in `FileEmbedderService`, not in the view.

---

## Build order

1. `plans/library-reset.md` → this document.
2. `step_card.py` → add `status`, defaulting to `pending`. Isolated, and the
   Sync screen keeps rendering identically.
3. `view/admin/library_reset_runner.py` → `LibraryResetRunner`: state, the five
   transitions, the capped log deque, attach/detach of the handler. No flet
   imports beyond calling `on_change` — it is testable headlessly, which is how
   the step-status table above gets verified without a window.
4. `admin_portal.py` + `base_view.py` → screens are built as
   `view_class(self)`; the portal owns one runner and clears `on_change` on
   navigation.
5. `library_sync_view.py` → `_confirmed()` dispatches; the header button
   switches between Reset / Cancel / Cancelling; `ResetStepsSection` and
   `RunLogSection` render from the runner. Delete `SOURCE_FILE_COUNT` and
   `EMBEDDING_MODEL`, zip `RESET_STAGES` against `LibraryResetService.STEPS`,
   and read the two paths from settings.
6. A results summary — the nine counts from `results`, rendered as tiles under
   the step cards. Last, because it is the only piece with nothing depending on
   it.

Verify with a probe against a **temporary** input folder and chroma store, the
way the settings work was verified — a reset run against the real
`resources/` is not something to trigger from a test.

---

## Decisions taken while designing

- **The run state lives on `AdminPortal`, not on the screen.** The alternative
  — blocking navigation while a run is in progress — is less code, but it locks
  a user out of the app for minutes because they clicked a button, and it does
  not survive the window being resized into a rebuild. Putting it on the portal
  costs one constructor argument on three screens.
- **The run log comes from `logging`, not from a new service callback.** The
  services already log everything the panel would show, and a callback
  parameter would have to be threaded through the downloader, the converter and
  the embedder to say the same thing twice.
- **`on_step` only fires five times, and that is accepted.** Steps 1, 3 and 5
  are minutes long with no progress within them. The log is what shows life
  during a step; a per-file progress callback is a service change, and the
  step cards would still only move five times. Revisit if the log turns out not
  to be enough.
- **"Estimated duration" is deleted rather than approximated.** A fabricated
  number in a confirmation dialog for a destructive, irreversible operation is
  the one place a guess is least excusable.
- **Cancel stays co-operative and says so.** Killing the thread mid-download
  would leave a half-written file tree with no record of where it stopped, and
  Python has no safe thread kill anyway.

## Still open

1. **Nothing is persisted.** A completed reset leaves no record — close the
   window and it never happened. That is `sync_run`
   ([`sync-run-table.md`](sync-run-table.md)), whose own *Still open* item 5
   names this screen as the missing writer. This plan deliberately ships
   without it: an in-memory run that works is more useful than a persisted run
   that does not exist, and the runner's `results` dict maps cleanly onto the
   columns when the table arrives. **"Last reset" reads "never" until then.**
2. **Per-file cancellation.** Requires `is_cancelled` inside the three workers'
   loops. Worth doing when a run against the real Drive folder shows how long
   step 1 actually blocks for.
3. **Two windows can each start a reset.** The runner is per-portal, so a
   second window has its own, and both would write the same folders. Same open
   question as `sync-run-table.md` item 4, and the same answer for now: the
   damage is in the pipeline, not in the screen.
4. **The Run log's copy button** (`library_sync_view.py:345`) is unwired, along
   with the copy buttons in Settings — flet 0.86.5 has no `page.set_clipboard`.
   One problem, four call sites, its own small piece of work.
5. **Sync mode is still presentation-only.** Reset was picked first because its
   service exists; the scan path needs a `file` table and a planner service
   before any of its UI can be wired.
