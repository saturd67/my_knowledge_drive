"""The four columns every table in this project carries.

The convention is written down in plans/settings-table.md: `id` first, then the
table's own columns, then `created_date`, `updated_date` and `is_active` last.
Timestamps end `_date` and are written by the application rather than by a
trigger - `BaseRepository` is what stamps them.
"""


class BaseModel:

    #: The table rows of this model live in. Every subclass sets it.
    TABLE_NAME = None

    def __init__(self, id=None, created_date=None, updated_date=None, is_active=1):
        #: None until BaseRepository.save() has inserted the row.
        self.id = id
        #: Set once, on insert, and never rewritten.
        self.created_date = created_date
        #: Restamped by every BaseRepository.update().
        self.updated_date = updated_date
        #: Soft delete - rows are deactivated, never DELETEd.
        self.is_active = is_active

    def columns(self):
        """Column -> value for this model's own columns.

        The audit columns are deliberately not in here: BaseRepository adds
        them, because it is what decides when each one is written.
        """
        raise NotImplementedError
