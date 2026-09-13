import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from constant.paths import DB_PATH

logger = logging.getLogger(__name__)


class DatabaseService:
    """Connection handling only - the SQL lives in repository/.

    The audit timestamps are stamped by BaseRepository, which is what knows
    when each column is written.
    """

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def initialise(self):
        """Creates and seeds every table. Called once, on app startup.

        A table added later joins the list below and nothing else changes -
        each repository still owns its own DDL, seed and migrations, and this
        only decides that they all run, against this database, in this order.
        Order matters once a table references another: a child table has to be
        created after the parent it points at.

        Safe to call more than once - every repository's `initialise` is.
        """
        # Imported here rather than at the top: every repository reaches
        # DatabaseService through BaseRepository, so a module-level import
        # would be a cycle.
        from repository.DriveFileRepository import DriveFileRepository
        from repository.SettingRepository import SettingRepository

        repositories = [
            SettingRepository(self),
            DriveFileRepository(self),
            # FileRepository(self),          # plans/file-table.md
            # SyncRunRepository(self),       # plans/sync-run-table.md
            # SyncRunFileRepository(self),   # after SyncRunRepository - it has the parent id
        ]
        for repository in repositories:
            repository.initialise()

        logger.info(f"Database ready: {self.db_path}")

    @contextmanager
    def connection(self):
        """Commits on success, rolls back on error, always closes."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()
