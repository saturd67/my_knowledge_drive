"""Feeding a run log from what the services already log.

Shared by both runs on this screen. The lines come from a logging handler
rather than from a callback the services would have to call: everything under
`services.*` logs through `logging` and nothing else, so attaching to that one
logger for the length of a run catches all of it without touching any worker.
"""

import logging

#: The logger the workers sit under. Not the root - that would pull in
#: chromadb, urllib3 and googleapiclient chatter that says nothing about the run.
LOGGED_MODULE = "services"

#: Nobody scrolls back further than this, and a run touching every file across
#: six steps would otherwise grow the list without a bound.
MAX_LOG_LINES = 500


class RunLogHandler(logging.Handler):
    """Feeds a runner's log from whatever the services log."""

    def __init__(self, runner):
        super().__init__(level=logging.INFO)
        self.runner = runner
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record):
        self.runner.log(self.format(record))

    def attach(self):
        """Puts this handler on the services logger and returns its old level.

        The level has to move too: those loggers are NOTSET, so their
        effective level comes from the root, which is WARNING by default and
        would drop every INFO line a run produces.
        """
        logger = logging.getLogger(LOGGED_MODULE)
        previous_level = logger.level
        logger.addHandler(self)
        logger.setLevel(logging.INFO)
        return previous_level

    def detach(self, previous_level):
        """Takes it off again. A handler left on a module logger outlives the
        run and would keep appending to a runner nothing is showing."""
        logger = logging.getLogger(LOGGED_MODULE)
        logger.removeHandler(self)
        logger.setLevel(previous_level)
