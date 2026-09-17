r"""The base class every library file type extends.

A library file is one file on its way into the library: how Drive gives it to
us, and how its text is split into the chunks that are embedded. One subclass
per file type, each in its own file in this directory, all built by
LibraryFileFactory:

    GoogleDocFile    exported from Drive as markdown (.md)   split as markdown
    DocxFile         converted to markdown (.md)             split as markdown
    MarkdownFile     .md / .markdown, byte for byte          split as markdown
    PlainTextFile    .txt, byte for byte                     split line by line
    PdfFile          .pdf, byte for byte                     nothing to split
    UnsupportedFile  skipped                                 nothing to split

The two halves need different things. Downloading needs the Drive service and
the file's id. Splitting needs neither - it reads the converted copy, which is
on disk by then - so the converter builds its file from a path alone
(`LibraryFileFactory.get_local_file`) and never calls `download`.

Splitting is the same for every type once the text is read into lines, so it
lives here; reading the lines (`_parse`) is each type's own. Every chunk fits
all-MiniLM-L6-v2's window, which reads only the first 256 tokens it is given:

    Java\Spring Boot\Spring Security\Spring Security.md     <- the path
    <blank>
    # Spring Security                                        <- the text, with its
    Spring Security is a framework that ...                     headings where they
    ## Authentication                                           stand, up to the
    ...                                                         budget
    <!-- chunk -->
    <blank>
    Java\Spring Boot\Spring Security\Spring Security.md     <- the path again
    Spring Security > Authentication                         <- the headings the
    <blank>                                                     chunk starts under
    ...the text carries on

Every chunk opens with the path, so where a note is filed counts towards
finding any part of it, and then with the headings above where it starts, so a
passage from the middle of a section still says which section it is. A type
without headings - plain text - heads every chunk with the path alone.

Chunks break between words, never inside one, and a heading always shares a
chunk with the first word under it, so no chunk ends on the title of a section
that starts in the next.
"""

import io
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

from services.file_embedder_service.file_embedder_service import FileEmbedderService

logger = logging.getLogger(__name__)


class LibraryFile(ABC):
    """A single Drive file: how it is written to disk, and how its text is split into chunks."""

    #: all-MiniLM-L6-v2's window, [CLS] and [SEP] included.
    MAX_TOKENS = 256

    #: [CLS] and [SEP], which the model adds around every input.
    SPECIAL_TOKEN_COUNT = 2

    #: Between a chunk's header - the path, and the headings it starts under -
    #: and its text. A blank line so the header cannot run into the first line
    #: and read as one, and so the header can be found again to take it off.
    HEADER_SEPARATOR = "\n\n"

    #: Between the headings on the second line of a chunk's header.
    HEADING_PATH_SEPARATOR = " > "

    #: A "word" longer than this is a URL or a base64 blob, not language.
    MAX_WORD_LENGTH = 60

    #: `<!--` - never kept as a word, so no line of a chunk can read as the
    #: separator between chunks. See `_words`.
    SEPARATOR_OPENING_WORD = FileEmbedderService.CHUNK_SEPARATOR.split()[0]

    def __init__(self, drive_service, file_id, name, mime_type, target_dir):
        self.drive_service = drive_service
        self.file_id = file_id
        self.name = name
        self.mime_type = mime_type
        self.target_dir = Path(target_dir)

    # --- downloading ---------------------------------------------------------

    def download(self):
        """Writes the file byte for byte, name unchanged. Returns False when nothing was written.

        What most types want. The ones that convert on the way - a Google Doc,
        a .docx - or that are skipped override it."""
        destination_path = self.get_output_file_path()
        logger.info(f"Downloading: {destination_path}")
        self._write(destination_path, self._get_media())
        return True

    def get_output_file_path(self):
        """Where this file lands - same name and extension unless overridden."""
        return self.target_dir / self.name

    def _get_media(self):
        """Raw bytes of an uploaded file."""
        request = self.drive_service.files().get_media(fileId=self.file_id, supportsAllDrives=True)
        return self._read_stream(request)

    def _export(self, mime_type):
        """Bytes of a Google-native file exported to `mime_type`."""
        request = self.drive_service.files().export_media(fileId=self.file_id, mimeType=mime_type)
        return self._read_stream(request)

    @staticmethod
    def _read_stream(request):
        buffer = io.BytesIO()
        media_io_base_download = MediaIoBaseDownload(buffer, request)
        is_done = False
        while not is_done:
            status, is_done = media_io_base_download.next_chunk()
            if status:
                logger.debug(f"  {int(status.progress() * 100)}%")
        return buffer.getvalue()

    def _write(self, destination_path, content):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with open(destination_path, "wb") as file:
            file.write(content)

    # --- splitting -----------------------------------------------------------

    def split(self, document_id, text, token_counter):
        """`text` as chunks that each fit the window, in order.

        Each chunk is its header - the path, then the headings it starts under
        - followed by as much of the text as the window has room for, and the
        next chunk carries on where it stopped. A file with no text once the
        markup is out is one chunk holding the path alone.

        `token_counter` is handed in rather than built here: it loads the
        model's tokenizer, which one conversion run shares across every file.

        A unit that is bigger than the window on its own - a heading hundreds
        of words long - still gets a chunk, and the model reads what fits of
        it: splitting a heading would name the section after half a title.
        """
        budget_count = LibraryFile.MAX_TOKENS - LibraryFile.SPECIAL_TOKEN_COUNT
        chunks = []
        chunk_header = document_id
        chunk_pieces = []
        used_token_count = 0

        for unit in self._units(text, token_counter):
            unit_token_count = sum(piece["token_count"] for piece in unit)
            if chunk_pieces and used_token_count + unit_token_count > budget_count:
                chunks.append(self._join(chunk_header, chunk_pieces))
                chunk_pieces = []

            if not chunk_pieces:
                # A chunk is named for the section its first piece is in.
                chunk_header = self._header(document_id, unit[0]["heading_path"], token_counter)
                used_token_count = token_counter.count(chunk_header)

            chunk_pieces += unit
            used_token_count += unit_token_count

        chunks.append(self._join(chunk_header, chunk_pieces))
        return chunks

    @abstractmethod
    def _parse(self, text):
        """(heading level, text) per line of `text`, in order; level 0 for body.

        The one part of splitting a type has to supply: which lines are
        headings, and what is left of each line once its format's markup is
        out. Words need no filtering here - `_units` drops the ones not worth a
        token, the same way for every type."""

    def _units(self, text, token_counter):
        """The text as the units chunks are packed from, in order.

        A unit is a list of pieces that must share a chunk. A piece is one body
        word, or one whole heading line. Each carries the line it came from, so
        a chunk can put its words back into lines, and the titles of the
        headings it sits under, so a chunk that starts on it can name its
        section.

        Most units are a single word. A heading is held back and joins the
        word after it - only the heading straight above the text, so a run of
        empty sections cannot grow one unit past the window.

        Tokens are counted a piece at a time: WordPiece splits on whitespace
        before anything else, so a word's tokens are the same alone as in a
        sentence, and the running total is exact. Each distinct piece is
        counted once - a long file repeats most of its words, and the tokenizer
        is the slow part of a run.
        """
        token_counts_by_text = {}
        units = []
        #: (level, title) of every heading above the current line, outermost first.
        headings = []
        held_heading_piece = None

        for line_index, (level, line) in enumerate(self._parse(text)):
            line = " ".join(self._words(line))
            if not line:
                continue

            if level:
                if held_heading_piece is not None:
                    units.append([held_heading_piece])
                # A heading closes every section at its own level or deeper.
                headings = [(heading_level, title) for heading_level, title in headings if heading_level < level]
                held_heading_piece = self._piece(
                    f"{'#' * level} {line}", line_index, [title for _, title in headings],
                    token_counter, token_counts_by_text,
                )
                headings.append((level, line))
                continue

            heading_path = [title for _, title in headings]
            for word in line.split():
                word_piece = self._piece(word, line_index, heading_path, token_counter, token_counts_by_text)
                if held_heading_piece is None:
                    units.append([word_piece])
                else:
                    units.append([held_heading_piece, word_piece])
                    held_heading_piece = None

        if held_heading_piece is not None:
            units.append([held_heading_piece])
        return units

    def _words(self, line):
        """The words of `line` worth a token.

        Not a "word" longer than MAX_WORD_LENGTH - a URL or a base64 run, which
        costs tokens and means nothing - and never `<!--`, the opening word of
        `FileEmbedderService.CHUNK_SEPARATOR`. Without it no line of a chunk can
        read as the separator, whatever format the text came from: markdown
        loses its HTML comments to `_parse` anyway, but a .txt keeps them.
        """
        return [
            word for word in line.split()
            if len(word) <= LibraryFile.MAX_WORD_LENGTH and word != LibraryFile.SEPARATOR_OPENING_WORD
        ]

    def _piece(self, piece_text, line_index, heading_path, token_counter, token_counts_by_text):
        if piece_text not in token_counts_by_text:
            token_counts_by_text[piece_text] = token_counter.count(piece_text)
        return {
            "text": piece_text,
            "line_index": line_index,
            "heading_path": heading_path,
            "token_count": token_counts_by_text[piece_text],
        }

    def _header(self, document_id, heading_path, token_counter):
        """The path, then the headings a chunk starts under as `A > B > C`.

        Held to half the window, so a deep outline cannot leave a chunk no room
        for text. The outermost headings go first - the innermost says the most
        about the passage, and the outermost is usually the file's own title,
        which the path already has - and the path stays whatever it costs.
        """
        max_header_token_count = (LibraryFile.MAX_TOKENS - LibraryFile.SPECIAL_TOKEN_COUNT) // 2
        for start_index in range(len(heading_path)):
            header = f"{document_id}\n{LibraryFile.HEADING_PATH_SEPARATOR.join(heading_path[start_index:])}"
            if token_counter.count(header) <= max_header_token_count:
                return header
        return document_id

    def _join(self, header, pieces):
        """One chunk: its header, a blank line, then its pieces back in their lines."""
        lines = []
        last_line_index = None
        for piece in pieces:
            if piece["line_index"] == last_line_index:
                lines[-1] += f" {piece['text']}"
            else:
                lines.append(piece["text"])
                last_line_index = piece["line_index"]

        if not lines:
            return f"{header}\n"
        return header + LibraryFile.HEADER_SEPARATOR + "\n".join(lines) + "\n"

    @staticmethod
    def remove_header(document_id, chunk_text):
        """A chunk's text without the path and headings `split` put in front of it.

        Left whole when it does not open with its path - a file the converter
        could not rewrite was embedded as it came, with no header to take off,
        and cutting at its first blank line would lose its opening paragraph.
        """
        if not chunk_text.startswith(document_id):
            return chunk_text
        return chunk_text.partition(LibraryFile.HEADER_SEPARATOR)[2]
