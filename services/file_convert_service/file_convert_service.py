r"""Splits each converted file into chunks that each fit the embedding model's window.

all-MiniLM-L6-v2 reads only the first 256 tokens of what it is given, so one
vector per file left the rest of a long note unsearchable. The converted copy
is rebuilt as a run of chunks instead, each small enough to be read whole, and
the embedder stores every chunk as a document of its own:

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
    <!-- chunk -->
    ...

Every chunk opens with the path, so where a note is filed counts towards
finding any part of it, and then with the headings above where it starts, so a
passage from the middle of a section still says which section it is. The text
is all of the file, in order - nothing is dropped for want of room any more.

Chunks break between words, never inside one, and a heading always shares a
chunk with the first word under it, so no chunk ends on the title of a section
that starts in the next.

Markdown markup is taken out on the way: `**bold**`, the `1\.` escapes a Google
Docs export is full of, link targets, images and code blocks all cost tokens
and carry little meaning, and every one removed leaves room for a word.
Images are dropped outright - the inline base64 kind (INLINE_IMAGE) and the
`![][image1]` references a Google Doc export uses - and never read out as
text, so a note made only of images is one chunk holding its path.

Written into the converted copy, never the download: the sources under the
input folder stay exactly as Drive gave them, which is what the reading pane
shows and what makes a re-run repeatable. Both conversion paths copy the
source over the top before calling this, so a second run rebuilds from a full
file rather than an already-split one.

Only the extensions the embedder reads are rewritten - a .pdf sitting in the
folder is never embedded, so changing it would have no reader.
"""

import logging
import re
from pathlib import Path

from constant.settings import EMBEDDING_MODEL
from services.SettingService import settingService
from services.file_embedder_service.file_embedder_service import FileEmbedderService
from services.file_convert_service.token_counter import TokenCounter

logger = logging.getLogger(__name__)

IMAGE_PATTERN = re.compile(r"!\[[^\]]*\](\([^)]*\)|\[[^\]]*\])")
LINK_PATTERN = re.compile(r"\[([^\]]+)\](\([^)]*\)|\[[^\]]*\])")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
ESCAPE_PATTERN = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~<])")
EMPHASIS_PATTERN = re.compile(r"\*\*|__|`")
LIST_MARKER_PATTERN = re.compile(r"^(>\s*)*([-*+]|\d+[.)])\s+")
RULE_PATTERN = re.compile(r"^\s*([-*_]\s*){3,}$")
TABLE_DIVIDER_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}")
REFERENCE_DEFINITION_PATTERN = re.compile(r"^\s*\[[^\]]+\]:")


class FileConvertService:

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

    #: Between two chunks in the converted file. The separator line has a
    #: blank line after it, so each chunk still opens on its own path.
    CHUNK_JOINER = f"\n{FileEmbedderService.CHUNK_SEPARATOR}\n\n"

    #: Markdown ATX heading levels, # to ######.
    HEADING_LEVELS = range(1, 7)

    #: A "word" longer than this is a URL or a base64 blob, not language.
    MAX_WORD_LENGTH = 60

    #: ![alt](data:image/png;base64,iVBOR...) - what mammoth writes for a docx.
    #: The payload may wrap over several lines, so this is matched against the
    #: whole file, not line by line. Group 1 is the base64, for a reader that
    #: wants to draw the image.
    INLINE_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*data:image/[^;,]+;base64,\s*([A-Za-z0-9+/=\s]+?)\s*\)")

    #: ![alt][image1] - the placeholder Drive writes exporting a Google Doc as
    #: markdown. Group 1 is the label; the picture itself is in a
    #: REFERENCE_DEFINITION line with the same label, further down the file.
    REFERENCE_IMAGE = re.compile(r"!\[[^\]]*\]\[([^\]]+)\]")

    #: [image1]: <data:image/png;base64,iVBOR...> - where a REFERENCE_IMAGE's
    #: picture lives. Group 1 is the label, group 2 the base64. Anchored to the
    #: start of a line, so it needs re.MULTILINE to find more than the first.
    REFERENCE_DEFINITION = re.compile(
        r"^\[([^\]]+)\]:[ \t]*<?[ \t]*data:image/[^;,]+;base64,\s*([A-Za-z0-9+/=\s]+?)[ \t]*>?[ \t]*$",
        re.MULTILINE,
    )

    #: What the reading pane shows in place of an image it cannot draw.
    UNREADABLE_IMAGE_TEXT = "[image could not be read]"

    def __init__(self, token_counter=None):
        self._token_counter = token_counter

    @property
    def token_counter(self):
        """Built on first use, so reading the settings table waits until a file needs it."""
        if self._token_counter is None:
            self._token_counter = TokenCounter(settingService.find_active_by_key(EMBEDDING_MODEL))
        return self._token_counter

    def add_to_folder(self, converted_dir):
        """Rewrites every embeddable file under `converted_dir`.

        Returns how many files were rewritten.
        """
        converted_dir = Path(converted_dir)
        logger.info(f"Splitting files into chunks of {FileConvertService.MAX_TOKENS} tokens in {converted_dir}")
        split_file_count = 0
        for file_path in sorted(converted_dir.rglob("*")):
            if file_path.is_file() and self.add_to_file(file_path, converted_dir):
                split_file_count += 1
        logger.info(f"Done. Split {split_file_count} file(s) into chunks")
        return split_file_count

    def add_to_file(self, converted_file_path, converted_dir):
        """Rewrites one converted file as the chunks it is embedded from.

        False when there was nothing to do, rather than an exception for a file
        that cannot be read: one bad file must not lose the rest of a run, and a
        file left as it was is still embedded, just as one chunk of raw text.
        """
        converted_file_path = Path(converted_file_path)
        if converted_file_path.suffix.lower() not in FileEmbedderService.TEXT_EXTENSIONS:
            return False

        try:
            document_id = str(converted_file_path.relative_to(Path(converted_dir)))
        except ValueError:
            logger.warning(f"Not rewriting {converted_file_path} - outside {converted_dir}")
            return False

        try:
            text = converted_file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            logger.warning(f"Could not read {converted_file_path} - {error}")
            return False

        # Belt and braces: the callers copy the source over the top first, so
        # this should never fire - but splitting a split file would be silent.
        if text.startswith(document_id):
            logger.debug(f"Already split: {converted_file_path}")
            return False

        chunks = self.split(document_id, text)
        try:
            converted_file_path.write_text(FileConvertService.CHUNK_JOINER.join(chunks), encoding="utf-8")
        except OSError as error:
            logger.warning(f"Could not write {converted_file_path} - {error}")
            return False

        logger.debug(f"Split {converted_file_path} into {len(chunks)} chunk(s)")
        return True

    def split(self, document_id, text):
        """`text` as chunks that each fit the window, in order.

        Each chunk is its header - the path, then the headings it starts under
        - followed by as much of the text as the window has room for, and the
        next chunk carries on where it stopped. A file with no text once the
        markup is out is one chunk holding the path alone.

        A unit that is bigger than the window on its own - a heading hundreds
        of words long - still gets a chunk, and the model reads what fits of
        it: splitting a heading would name the section after half a title.
        """
        budget_count = FileConvertService.MAX_TOKENS - FileConvertService.SPECIAL_TOKEN_COUNT
        chunks = []
        chunk_header = document_id
        chunk_pieces = []
        used_token_count = 0

        for unit in self._units(text):
            unit_token_count = sum(piece["token_count"] for piece in unit)
            if chunk_pieces and used_token_count + unit_token_count > budget_count:
                chunks.append(FileConvertService._join(chunk_header, chunk_pieces))
                chunk_pieces = []

            if not chunk_pieces:
                # A chunk is named for the section its first piece is in.
                chunk_header = self._header(document_id, unit[0]["heading_path"])
                used_token_count = self.token_counter.count(chunk_header)

            chunk_pieces += unit
            used_token_count += unit_token_count

        chunks.append(FileConvertService._join(chunk_header, chunk_pieces))
        return chunks

    def _units(self, text):
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

        for line_index, (level, line) in enumerate(FileConvertService._parse(text)):
            if not line:
                continue

            if level:
                if held_heading_piece is not None:
                    units.append([held_heading_piece])
                # A heading closes every section at its own level or deeper.
                headings = [(heading_level, title) for heading_level, title in headings if heading_level < level]
                held_heading_piece = self._piece(
                    f"{'#' * level} {line}", line_index, [title for _, title in headings], token_counts_by_text
                )
                headings.append((level, line))
                continue

            heading_path = [title for _, title in headings]
            for word in line.split():
                word_piece = self._piece(word, line_index, heading_path, token_counts_by_text)
                if held_heading_piece is None:
                    units.append([word_piece])
                else:
                    units.append([held_heading_piece, word_piece])
                    held_heading_piece = None

        if held_heading_piece is not None:
            units.append([held_heading_piece])
        return units

    def _piece(self, piece_text, line_index, heading_path, token_counts_by_text):
        if piece_text not in token_counts_by_text:
            token_counts_by_text[piece_text] = self.token_counter.count(piece_text)
        return {
            "text": piece_text,
            "line_index": line_index,
            "heading_path": heading_path,
            "token_count": token_counts_by_text[piece_text],
        }

    def _header(self, document_id, heading_path):
        """The path, then the headings a chunk starts under as `A > B > C`.

        Held to half the window, so a deep outline cannot leave a chunk no room
        for text. The outermost headings go first - the innermost says the most
        about the passage, and the outermost is usually the file's own title,
        which the path already has - and the path stays whatever it costs.
        """
        max_header_token_count = (FileConvertService.MAX_TOKENS - FileConvertService.SPECIAL_TOKEN_COUNT) // 2
        for start_index in range(len(heading_path)):
            header = f"{document_id}\n{FileConvertService.HEADING_PATH_SEPARATOR.join(heading_path[start_index:])}"
            if self.token_counter.count(header) <= max_header_token_count:
                return header
        return document_id

    @staticmethod
    def _join(header, pieces):
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
        return header + FileConvertService.HEADER_SEPARATOR + "\n".join(lines) + "\n"

    @staticmethod
    def remove_header(document_id, chunk_text):
        """A chunk's text without the path and headings `split` put in front of it.

        Left whole when it does not open with its path - a file the converter
        could not rewrite was embedded as it came, with no header to take off,
        and cutting at its first blank line would lose its opening paragraph.
        """
        if not chunk_text.startswith(document_id):
            return chunk_text
        return chunk_text.partition(FileConvertService.HEADER_SEPARATOR)[2]

    @staticmethod
    def _parse(text):
        """(heading level, cleaned text) per line outside code blocks; level 0 for body.

        Headings follow Markdown's rules: 1-6 `#` then a space (or nothing), at
        most three spaces of indent - so `#include` and `#hashtag` are body
        text, and a `# comment` in a ``` block is dropped with the block.

        Not kept: code blocks, images, link targets, table borders, rules, or
        reference definitions - the last is where a Google Docs export keeps
        its base64 images.
        """
        parsed_lines = []
        is_in_fence = False
        # Before the split: an inline image's base64 can run over many lines,
        # and cut line by line it would leak into the text as long "words".
        text = FileConvertService.INLINE_IMAGE.sub(" ", text)
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                is_in_fence = not is_in_fence
                continue
            if is_in_fence:
                continue

            level = len(stripped) - len(stripped.lstrip("#"))
            is_heading = (
                len(line) - len(stripped) <= 3
                and level in FileConvertService.HEADING_LEVELS
                and stripped[level:level + 1] in ("", " ", "\t")
            )
            if is_heading:
                title = FileConvertService._clean(FileConvertService._heading_title(stripped[level:]))
                if title:
                    parsed_lines.append((level, title))
                continue

            if (
                RULE_PATTERN.match(stripped)
                or TABLE_DIVIDER_PATTERN.match(stripped)
                or REFERENCE_DEFINITION_PATTERN.match(stripped)
            ):
                continue
            parsed_lines.append((0, FileConvertService._clean(LIST_MARKER_PATTERN.sub("", stripped))))
        return parsed_lines

    @staticmethod
    def _clean(text):
        """Markdown taken out of one line, leaving the words.

        Every HTML tag goes too, which is what makes
        `FileEmbedderService.CHUNK_SEPARATOR` - a comment - safe to split on.
        """
        text = IMAGE_PATTERN.sub(" ", text)
        text = LINK_PATTERN.sub(r"\1", text)
        text = HTML_TAG_PATTERN.sub(" ", text)
        text = ESCAPE_PATTERN.sub(r"\1", text)
        text = EMPHASIS_PATTERN.sub("", text)
        text = text.replace("|", " ").lstrip("> ")
        words = [
            word for word in text.split()
            if len(word) <= FileConvertService.MAX_WORD_LENGTH
        ]
        return " ".join(words)

    @staticmethod
    def _heading_title(after_markers):
        """The words of a heading, from whatever follows its opening `#`s.

        A closing run of `#` is only markup when a space precedes it, so
        `## C#` keeps its `#` while `## Setup ##` drops the trailing pair.
        """
        title = after_markers.strip()
        without_closing = title.rstrip("#")
        if without_closing != title and (not without_closing or without_closing[-1] in " \t"):
            title = without_closing.rstrip()
        return title
