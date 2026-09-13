r"""Fits each converted file into the embedding model's window.

The embedder makes one vector per file, and all-MiniLM-L6-v2 reads only the
first 256 tokens of it - the rest of a long note was never searchable. So the
converted copy is rebuilt in order of what is worth a token most:

    Java\Spring Boot\Spring Security\Spring Security.md     <- the path
    <blank>
    # Spring Security                                        <- every heading
    ## Authentication
    ## Authorization
    <blank>
    Spring Security is a framework that ...                 <- opening text, up
                                                               to the budget

The path puts the folders and the file name into the vector, so where a note is
filed counts towards finding it. The headings carry the outline. The opening
text fills whatever room is left, so a note without headings - most .txt files -
is still found by what it says, not only by where it is kept.

Markdown markup is taken out on the way: `**bold**`, the `1\.` escapes a Google
Docs export is full of, link targets, images and code blocks all cost tokens
and carry little meaning, and every one removed leaves room for a word.
Images are dropped outright - the inline base64 kind (INLINE_IMAGE) and the
`![][image1]` references a Google Doc export uses - and never read out as
text, so a note made only of images keeps its path.

Written into the converted copy, never the download: the sources under the
input folder stay exactly as Drive gave them, which is what the reading pane
shows and what makes a re-run repeatable. Both conversion paths copy the
source over the top before calling this, so a second run rebuilds from a full
file rather than an already-reduced one.

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

    #: The path, then a blank line. A blank line so the path cannot run into
    #: the first heading and read as one line.
    HEADER_TEMPLATE = "{document_id}\n\n"

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
        logger.info(f"Fitting files to {FileConvertService.MAX_TOKENS} tokens in {converted_dir}")
        stamped_file_count = 0
        for file_path in sorted(converted_dir.rglob("*")):
            if file_path.is_file() and self.add_to_file(file_path, converted_dir):
                stamped_file_count += 1
        logger.info(f"Done. Fitted {stamped_file_count} file(s) to path, headings and opening text")
        return stamped_file_count

    def add_to_file(self, converted_file_path, converted_dir):
        """Rewrites one converted file as its path, headings and opening text.

        False when there was nothing to do, rather than an exception for a file
        that cannot be read: one bad file must not lose the rest of a run, and a
        file left as it was is still embedded, just from its full text.
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
        # this should never fire - but reducing a reduced file would be silent.
        if text.startswith(document_id):
            logger.debug(f"Already reduced: {converted_file_path}")
            return False

        content = self.fit(document_id, text)
        try:
            converted_file_path.write_text(content, encoding="utf-8")
        except OSError as error:
            logger.warning(f"Could not write {converted_file_path} - {error}")
            return False

        return True

    def fit(self, document_id, text):
        """The path, every heading, then as much opening text as the window holds.

        The path and headings are always kept whole, even past the budget - they
        are what the file is about. Text is added a word at a time: WordPiece
        splits on whitespace before anything else, so a word's tokens are the
        same alone as in a sentence, and the running total is exact.
        """
        content = FileConvertService.HEADER_TEMPLATE.format(document_id=document_id)
        headings = FileConvertService.extract_headings(text)
        if headings:
            # Ends in its own blank line, so the text reads as a paragraph
            # after the outline rather than one more heading.
            content += "\n".join(headings) + "\n\n"

        budget_count = FileConvertService.MAX_TOKENS - FileConvertService.SPECIAL_TOKEN_COUNT
        used_token_count = self.token_counter.count(content)

        words = []
        for line in FileConvertService.extract_body_lines(text):
            for word in line.split():
                word_token_count = self.token_counter.count(word)
                if used_token_count + word_token_count > budget_count:
                    return FileConvertService._join(content, words)
                used_token_count += word_token_count
                words.append(word)
        return FileConvertService._join(content, words)

    @staticmethod
    def _join(content, words):
        """`content` already ends in a blank line, so the text follows straight on."""
        if not words:
            return content.rstrip("\n") + "\n"
        return f"{content}{' '.join(words)}\n"

    @staticmethod
    def extract_headings(text):
        """The Markdown headings of `text`, in order, as tidied `## Title` lines."""
        headings = []
        for level, title in FileConvertService._parse(text):
            if level:
                headings.append(f"{'#' * level} {title}")
        return headings

    @staticmethod
    def extract_body_lines(text):
        """The prose of `text`, in order, with the markup taken out.

        Not headings (those are listed already), code blocks, images, link
        targets, table borders, rules, or reference definitions - the last is
        where a Google Docs export keeps its base64 images.
        """
        lines = []
        for level, line in FileConvertService._parse(text):
            if not level and line:
                lines.append(line)
        return lines

    @staticmethod
    def _parse(text):
        """(heading level, cleaned text) per line outside code blocks; level 0 for body.

        Headings follow Markdown's rules: 1-6 `#` then a space (or nothing), at
        most three spaces of indent - so `#include` and `#hashtag` are body
        text, and a `# comment` in a ``` block is dropped with the block.
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
        """Markdown taken out of one line, leaving the words."""
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
