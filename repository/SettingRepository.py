"""Every SQL statement that touches the setting table.

Nothing above this layer writes SQL: SettingService handles path resolution,
errors and the all-settings cache, and calls in here for the data. Reads come
back as `Setting` models; the plain insert and update come from BaseRepository,
which is what stamps the audit timestamps.
"""

import logging

from constant.settings import SETTING_DEFAULT_VALUES
from model.Setting import Setting
from repository.BaseRepository import BaseRepository

logger = logging.getLogger(__name__)


class SettingRepository(BaseRepository):

    def initialise(self):
        """Creates the table if absent and seeds any key that has never existed."""
        with self.database_service.connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS setting (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    key          TEXT    NOT NULL UNIQUE,
                    value        TEXT    NOT NULL,
                    -- 'localtime', to match what BaseRepository stamps. These
                    -- defaults are only an insert-time net; the app supplies both.
                    created_date TEXT    NOT NULL
                                 DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
                    updated_date TEXT    NOT NULL
                                 DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
                    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
                )
            """)
            self._rename_legacy_date_columns(connection)
            self._set_default_value_if_not_exist(connection)

    def find_by_key_is_active(self, key, is_active):
        """The one row for `key` at that is_active, or None if there is none."""
        with self.database_service.connection() as connection:
            row = connection.execute(
                "SELECT * FROM setting WHERE key = ? AND is_active = ?",
                (key, is_active),
            ).fetchone()
        return Setting.from_row(row) if row else None

    def find_all_active(self):
        with self.database_service.connection() as connection:
            rows = connection.execute("SELECT * FROM setting WHERE is_active = 1").fetchall()
        return [Setting.from_row(row) for row in rows]

    def update_all(self, values):
        """Applies every change in one transaction, or none at all.

        Returns the keys that matched no active row; when that list is not
        empty nothing has been written.
        """
        with self.database_service.connection() as connection:
            rows = connection.execute("SELECT * FROM setting WHERE is_active = 1").fetchall()
            settings = {row["key"]: Setting.from_row(row) for row in rows}

            missing = [key for key in values if key not in settings]
            if missing:
                return missing

            for key, value in values.items():
                setting = settings[key]
                setting.value = str(value)
                # The open connection, so every row lands or none of them do.
                self.update(setting, connection)

        return []

    def _set_default_value_if_not_exist(self, connection):
        """Deactivated keys count as existing, so retiring one is not undone."""
        existing = {row["key"] for row in connection.execute("SELECT key FROM setting")}
        missing = [(key, value) for key, value in SETTING_DEFAULT_VALUES if key not in existing]
        if not missing:
            return

        for key, value in missing:
            self.save(Setting(key=key, value=value), connection)
        logger.info(f"Seeded settings: {', '.join(key for key, _ in missing)}")

    @staticmethod
    def _rename_legacy_date_columns(connection):
        """Brings a database made before the `_date` naming up to it.

        `CREATE TABLE IF NOT EXISTS` leaves an existing table alone, so a
        database seeded with `created_at`/`updated_at` still has those names
        and every statement here would fail against it.
        """
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(setting)")}
        if "created_at" not in columns and "updated_at" not in columns:
            return

        if "created_at" in columns:
            connection.execute("ALTER TABLE setting RENAME COLUMN created_at TO created_date")
        if "updated_at" in columns:
            connection.execute("ALTER TABLE setting RENAME COLUMN updated_at TO updated_date")
        logger.info("Renamed setting.created_at/updated_at to created_date/updated_date")
