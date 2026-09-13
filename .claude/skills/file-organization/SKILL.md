---
name: file-organization
description: Use when adding a new class, or deciding where a class should live, anywhere in this project. Don't put classes with no relationship to each other in the same file - default to one class per file, and only share a file when there's a genuine direct relationship (inheritance, a class with its own dedicated exception, a protocol and its refinement). Triggers on creating a new class, adding a class to an existing file that already has one, or reviewing a file that holds several classes.
---

# File organization

Default to **one class per file**. Only put more than one class in the same
file when they have a genuine, direct relationship:

- a class and a small subclass built only to specialize it
- a service class and the exception type it raises (nothing else raises it)
- a `Protocol` and the narrower `Protocol` that refines it
- a small family of tightly related constants/config classes that only make
  sense read together (a "tokens" module)

Do **not** put multiple independent, separately-usable classes in one file
just because they're thematically similar (e.g. "all the buttons", "all the
composite widgets"). That was the shape of the old
`view/widgets/blocks.py` / `buttons.py` / `containers.py` / `feedback.py` /
`text.py` - a dozen unrelated public widget classes sharing one file each -
which was split into `view/widgets/blocks/`, `buttons/`, `containers/`,
`feedback/`, `text/`, one file per class, grouped only by directory.

## Examples already in this codebase (compliant)

- `components/FileManager.py` - `OutputFile` (base), `DocFile`/`ImageFile`/
  `OtherFile`/`UnknownFile` (subclasses), `OutputFileFactory` (builds them) -
  an inheritance hierarchy plus its own factory, genuinely one unit.
- `services/SettingService.py` - `SettingService` and
  `SettingNotFoundError`, the exception only it raises.
- `view/protocols/portal.py` - `Portal` and `SearchPortal(Portal, Protocol)`,
  a protocol and its refinement.
- `view/theme.py` - `Space`, `Radius`, `Window`, `Palette`, all design
  tokens read together by the same theme-building functions in that file.

## How to apply

When adding a new class: give it its own file unless it's a small, direct
extension of a class already in the file you're editing. When a file
accumulates classes that don't share one of the relationships above, split
it - one file per class, grouped into a directory if there's a shared theme
(mirror the `view/widgets/` split as the template).
