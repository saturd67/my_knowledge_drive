r"""Checks the path header FileConvertService writes into each converted file.

Every embeddable file under the converted folder should open with its own path,
relative to that folder, then a blank line:

    Java\Spring Boot\Spring Security\Spring Security.md
    <blank>
    ...the file as downloaded...

The downloads themselves must stay untouched, so the input folder is checked
the other way round: a source that starts with its path means a header leaked
into the copy Drive gave us.

Run it from the project root:

    python scripts/check_file_path_headers.py
    python scripts/check_file_path_headers.py --converted-dir D:\x --input-dir D:\y
    python scripts/check_file_path_headers.py --verbose

Exits 1 when anything needs attention, so it can gate a script or CI step.
"""

import argparse
import sys
from pathlib import Path

# Run as a plain script, the project root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constant.settings import PATHS_INPUT_DIR, PATHS_OUTPUT_DIR  # noqa: E402
from services.file_embedder_service.file_embedder_service import FileEmbedderService  # noqa: E402

# status -> what it means, shown in the summary
STATUS_MEANINGS = {
    "ok": "path header present and correct",
    "missing": "no path header",
    "wrong_path": "a path header, but not this file's path (moved or renamed?)",
    "no_blank_line": "path header runs straight into the text",
    "stamped_twice": "path header written more than once",
    "empty": "empty file",
    "unreadable": "could not be read as UTF-8",
    "leaked": "download starts with its own path - the source was stamped",
}

PROBLEM_STATUSES = {status for status in STATUS_MEANINGS if status != "ok"}


def check_converted_file(file_path, converted_dir):
    """Returns (status, detail) for one converted file."""
    document_id = str(file_path.relative_to(converted_dir))
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return "unreadable", str(error)

    if not text.strip():
        return "empty", ""

    lines = text.split("\n")
    first_line = lines[0].rstrip("\r")

    if first_line != document_id:
        if _looks_like_header(first_line):
            return "wrong_path", f"header says {first_line!r}"
        return "missing", f"starts with {first_line[:60]!r}"

    second_line = lines[1].rstrip("\r") if len(lines) > 1 else ""
    if second_line.strip():
        return "no_blank_line", f"second line is {second_line[:60]!r}"

    # FileConvertService refuses to restamp, but a copy that skipped the
    # "copy the source over first" step would still stack headers.
    third_line = lines[2].rstrip("\r") if len(lines) > 2 else ""
    if third_line == document_id:
        return "stamped_twice", ""

    return "ok", ""


def check_input_file(file_path, input_dir):
    """Returns (status, detail) for one downloaded source - it must not be stamped."""
    document_id = str(file_path.relative_to(input_dir))
    try:
        with file_path.open(encoding="utf-8") as source_file:
            first_line = source_file.readline().rstrip("\r\n")
    except (OSError, UnicodeDecodeError) as error:
        return "unreadable", str(error)

    if first_line == document_id:
        return "leaked", ""
    return "ok", ""


def _looks_like_header(line):
    """A first line that is a lone relative path to an embeddable file."""
    return (
        line.lower().endswith(FileEmbedderService.TEXT_EXTENSIONS)
        and ("\\" in line or "/" in line or " " not in line.strip())
        and not line.lstrip().startswith(("#", "-", "*", ">", "!["))
    )


#: Markdown ATX heading levels, # to ######.
HEADING_LEVELS = range(1, 7)


def count_words(text):
    """Whitespace-separated tokens that hold at least one letter or digit.

    Markdown punctuation standing on its own - a `-` bullet, a `|` table
    border, a ``` fence - is markup, so it is not a word; `C#` and `don't` are
    one word each. CJK text has no spaces, so a run of it counts as one word.
    """
    return sum(1 for token in text.split() if any(character.isalnum() for character in token))


def file_stats(file_path):
    """Heading and word statistics for one file, or None if unreadable.

    Returns (heading_counts, heading_character_count, heading_word_count,
    word_count) where heading_counts is {level: count}.

    Headings follow Markdown's rules: 1-6 `#` then a space (or nothing), at
    most three spaces of indent, and never inside a ``` or ~~~ fence - so a
    `#include` or a `# comment` in a code block is not counted.

    Heading characters and words come from the title text only: `## Setup ##`
    is 5 characters and 1 word - the `#` markers, the surrounding spaces and an
    optional closing run of `#` are markup. Characters are counted on the
    decoded text, so an accented letter or a CJK character is one character.

    `word_count` is the whole file, code blocks included - it is what the
    embedder is handed.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    heading_counts = {level: 0 for level in HEADING_LEVELS}
    heading_character_count = 0
    heading_word_count = 0
    is_in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            is_in_fence = not is_in_fence
            continue
        if is_in_fence or len(line) - len(stripped) > 3:
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        is_heading = level in HEADING_LEVELS and stripped[level:level + 1] in ("", " ", "\t")
        if is_heading:
            title = heading_title(stripped[level:])
            heading_counts[level] += 1
            heading_character_count += len(title)
            heading_word_count += count_words(title)
    return heading_counts, heading_character_count, heading_word_count, count_words(text)


def heading_title(after_markers):
    """The words of a heading, from whatever follows its opening `#`s.

    A closing run of `#` is only markup when a space precedes it, so
    `## C#` keeps its `#` while `## Setup ##` drops the trailing pair.
    """
    title = after_markers.strip()
    without_closing = title.rstrip("#")
    if without_closing != title and (not without_closing or without_closing[-1] in " \t"):
        title = without_closing.rstrip()
    return title


def heading_types(heading_counts):
    """The levels a file actually uses, e.g. "H1,H2,H4" - or "-" for none."""
    return ",".join(f"H{level}" for level, count in heading_counts.items() if count) or "-"


def print_file_stats(label, folder):
    """One row per file: heading characters and words, file words, heading types,
    and a count per level."""
    if not folder.is_dir():
        return
    print(f"\n[{label}] Header types, header characters and word counts per file in {folder}")
    level_columns = "".join(f"{'H' + str(level):>5}" for level in HEADING_LEVELS)
    print(f"  {'HDR CHARS':>9}  {'HDR WORDS':>9}  {'WORDS':>8}  {'TYPES':<18}{level_columns}  FILE")

    total_heading_counts = {level: 0 for level in HEADING_LEVELS}
    total_heading_character_count = 0
    total_heading_word_count = 0
    total_word_count = 0
    unreadable_file_count = 0
    for file_path in embeddable_files(folder):
        relative_path = file_path.relative_to(folder)
        stats = file_stats(file_path)
        if stats is None:
            unreadable_file_count += 1
            print(f"  {'-':>9}  {'-':>9}  {'-':>8}  {'unreadable':<18}{'':30}  {relative_path}")
            continue
        heading_counts, heading_character_count, heading_word_count, word_count = stats
        total_heading_character_count += heading_character_count
        total_heading_word_count += heading_word_count
        total_word_count += word_count
        for level, count in heading_counts.items():
            total_heading_counts[level] += count
        counts = "".join(f"{count:>5}" for count in heading_counts.values())
        print(f"  {heading_character_count:>9}  {heading_word_count:>9}  {word_count:>8}"
              f"  {heading_types(heading_counts):<18}{counts}  {relative_path}")

    totals = "".join(f"{count:>5}" for count in total_heading_counts.values())
    print(f"  {total_heading_character_count:>9}  {total_heading_word_count:>9}  {total_word_count:>8}"
          f"  {'TOTAL':<18}{totals}")
    if unreadable_file_count:
        print(f"  {unreadable_file_count} file(s) could not be read as UTF-8")


def embeddable_files(folder):
    return sorted(
        file_path for file_path in folder.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in FileEmbedderService.TEXT_EXTENSIONS
    )


def scan(folder, check, label, is_verbose):
    """Checks every embeddable file in `folder`. Returns {status: [(path, detail)]}."""
    results = {}
    if not folder.is_dir():
        print(f"[{label}] folder not found: {folder}")
        return results

    for file_path in embeddable_files(folder):
        status, detail = check(file_path, folder)
        results.setdefault(status, []).append((file_path.relative_to(folder), detail))
        if is_verbose or status != "ok":
            suffix = f" - {detail}" if detail else ""
            print(f"  {status.upper():14} {file_path.relative_to(folder)}{suffix}")
    return results


def print_summary(label, folder, results):
    checked_file_count = sum(len(entries) for entries in results.values())
    print(f"\n[{label}] {folder}")
    print(f"  {checked_file_count} embeddable file(s) checked")
    for status, meaning in STATUS_MEANINGS.items():
        if status == "ok" and label == "downloads":
            # For a download, "ok" is the opposite: it must carry no header.
            meaning = "no path header, as Drive gave it"
        if status in results:
            print(f"  {len(results[status]):6}  {status:14} {meaning}")


def default_dirs():
    """The folders the app itself uses, read from the settings table."""
    from services.SettingService import settingService

    return (
        Path(settingService.get_path(PATHS_OUTPUT_DIR)),
        Path(settingService.get_path(PATHS_INPUT_DIR)),
    )


def main():
    parser = argparse.ArgumentParser(description="Check the file path headers in converted files.")
    parser.add_argument("--converted-dir", type=Path, help="defaults to the paths.output_dir setting")
    parser.add_argument("--input-dir", type=Path, help="defaults to the paths.input_dir setting")
    parser.add_argument("--skip-input", action="store_true", help="do not check the downloads")
    parser.add_argument("--verbose", action="store_true", help="also list files that are fine")
    args = parser.parse_args()

    converted_dir, input_dir = args.converted_dir, args.input_dir
    if converted_dir is None or (input_dir is None and not args.skip_input):
        default_converted_dir, default_input_dir = default_dirs()
        converted_dir = converted_dir or default_converted_dir
        input_dir = input_dir or default_input_dir

    print(f"Checking converted files in {converted_dir}")
    converted_results = scan(converted_dir, check_converted_file, "converted", args.verbose)

    input_results = {}
    if not args.skip_input:
        print(f"\nChecking downloads are unstamped in {input_dir}")
        input_results = scan(input_dir, check_input_file, "downloads", args.verbose)

    print_summary("converted", converted_dir, converted_results)
    if not args.skip_input:
        print_summary("downloads", input_dir, input_results)
        print_file_stats("downloads", input_dir)

    problem_count = sum(
        len(entries)
        for results in (converted_results, input_results)
        for status, entries in results.items()
        if status in PROBLEM_STATUSES
    )
    is_folder_missing = not converted_dir.is_dir()
    print(f"\n{'PASS' if problem_count == 0 and not is_folder_missing else 'FAIL'}"
          f" - {problem_count} file(s) need attention")
    return 1 if problem_count or is_folder_missing else 0


if __name__ == "__main__":
    sys.exit(main())
