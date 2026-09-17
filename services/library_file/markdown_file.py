r"""A markdown file, and how markdown is read into the lines chunks are cut from.

Markdown markup is taken out on the way: `**bold**`, the `1\.` escapes a Google
Docs export is full of, link targets, images and code blocks all cost tokens
and carry little meaning, and every one removed leaves room for a word.
Images are dropped outright - the inline base64 kind (INLINE_IMAGE) and the
`![][image1]` references a Google Doc export uses - and never read out as
text, so a note made only of images is one chunk holding its path.

Headings are kept as headings, so a chunk can be headed by the section it
starts in.
"""

import re

from services.library_file.library_file import LibraryFile

IMAGE_PATTERN = re.compile(r"!\[[^\]]*\](\([^)]*\)|\[[^\]]*\])")
LINK_PATTERN = re.compile(r"\[([^\]]+)\](\([^)]*\)|\[[^\]]*\])")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
ESCAPE_PATTERN = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~<])")
EMPHASIS_PATTERN = re.compile(r"\*\*|__|`")
LIST_MARKER_PATTERN = re.compile(r"^(>\s*)*([-*+]|\d+[.)])\s+")
RULE_PATTERN = re.compile(r"^\s*([-*_]\s*){3,}$")
TABLE_DIVIDER_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}")
REFERENCE_DEFINITION_PATTERN = re.compile(r"^\s*\[[^\]]+\]:")


class MarkdownFile(LibraryFile):
    """A .md or .markdown - downloaded byte for byte, and split as markdown.

    Also the base of the types that become markdown on the way in, a Google
    Doc and a .docx: they download differently, but what lands on disk is a
    .md, and it splits the same.

    Drive is inconsistent about the mime type it reports for an uploaded .md
    (it often arrives as text/plain or application/octet-stream), so the
    factory matches on the extension before the mime type.
    """

    MIME_TYPES = ("text/markdown", "text/x-markdown")
    EXTENSIONS = (".md", ".markdown")

    #: Markdown ATX heading levels, # to ######.
    HEADING_LEVELS = range(1, 7)

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

    def _parse(self, text):
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
        text = MarkdownFile.INLINE_IMAGE.sub(" ", text)
        for line in text.splitlines():
            stripped_line = line.lstrip()
            if stripped_line.startswith(("```", "~~~")):
                is_in_fence = not is_in_fence
                continue
            if is_in_fence:
                continue

            level = len(stripped_line) - len(stripped_line.lstrip("#"))
            is_heading = (
                len(line) - len(stripped_line) <= 3
                and level in MarkdownFile.HEADING_LEVELS
                and stripped_line[level:level + 1] in ("", " ", "\t")
            )
            if is_heading:
                title = self._strip_markdown(self._heading_title(stripped_line))
                if title:
                    parsed_lines.append((level, title))
                continue

            if (
                RULE_PATTERN.match(stripped_line)
                or TABLE_DIVIDER_PATTERN.match(stripped_line)
                or REFERENCE_DEFINITION_PATTERN.match(stripped_line)
            ):
                continue
            parsed_lines.append((0, self._strip_markdown(LIST_MARKER_PATTERN.sub("", stripped_line))))
        return parsed_lines

    def _strip_markdown(self, text):
        """Markdown taken out of one line, leaving the words.

        Every HTML tag goes too, comments included. Words too long to be
        language are left for `LibraryFile._words`, which drops them for every
        type.
        """
        text = IMAGE_PATTERN.sub(" ", text)
        text = LINK_PATTERN.sub(r"\1", text)
        text = HTML_TAG_PATTERN.sub(" ", text)
        text = ESCAPE_PATTERN.sub(r"\1", text)
        text = EMPHASIS_PATTERN.sub("", text)
        text = text.replace("|", " ").lstrip("> ")
        return " ".join(text.split())

    def _heading_title(self, heading_line):
        """
        Strip and remove the leading and trailing '#' characters from a heading line.
        """
        title = heading_line.strip().lstrip("#").strip()
        without_closing = title.rstrip("#")
        if without_closing != title and (not without_closing or without_closing[-1] in " \t"):
            title = without_closing.rstrip()
        return title
