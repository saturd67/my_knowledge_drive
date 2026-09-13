"""The scan and the update it leads to, owned by the portal.

Same arrangement as `library_reset_runner.py`, and for the same reason: a
screen is rebuilt on every navigation while a run takes minutes, so the state
lives here, `AdminPortal` holds one, and whichever screen is showing attaches
its redraw to `on_change`.

Sync mode is two runs rather than one, and the second reads what the first
produced. That is the only real difference from the reset runner:

    scan    -> file_changes, which the review list renders and ticks
    update  -> results, from the changes that were still ticked

`file_changes` survives a finished scan on purpose, so navigating away and
back does not throw away a scan you have not applied yet. It is dropped the
moment a new scan starts, because a stale plan must never be applied - the
rule in plans/file-table.md.
"""

from collections import deque

from services.sync_planner_service.sync_planner_service import (
    SyncPlannerCancelled,
    SyncPlannerService,
)
from view.admin.screens.library_sync.run_log_handler import MAX_LOG_LINES, RunLogHandler

SCAN_STEP_COUNT = len(SyncPlannerService.SCAN_STEPS)
UPDATE_STEP_COUNT = len(SyncPlannerService.UPDATE_STEPS)


class LibrarySyncRunner:

    def __init__(self):
        #: idle | running | done | cancelled | failed
        self.status = "idle"
        #: scan | update - which of the two the last run was.
        self.run_type = "scan"
        #: 0 before step 1, then the step under way.
        self.step_number = 0
        #: What the last scan found. Kept after it finishes, so the review
        #: list survives navigating away and back.
        self.file_changes = []
        #: Whether a scan has ever finished in this session - the review list
        #: shows "nothing to do" only once there is a result to say it about.
        self.is_scanned = False
        #: The counts the last update returned.
        self.results = None
        self.error = None
        self.lines = deque(maxlen=MAX_LOG_LINES)
        self.cancel_requested = False
        self.on_change = None
        self.on_log = None

    # --- what the screen reads -----------------------------------------------

    @property
    def is_running(self):
        return self.status == "running"

    @property
    def is_idle(self):
        return self.status == "idle"

    @property
    def is_scanning(self):
        return self.is_running and self.run_type == "scan"

    @property
    def steps(self):
        """The step names of whichever run is showing."""
        if self.run_type == "update":
            return SyncPlannerService.UPDATE_STEPS
        return SyncPlannerService.SCAN_STEPS

    @property
    def step_count(self):
        return len(self.steps)

    @property
    def selected_changes(self):
        return [f for f in self.file_changes if f.is_selected and f.is_actionable]

    @property
    def actionable_changes(self):
        return [f for f in self.file_changes if f.is_actionable]

    @property
    def can_update(self):
        """Whether the Update button has anything to do."""
        return not self.is_running and bool(self.selected_changes)

    def step_status(self, index):
        """`pending` / `running` / `done` / `failed` / `skipped` for one card."""
        step_number = index + 1

        if step_number < self.step_number:
            return "done"

        if step_number == self.step_number:
            if self.status == "running":
                return "running"
            if self.status == "failed":
                # on_step fired, then the work under it raised.
                return "failed"
            return "done"

        if self.status in ("cancelled", "failed"):
            return "skipped"
        return "pending"

    def summary(self):
        """One line for the section's pill."""
        if self.status == "running":
            if self.cancel_requested:
                return "Cancelling", "warning"
            return f"Step {self.step_number or 1} of {self.step_count}", "primary"
        if self.status == "done":
            return "Done", "success"
        if self.status == "cancelled":
            return "Cancelled", "warning"
        if self.status == "failed":
            return "Failed", "danger"
        return "Idle", "neutral"

    def count_by_status(self):
        return SyncPlannerService.count_by_status(self.file_changes)

    def toggle(self, file_change):
        """Ticks or unticks one row. Blocked rows can never be ticked."""
        if not file_change.is_actionable or self.is_running:
            return
        file_change.is_selected = not file_change.is_selected
        self.on_safe_change()

    def select_all(self, is_selected):
        for file_change in self.actionable_changes:
            file_change.is_selected = is_selected
        self.on_safe_change()

    # --- the runs ------------------------------------------------------------

    def begin_scan(self):
        self._begin("scan")
        # A scan replaces the plan. Anything ticked from the last one described
        # a state that no longer holds, so it goes before the new one arrives.
        self.file_changes = []
        self.is_scanned = False
        self.results = None
        self.on_safe_change()

    def run_scan(self):
        """Blocking - call it on a worker thread."""
        self._run(lambda planner: self.handle_scan_finish(
            planner.start_scan(on_step=self.step_started,
                               is_cancelled=lambda: self.cancel_requested)
        ))

    def begin_update(self):
        self._begin("update")
        self.results = None
        self.on_safe_change()

    def run_update(self):
        """Blocking - call it on a worker thread."""
        # The list is read once, here, so a tick changed mid-run cannot alter
        # what this run was asked to do.
        picked_changes = list(self.selected_changes)
        self._run(lambda planner: self.handle_update_finish(
            planner.start_update(picked_changes, on_step=self.step_started,
                                 is_cancelled=lambda: self.cancel_requested)
        ))

    def request_cancel(self):
        """Asks the run to stop. Checked between steps, so the step already
        under way finishes first."""
        if not self.is_running:
            return
        self.cancel_requested = True
        self.on_safe_change()

    def _begin(self, run_type):
        self.status = "running"
        self.run_type = run_type
        self.step_number = 0
        self.error = None
        self.cancel_requested = False
        self.lines.clear()

    def _run(self, work):
        """The log handler, the three outcomes, and the tidy-up around them.

        Nothing in here touches flet: the screen redraws through `on_change`,
        which is the one place the UI is reached from this thread.
        """
        run_log_handler = RunLogHandler(self)
        previous_level = run_log_handler.attach()

        try:
            work(SyncPlannerService())
        except SyncPlannerCancelled:
            self.cancel_run_finished()
        except Exception as error:
            self.handle_run_fail(error)
        finally:
            run_log_handler.detach(previous_level)

    # --- what the service calls back into ------------------------------------

    def step_started(self, step_number, step_name):
        self.step_number = step_number
        self.on_safe_change()

    def handle_scan_finish(self, file_changes):
        self.status = "done"
        self.file_changes = file_changes
        self.is_scanned = True
        self.step_number = SCAN_STEP_COUNT
        self.on_safe_change()

    def handle_update_finish(self, results):
        self.status = "done"
        self.results = results
        self.step_number = UPDATE_STEP_COUNT
        # What was just applied is no longer a pending change, and the rows
        # would otherwise stay ticked and re-appliable. The next scan says
        # what the collection holds now.
        self.file_changes = []
        self.is_scanned = False
        self.on_safe_change()

    def cancel_run_finished(self):
        self.status = "cancelled"
        self.on_safe_change()

    def handle_run_fail(self, error):
        self.status = "failed"
        self.error = str(error) or type(error).__name__
        self.on_safe_change()

    def log(self, line):
        self.lines.append(line)
        if self.on_log is not None:
            self.on_log()

    def on_safe_change(self):
        if self.on_change is not None:
            self.on_change()

    def detach(self):
        """Called when the screen goes away - the run carries on regardless."""
        self.on_change = None
        self.on_log = None
