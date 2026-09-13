---
name: variable-naming
description: Use when writing or reviewing any Python code in this project - covers three rules - (1) a local variable holding a single class instance is named after that class, in snake_case, (2) a boolean variable's name always starts with 'is', and (3) a counter's name ends with 'count' and says what it counts (downloaded_file_count). Applies everywhere (view/ widgets and screens, services/, repository/, components/). Triggers on introducing a new local var assigned from a class constructor, a boolean expression, or a running total, or noticing an existing generically-named one nearby (field, box, view, header, selected, busy, armed, active, read_only, heavy, count, total, downloaded, skipped, failed).
---

# Variable naming

## 1. Class instances - name after the class

When a local variable is assigned an instance of a single, unambiguous
class - a Flet control (`ft.TextField`, `ft.Container`), a project widget
or screen (`SearchView`, `PortalRail`, `widgets.CheckRow`), a service
(`FileFetcherService`), or any other class - name the variable after that
class, in **snake_case**:

```python
text_field = ft.TextField(...)
filled_button = ft.FilledButton(...)
search_view = SearchView(self)
progress_row = widgets.ProgressRow(...)
alert_dialog = ft.AlertDialog(...)
file_fetcher_service = FileFetcherService()
```

Do not use generic placeholder names for these: `field`, `box`, `view`,
`header`, `title`, `caret`, `counter`, `button`, `dialog`, `bar`.

This applies to any class instance, project-defined or from a library
(Flet, pathlib, etc.) - not just widgets.

### On name collision

Name the variable after its class name first. If that name is already taken
in the same scope (two different instances of the same class, or it would
collide with another variable), add a word to the class-based name to make
the two different and easier to tell apart - don't fall back to a generic
name:

```python
header_container = ft.Container(...)
body_container = ft.Container(...)
content_row = ft.Row([...])       # distinct from a later `row = widgets.CheckRow(...)`
```

### Exceptions

- **`p = self.p` / `p = palette()` stays `p`.** Renaming it to `palette`
  would shadow the imported `palette` function itself - a real collision,
  not just a style nit.
- **Genuinely polymorphic variables keep a semantic name.** If a variable
  holds different classes depending on the branch (e.g. `Pill` in one
  branch, `ProgressRing` or `Container` in another), there is no single
  class to name it after - keep whatever name describes its role (`count`,
  `body`, `header_content`).

## 2. Booleans - always start with `is`

A variable or parameter that holds a `True`/`False` value starts with `is`:

```python
is_open = self._folder_open(path)
is_selected = index == self.state.selected_index
is_busy = self.state.sync_stage in ("scanning", "updating")
is_armed = typed.strip() == CONFIRM_WORD
is_read_only = self.state.sync_stage != "reviewing"
```

Don't use a bare adjective/participle (`busy`, `armed`, `active`,
`read_only`, `heavy`, `selected`) for a boolean - only `is_...` reads
unambiguously as true/false at the call site.

### Exceptions

- **Keyword arguments to an external library's fixed API stay as that API
  names them.** `ft.Checkbox(disabled=..., tristate=...)`,
  `Card(..., border=...)`, `Hoverable(..., selected=..., bordered=...)` -
  these parameter names are Flet's (or another library's) own signature,
  not ours to rename.
- **A name that is only sometimes boolean stays untouched, or gets split.**
  e.g. `selected = len(self.state.scan_selected)` (an int) and
  `selected = self.state.scan_selected` (a set) are not booleans at
  all - only rename the specific occurrences that actually hold a
  `True`/`False` value.

## 3. Counters - end with `count`, and say what is counted

A variable that holds a running total ends with `count`, and names the
thing it counts:

```python
downloaded_file_count = 0
skipped_file_count = 0
failed_file_count = 0
converted_file_count, skipped_file_count = self._sync_file(input_dir)
```

Don't use the bare participle or adjective on its own (`downloaded`,
`skipped`, `failed`, `converted`, `total`) - on its own it reads like a
boolean or like the thing itself rather than how many of them there are.

### On accumulating from a nested call

When a recursive or nested call returns counts that are added to the
running ones, prefix the returned names rather than shortening them:

```python
sub_downloaded_file_count, sub_skipped_file_count = self._download_files_in_folder(...)
downloaded_file_count += sub_downloaded_file_count
skipped_file_count += sub_skipped_file_count
```

### Exceptions

- **A loop index is not a count.** `index`, or the `index` from
  `enumerate(...)`, stays as it is.
- **A length read once and used inline** keeps a descriptive name if it is
  not a running total - `total_img = len(soup.find_all('img'))` is a
  count, and would be `image_count`; `len(files)` used directly in an
  f-string needs no variable at all.

## Where this applies

Project-wide - `view/` (shells, screens, widgets), `services/`,
`repository/`, `components/`, and anywhere else a variable is assigned a
class instance, a boolean value, or a count. Apply all three rules when
introducing new local variables and when touching nearby code that still
uses the old style.
