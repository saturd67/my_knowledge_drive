import logging
import os

from constant.paths import BASE_DIR
from constant.settings import RELATIVE_TO_BASE_DIR
from repository.SettingRepository import SettingRepository

logger = logging.getLogger(__name__)


class SettingNotFoundError(Exception):
    pass


class SettingService:
    """Reads and writes settings.

    There is no fallback to a value in code: a key that is missing or retired
    is an error, not a default. `DatabaseService.initialise()` must have run
    once, on app startup, before any read or write here - it is not checked on
    every call.

    Nothing is cached: every read is a query, so a value written anywhere is
    visible on the next call.
    """

    def __init__(self, setting_repository=None):
        self.setting_repository = setting_repository or SettingRepository()

    def find_active_by_key(self, key):
        """One active row, queried by key.

        Every call is a `SELECT`, so a caller reading the same key once per
        file in a loop should hoist it out of the loop.
        """
        setting = self.setting_repository.find_by_key_is_active(key, 1)
        if setting is None:
            raise SettingNotFoundError(
                f"Setting '{key}' is not in the database. "
                f"Delete {self.setting_repository.db_path} to rebuild it from the seed."
            )
        return setting.value

    def get_path(self, key):
        """Absolute path for a path setting, resolved against BASE_DIR."""
        value = self.find_active_by_key(key)
        if key in RELATIVE_TO_BASE_DIR and not os.path.isabs(value):
            return os.path.join(BASE_DIR, value)
        return value

    def update_all(self, values):
        """Writes every change in one transaction, or none of them."""
        if not values:
            return

        missing = self.setting_repository.update_all(values)
        if missing:
            raise SettingNotFoundError(
                f"Not in the database, nothing was saved: {', '.join(missing)}"
            )

        logger.info(f"Updated settings: {', '.join(values)}")


# Shared instance, so every caller reads and writes through one repository.
settingService = SettingService()
