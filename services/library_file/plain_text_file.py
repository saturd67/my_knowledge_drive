from services.library_file.library_file import LibraryFile


class PlainTextFile(LibraryFile):
    """A .txt - downloaded byte for byte, and split as the lines it holds.

    Nothing in it is read as markup: a `# note` line is not a heading, the
    `<String>` in `List<String>` is not an HTML tag, and `**` is not bold - a
    text file of commands or a log means exactly what it says. With no
    headings, every chunk is headed by the path alone.
    """

    MIME_TYPES = ("text/plain",)
    EXTENSIONS = (".txt",)

    def _parse(self, text):
        """Every line as body text, as written."""
        return [(0, line) for line in text.splitlines()]
