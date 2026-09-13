"""The insert and the update every repository shares.

`save` stamps both audit timestamps; `update` stamps only `updated_date`, so
the moment a row was created survives every later edit. Both take a model and
write it back, so the caller gets the id and the timestamps that were used.

Both also accept an already-open connection. A repository that has to write
several rows as one unit passes its own, and the writes stay all-or-nothing;
called without one, each does its own connection and commits on its own.
"""

import logging
from contextlib import contextmanager
from datetime import datetime

from services.DatabaseService import DatabaseService

logger = logging.getLogger(__name__)

#: The one shape every audit column is stamped with. Fixed width and
#: biggest-unit-first, so a TEXT column still sorts chronologically. No `Z`
#: suffix - that means UTC, and these are local.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"


class BaseRepository:

    def __init__(self, database_service=None):
        self.database_service = database_service or DatabaseService()

    @property
    def db_path(self):
        return self.database_service.db_path

    def initialise(self):
        """Create this repository's table, and seed it if it needs seeding.

        `DatabaseService.initialise()` calls this on every repository at
        startup, so it has to be safe to run against a database that already
        has the table.
        """
        raise NotImplementedError

    @staticmethod
    def current_datetime():
        """The machine's local time, for the audit columns."""
        return datetime.now().strftime(TIMESTAMP_FORMAT)

    def save(self, model, connection=None):
        """INSERT one row, with created_date and updated_date both set to now."""
        current_datetime = self.current_datetime()
        model.created_date = current_datetime
        model.updated_date = current_datetime

        values = {
            **model.columns(),
            "created_date": model.created_date,
            "updated_date": model.updated_date,
            "is_active": model.is_active,
        }
        # The table and column names come from the model class, never from
        # anything typed in - only the values are ever bound.
        statement = (
            f"INSERT INTO {model.TABLE_NAME} ({', '.join(values)}) "
            f"VALUES ({', '.join('?' for _ in values)})"
        )
        with self._connection(connection) as open_connection:
            model.id = open_connection.execute(statement, tuple(values.values())).lastrowid
        return model

    def update(self, model, connection=None):
        """UPDATE one row by id, restamping updated_date and nothing else.

        `created_date` is not in the statement at all, so an edit cannot move
        it even by accident.
        """
        model.updated_date = self.current_datetime()

        values = {
            **model.columns(),
            "updated_date": model.updated_date,
            "is_active": model.is_active,
        }
        assignments = ", ".join(f"{name} = ?" for name in values)
        statement = f"UPDATE {model.TABLE_NAME} SET {assignments} WHERE id = ?"

        with self._connection(connection) as open_connection:
            open_connection.execute(statement, (*values.values(), model.id))
        return model

    @contextmanager
    def _connection(self, connection=None):
        """Join the caller's transaction when handed one, or open our own."""
        if connection is not None:
            yield connection
            return
        with self.database_service.connection() as own_connection:
            yield own_connection
