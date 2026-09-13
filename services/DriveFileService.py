"""Which Drive file a document came from.

`FileEmbedderService` sets the Chroma document id to the file's path under the
converted folder, so the collection carries no Drive file id and a Drive link
cannot be built from it. The download is the only moment both are known at
once, so that is where the mapping is recorded; this is where it is read back.

A missing mapping is not an error. Only a run that wrote rows can have them,
so every document embedded before this table existed - and every document
whose row a later reset deactivated - reads back as None, and the screen falls
back rather than breaking.
"""

import logging

from repository.DriveFileRepository import DriveFileRepository

logger = logging.getLogger(__name__)


class DriveFileService:

    def __init__(self, drive_file_repository=None):
        self.drive_file_repository = drive_file_repository or DriveFileRepository()

    def find_drive_id(self, document_id):
        """The Drive file id behind `document_id`, or None when it is unmapped.

        Every call is a `SELECT`, so a caller reading one per row in a listing
        should use `find_all_drive_ids()` instead.
        """
        drive_file = self.drive_file_repository.find_by_document_id(document_id)
        return drive_file.drive_id if drive_file else None

    def find_all_drive_ids(self):
        """document_id -> drive_id for every mapping, in one query."""
        return {
            drive_file.document_id: drive_file.drive_id
            for drive_file in self.drive_file_repository.find_all_active()
        }

    def save_all(self, drive_ids_by_document_id):
        """Records what a run downloaded, in one transaction or not at all."""
        if not drive_ids_by_document_id:
            return 0

        written_row_count = self.drive_file_repository.save_all(drive_ids_by_document_id)
        logger.info(f"Mapped {written_row_count} document(s) to their Drive file")
        return written_row_count

    def deactivate_missing(self, document_ids):
        """Retires the mappings for documents that are no longer embedded."""
        deactivated_row_count = self.drive_file_repository.deactivate_missing(document_ids)
        if deactivated_row_count:
            logger.info(f"Retired {deactivated_row_count} stale Drive mapping(s)")
        return deactivated_row_count


# Shared instance, so every caller reads and writes through one repository.
driveFileService = DriveFileService()
