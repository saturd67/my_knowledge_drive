"""One reset run, owned by the portal so it outlives the screen.

A screen is built fresh on every navigation (`AdminPortal._fill_reader`), but
a reset takes minutes. If the run kept its state on the screen, navigating
away mid-run would leave the worker thread updating a control tree that is no
longer in the page. So the state lives here, `AdminPortal` holds one, and
whichever screen is showing attaches its redraw to `on_change`.

The run log is filled by a logging handler rather than by a callback the
services would have to call: all three workers log through `logging` under
`services.*` and nothing else, so attaching to that one logger for the length
of the run catches everything without touching them.
"""

from collections import deque

from services.library_reset_service.library_reset_service import (
    LibraryResetCancelled,
    LibraryResetService,
)
from view.admin.screens.library_sync.run_log_handler import MAX_LOG_LINES, RunLogHandler

STEP_COUNT = len(LibraryResetService.STEPS)


class LibraryResetRunner:

    def __init__(self):
        #: idle | running | done | cancelled | failed
        self.status = "idle"
        #: 0 before step 1; 5 while the last step runs. On a cancelled run it
        #: is the last step that finished, because the cancel is checked
        #: before `on_step` fires for the next one.
        self.step_number = 0
        #: The counts `start_reset` returned, once it has.
        self.results = None
        #: The exception text when `status` is `failed`.
        self.error = None
        self.lines = deque(maxlen=MAX_LOG_LINES)
        self.cancel_requested = False
        #: The showing screen's redraw, or None while no screen is showing.
        self.on_change = None
        #: The log panel's own update. Separate from `on_change` so a log line
        #: does not rebuild the whole screen hundreds of times a second.
        self.on_log = None

    # --- what the screen reads -----------------------------------------------

    @property
    def is_running(self):
        return self.status == "running"

    @property
    def is_idle(self):
        return self.status == "idle"

    @property
    def step_count(self):
        """Fixed, unlike the sync runner's - a reset is always the same six
        steps. Here so the header can read either runner the same way."""
        return STEP_COUNT

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
            # Finished, or the last step to finish before a cancel landed.
            return "done"

        # Above the step the run reached: never going to happen now.
        if self.status in ("cancelled", "failed"):
            return "skipped"
        return "pending"

    def summary(self):
        """One line for the section's pill, or None while idle."""
        if self.status == "running":
            if self.cancel_requested:
                return "Cancelling", "warning"
            return f"Step {self.step_number or 1} of {STEP_COUNT}", "primary"
        if self.status == "done":
            return "Done", "success"
        if self.status == "cancelled":
            return "Cancelled", "warning"
        if self.status == "failed":
            return "Failed", "danger"
        return "Idle", "neutral"

    # --- the run -------------------------------------------------------------

    def begin(self):
        self.status = "running"
        self.step_number = 0
        self.results = None
        self.error = None
        self.cancel_requested = False
        self.lines.clear()
        self.on_safe_change()

    def run(self):
        """The whole rebuild. Blocking - call it on a worker thread.

        Nothing here touches flet: the screen redraws through `on_change`,
        which is the one place the UI is reached from this thread.
        """
        run_log_handler = RunLogHandler(self)
        previous_level = run_log_handler.attach()

        try:
            results = LibraryResetService().start_reset(
                on_step=self.step_started,
                is_cancelled=lambda: self.cancel_requested,
            )
            self.handle_run_finish(results)
        except LibraryResetCancelled:
            self.handle_cancel_run()
        except Exception as error:
            self.handle_run_fail(error)
        finally:
            run_log_handler.detach(previous_level)

    def request_cancel(self):
        """Asks the run to stop. It is checked between steps, so the step
        already under way finishes first."""
        if not self.is_running:
            return
        self.cancel_requested = True
        self.on_safe_change()

    # --- what the service calls back into ------------------------------------

    def step_started(self, step_number, step_name):
        self.step_number = step_number
        self.on_safe_change()

    def handle_run_finish(self, results):
        self.status = "done"
        self.results = results
        # Every step ran, so say so rather than leaving it to whatever the
        # last `on_step` happened to set - the cards read this to decide that
        # nothing is still pending.
        self.step_number = STEP_COUNT
        self.on_safe_change()

    def handle_cancel_run(self):
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
