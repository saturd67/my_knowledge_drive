from model.BaseModel import BaseModel


class DriveFile(BaseModel):
    """One row of the drive_file table: a document, and the Drive file it came from.

    The mapping the collection cannot hold. `FileEmbedderService` sets the
    Chroma document id to the file's path under the converted folder, so
    nothing in the collection knows which Drive file produced it - and a Drive
    link needs exactly that. This table is where the two are kept together.

        document_id  resources\\converted_files\\Python\\Async.md, relative
        drive_id     the Drive file id, from the download that wrote it

    `document_id` is UNIQUE, so it is the natural key - but `id` is still the
    identity, which is what BaseRepository.update() writes against.

    Deliberately only the two: this is a lookup, not the `file` registry in
    plans/file-table.md. That one records what a scan saw and what an update
    did, and is a bigger thing that can arrive later without disturbing this.
    """

    TABLE_NAME = "drive_file"

    def __init__(self, document_id=None, drive_id=None, id=None, created_date=None,
                 updated_date=None, is_active=1):
        super().__init__(id, created_date, updated_date, is_active)
        self.document_id = document_id
        self.drive_id = drive_id

    @staticmethod
    def from_row(row):
        """Build one from a sqlite3.Row - the only place these columns are read."""
        return DriveFile(
            document_id=row["document_id"],
            drive_id=row["drive_id"],
            id=row["id"],
            created_date=row["created_date"],
            updated_date=row["updated_date"],
            is_active=row["is_active"],
        )

    def columns(self):
        return {"document_id": self.document_id, "drive_id": self.drive_id}
