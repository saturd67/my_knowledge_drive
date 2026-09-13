"""Every SQL statement that touches the drive_file table.

Nothing above this layer writes SQL: `DriveFileService` owns the errors and the
shape the callers want, and calls in here for the data. Reads come back as
`DriveFile` models; the plain insert and update come from BaseRepository, which
is what stamps the audit timestamps.
"""

import logging

from model.DriveFile import DriveFile
from repository.BaseRepository import BaseRepository

logger = logging.getLogger(__name__)


class DriveFileRepository(BaseRepository):

    def initialise(self):
        """Creates the table if it is absent. There is nothing to seed.

        Unlike the setting table this one starts empty: a row only means
        something once a download has produced the file it points at, so the
        rows arrive with the first reset or sync.
        """
        with self.database_service.connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS drive_file (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id  TEXT    NOT NULL UNIQUE,
                    drive_id     TEXT    NOT NULL,
                    -- 'localtime', to match what BaseRepository stamps. These
                    -- defaults are only an insert-time net; the app supplies both.
                    created_date TEXT    NOT NULL
                                 DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
                    updated_date TEXT    NOT NULL
                                 DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
                    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
                )
            """)
            # Every read is by document_id, and UNIQUE already indexes it - so
            # there is no second index to add here.

    def find_by_document_id(self, document_id):
        """The one active row for `document_id`, or None if there is none."""
        with self.database_service.connection() as connection:
            row = connection.execute(
                "SELECT * FROM drive_file WHERE document_id = ? AND is_active = 1",
                (document_id,),
            ).fetchone()
        return DriveFile.from_row(row) if row else None

    def find_all_active(self):
        with self.database_service.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM drive_file WHERE is_active = 1"
            ).fetchall()
        return [DriveFile.from_row(row) for row in rows]

    def save_all(self, drive_ids_by_document_id):
        """Writes every mapping in one transaction, or none of them.

        A run hands over hundreds of files at once, and a half-written mapping
        is worse than none: it would leave some documents linking to Drive and
        others not, with nothing on screen to say which.

        A document that is already mapped is updated rather than inserted
        twice - re-downloading a file keeps its row and restamps it, which is
        what `document_id UNIQUE` requires and what makes a repeat run cheap.
        Returns how many rows were written.
        """
        if not drive_ids_by_document_id:
            return 0

        with self.database_service.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM drive_file WHERE document_id IN "
                f"({', '.join('?' for _ in drive_ids_by_document_id)})",
                tuple(drive_ids_by_document_id),
            ).fetchall()
            existing = {row["document_id"]: DriveFile.from_row(row) for row in rows}

            for document_id, drive_id in drive_ids_by_document_id.items():
                drive_file = existing.get(document_id)
                if drive_file is None:
                    # The open connection, so every row lands or none of them do.
                    self.save(DriveFile(document_id=document_id, drive_id=drive_id),
                              connection)
                    continue
                drive_file.drive_id = drive_id
                drive_file.is_active = 1
                self.update(drive_file, connection)

        return len(drive_ids_by_document_id)

    def deactivate_missing(self, document_ids):
        """Soft-deletes every mapping whose document is not in `document_ids`.

        A reset rebuilds the collection from scratch, so a document that is no
        longer in it must stop claiming a Drive file - otherwise a stale row
        outlives what it described and links a document that is gone. Rows are
        deactivated rather than deleted, per the `is_active` convention.

        Returns how many rows were deactivated.
        """
        with self.database_service.connection() as connection:
            if not document_ids:
                cursor = connection.execute(
                    "UPDATE drive_file SET is_active = 0, updated_date = ? "
                    "WHERE is_active = 1",
                    (self.current_datetime(),),
                )
                return cursor.rowcount

            placeholders = ", ".join("?" for _ in document_ids)
            cursor = connection.execute(
                "UPDATE drive_file SET is_active = 0, updated_date = ? "
                f"WHERE is_active = 1 AND document_id NOT IN ({placeholders})",
                (self.current_datetime(), *document_ids),
            )
            return cursor.rowcount
