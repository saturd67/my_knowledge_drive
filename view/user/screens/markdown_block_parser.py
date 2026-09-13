"""A file's markdown, read into the blocks the reading pane draws.

Text in, `(kind, payload)` tuples out. Nothing here touches flet - the kinds
are the ones `FileBody._block` knows how to render, which is why this lives
under view/ rather than in services/: the vocabulary is the reading pane's,
even though the reading is not.

    h1, h2, code, bullet, p   payload is the text
    image                     payload is the decoded bytes of the picture

Two shapes of embedded image are recognised, both produced by the download
pipeline: the inline `![alt](data:image/png;base64,...)` mammoth writes for a
.docx, and the `![alt][image1]` plus trailing definition Drive writes when it
exports a Google Doc. The patterns are `FileConvertService`'s own - it drops
those same images on the way to the converted copy - so what the pane
recognises and what the converter removes live in one place.
"""

import base64
import binascii
import logging
import re

from services.file_convert_service.file_convert_service import FileConvertService

logger = logging.getLogger(__name__)


class MarkdownBlockParser:

    #: Bullets in the markdown start with one of these.
    BULLET_MARKERS = ("- ", "* ", "+ ")

    #: A data URI that neither image pattern claimed - a payload with a
    #: character outside the base64 alphabet, say. Dropping it beats rendering
    #: a megabyte of base64 as a paragraph, which is what the pane used to do.
    STRAY_DATA_URI = re.compile(r"data:image/[^;,]+;base64,[A-Za-z0-9+/=\s]+")

    def parse(self, text):
        """Split a file into the (kind, payload) blocks the pane draws.

        Deliberately small: the files are the markdown and plain text the
        downloader wrote, and this recognises only what
        the reading pane can render. Anything it does not know becomes a
        paragraph, so nothing is ever dropped.
        """
        encoded_images_by_reference = self._images_by_reference(text)
        # The definitions are markup rather than content - they are only what
        # the references point at, and each carries a whole base64 payload on
        # one line.
        text = FileConvertService.REFERENCE_DEFINITION.sub("", text)

        blocks = []
        paragraph = []
        code = None

        def close_paragraph():
            if paragraph:
                blocks.append(("p", " ".join(paragraph)))
                paragraph.clear()

        for line in text.splitlines():
            stripped = line.strip()

            if stripped.startswith("```"):
                if code is None:
                    close_paragraph()
                    code = []
                else:
                    blocks.append(("code", "\n".join(code)))
                    code = None
                continue

            if code is not None:
                code.append(line)
                continue

            if not stripped:
                close_paragraph()
                continue

            # Before the heading and bullet checks: a picture is the content of
            # the line it sits on, whatever else that line is marked up as.
            line_image_blocks = self._image_blocks(stripped, encoded_images_by_reference)
            if line_image_blocks is not None:
                close_paragraph()
                blocks += line_image_blocks
                continue

            if stripped.startswith("#"):
                close_paragraph()
                level = len(stripped) - len(stripped.lstrip("#"))
                blocks.append(("h1" if level == 1 else "h2", stripped.lstrip("#").strip()))
                continue

            if stripped[:2] in self.BULLET_MARKERS:
                close_paragraph()
                blocks.append(("bullet", stripped[2:].strip()))
                continue

            paragraph.append(self.STRAY_DATA_URI.sub("[image]", stripped))

        close_paragraph()
        # An unterminated fence still has to show, or the tail of the file
        # vanishes.
        if code:
            blocks.append(("code", "\n".join(code)))
        return blocks

    def _images_by_reference(self, text):
        """The `[image1]: <data:image/png;base64,...>` payloads, keyed by name.

        Collected up front because the definitions sit at the *end* of a Google
        Doc export while the `![alt][image1]` that points at them is in the
        body, so a single pass down the lines would reach the reference first.
        """
        return dict(FileConvertService.REFERENCE_DEFINITION.findall(text))

    def _image_blocks(self, line, encoded_images_by_reference):
        """One line split into image and text blocks, in source order.

        None when the line holds no image at all, so the caller can carry on
        treating it as the ordinary markdown it is.
        """
        spans = self._image_spans(line, encoded_images_by_reference)
        if not spans:
            return None

        blocks = []
        cursor = 0
        for start, end, encoded_image in spans:
            leading_text = line[cursor:start].strip()
            if leading_text:
                blocks.append(("p", leading_text))
            image_bytes = self._decode_image(encoded_image)
            blocks.append(("image", image_bytes) if image_bytes is not None
                          else ("p", FileConvertService.UNREADABLE_IMAGE_TEXT))
            cursor = end

        trailing_text = line[cursor:].strip()
        if trailing_text:
            blocks.append(("p", trailing_text))
        return blocks

    def _image_spans(self, line, encoded_images_by_reference):
        """(start, end, base64) for every image on one line, in the order they sit.

        Both shapes the pipeline produces: `![alt](data:image/png;base64,...)`,
        which is what mammoth writes for a .docx, and `![alt][image1]`, which is
        what Drive writes exporting a Google Doc. They use different delimiters,
        so no run of text can match both.
        """
        spans = []

        for match in FileConvertService.INLINE_IMAGE.finditer(line):
            spans.append((match.start(), match.end(), match.group(1)))

        for match in FileConvertService.REFERENCE_IMAGE.finditer(line):
            encoded_image = encoded_images_by_reference.get(match.group(1))
            # A reference whose definition is missing is left alone, to fall
            # through and read as the ordinary text it now is.
            if encoded_image is not None:
                spans.append((match.start(), match.end(), encoded_image))

        spans.sort()
        return spans

    def _decode_image(self, encoded_image):
        """A base64 payload as the bytes flet draws, or None if it will not decode."""
        try:
            image_bytes = base64.b64decode(re.sub(r"\s+", "", encoded_image))
        except (binascii.Error, ValueError) as error:
            logger.warning(f"Could not decode an embedded image - {error}")
            return None

        # b64decode is lenient: a payload of "====" comes back as no bytes at
        # all rather than raising, and an empty `src` draws as a broken picture.
        if not image_bytes:
            logger.warning("An embedded image decoded to nothing")
            return None
        return image_bytes
