from model.BaseModel import BaseModel


class Setting(BaseModel):
    """One row of the setting table: a key and the value it holds.

    `key` is UNIQUE, so it is the natural key - but `id` is still the identity,
    which is what BaseRepository.update() writes against.
    """

    TABLE_NAME = "setting"

    def __init__(self, key=None, value=None, id=None, created_date=None,
                 updated_date=None, is_active=1):
        super().__init__(id, created_date, updated_date, is_active)
        self.key = key
        self.value = value

    @staticmethod
    def from_row(row):
        """Build one from a sqlite3.Row - the only place these columns are read."""
        return Setting(
            key=row["key"],
            value=row["value"],
            id=row["id"],
            created_date=row["created_date"],
            updated_date=row["updated_date"],
            is_active=row["is_active"],
        )

    def columns(self):
        return {"key": self.key, "value": self.value}
