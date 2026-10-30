"""Check Markdown links, anchors, and the development task table.

Run:
    uv run --no-sync python -B tools/check_docs.py
    uv run --no-sync python -B tools/check_docs.py --verbose

``--root`` points the same checks at another documentation tree, which is how
the failure paths are demonstrated without touching the real docs.

The checker is read-only, needs only the standard library, and exits non-zero
when any problem is found. It scans ``AGENTS.md``, ``README.md`` and every
``*.md`` under ``docs/``. READMEs inside ``src/`` are *not* scanned: they are
package documentation, their links are checked when the package is reviewed,
and scanning them here would tie ``make docs`` to code moves; ``.git``, ``.venv``, ``.artifacts``, ``rsl_rl``,
``node_modules`` and ``__pycache__`` are skipped. Fenced code blocks are not
treated as Markdown content. Prose is not parsed, so status words in sentences
are never interpreted as task status.

Checks
------
1. Inline links ``[text](target)`` must resolve, relative to the containing
   document, to an existing file or directory. Empty targets, HTTP(S),
   ``mailto:`` and ``data:`` targets are skipped; an optional ``<...>``
   wrapper and an optional ``"title"`` are stripped before resolution. A
   target that starts with ``#`` has an empty path part, so it resolves to the
   containing document and only its anchor is checked. A local anchor must
   match a GitHub-style heading slug: lowercase, drop everything that is not
   a letter, digit, ``-``, ``_`` or whitespace, collapse whitespace runs to
   ``-`` and strip leading/trailing ``-``; CJK characters count as letters.
   Duplicate headings get ``-1``, ``-2``, ... in document order. Explicit
   HTML ``<a name="...">`` and ``id="..."`` anchors are accepted too, and
   anchor comparison ignores case (percent-encoded anchors are decoded).
2. The task table in ``docs/development.md`` (rows with four cells whose
   first cell is exactly ``T`` plus three digits) must use the statuses
   待办/进行中/阻塞/完成, must not repeat an id, must have at most one
   进行中 task (zero is fine; it is printed as information, not a problem),
   may only list existing prerequisites, and that prerequisite graph must be
   acyclic. A 进行中 or 完成 task may not depend on a 待办 or 阻塞 task.
   ``### Txxx`` headings must have a matching row. Only the part of the
   prerequisite cell before the first ``；`` is a dependency list: everything
   after it is a note, so ``T000；不依赖 T001 提交`` depends on ``T000`` alone.
3. Every ``Txxx`` token in ``docs/archive/development_records.md`` must
   appear in the task table.

Table id without entry heading
------------------------------
Every id in the status table must be traceable to detailed documentation.
An id of the status table counts as documented when at least one of these
exists outside that table's own row:

* a level-2 to level-6 Markdown heading that names the id first or last, so
  ``### T042 导出策略`` and ``### 2026 年 10 月 27 日 T042`` count but a
  passing mention such as ``## 后续 T042 相关讨论`` does not, or
* a table row whose first cell is exactly the id,

in ``docs/development.md`` or in any ``*.md`` under ``docs/archive/``. An id
that appears only in the status table is reported.

The search covers ``docs/archive/`` on purpose: task entries and completion
records live there now, so requiring the entry heading inside
``docs/development.md`` alone would flag every archived task. The stricter
"the heading must be a ``### Txxx`` heading in ``docs/development.md``" form
is used for the orphan check in item 2, where the reverse direction (heading
without a status row) is what matters.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]

ROOT_DOCUMENTS = ("AGENTS.md", "README.md")
DOCS_DIRECTORY = "docs"
TASK_TABLE_DOCUMENT = Path("docs/development.md")
ARCHIVE_DIRECTORY = Path("docs/archive")
RECORDS_DOCUMENT = Path("docs/archive/development_records.md")

SKIP_DIRECTORIES = frozenset(
    {".git", ".venv", ".artifacts", "rsl_rl", "node_modules", "__pycache__"}
)
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "data:")
TASK_STATUSES = ("待办", "进行中", "阻塞", "完成")
ACTIVE_STATUSES = frozenset({"进行中", "完成"})
UNFINISHED_STATUSES = frozenset({"待办", "阻塞"})

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*)$")
_ENTRY_HEADING_RE = re.compile(r"^ {0,3}###[ \t]+(T\d{3})\b")
_TASK_ID_RE = re.compile(r"T\d{3}")
_TASK_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z])T\d{3}(?![0-9A-Za-z])")
_LEADING_TASK_ID_RE = re.compile(r"^(T\d{3})(?![0-9A-Za-z])")
_TRAILING_TASK_ID_RE = re.compile(r"(?<![0-9A-Za-z])(T\d{3})$")
_LINK_RE = re.compile(r"\[[^\]\n]*\]\(\s*([^()\n]*?)\s*\)")
_LINK_TITLE_RE = re.compile(r'^(.*?)\s+"[^"]*"$')
_TABLE_SPLIT_RE = re.compile(r"(?<!\\)\|")
_HTML_NAME_RE = re.compile(r"""<a\s+[^>]*\bname\s*=\s*["']([^"']+)["']""", re.I)
_HTML_ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)


# ---------- parsing helpers (pure, unit-tested) ----------


def slugify(text: str) -> str:
    """Return the GitHub-style heading slug for ``text``."""
    kept: list[str] = []
    for character in text.strip().lower():
        if character.isalnum() or character in "-_":
            kept.append(character)
        elif character.isspace():
            kept.append(" ")
    slug = re.sub(r"\s+", "-", "".join(kept))
    return slug.strip("-")


def heading_anchors(headings: Sequence[str]) -> set[str]:
    """Return anchors for ``headings``, suffixing repeated slugs with ``-1``...

    The suffix keeps growing until the anchor is unused, so a document that
    already contains a heading literally called ``Notes 1`` cannot collide
    with the suffix generated for a repeated ``Notes`` heading.
    """
    used: set[str] = set()
    anchors: set[str] = set()
    for heading in headings:
        base = slugify(heading)
        candidate = base
        suffix = 1
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        anchors.add(candidate)
    return anchors


def parse_link_target(raw: str) -> str | None:
    """Strip ``<...>`` wrapper and ``"title"`` from a link target."""
    target = raw.strip()
    if not target:
        return None
    if target.startswith("<"):
        end = target.find(">")
        if end != -1:
            return target[1:end].strip() or None
    titled = _LINK_TITLE_RE.match(target)
    if titled:
        target = titled.group(1).strip()
    return target or None


def extract_task_ids(text: str) -> list[str]:
    """Return distinct ``Txxx`` tokens from ``text`` in first-seen order."""
    return list(dict.fromkeys(_TASK_TOKEN_RE.findall(text)))


def _heading_task_ids(title: str) -> set[str]:
    """Return the ids a documented-entry heading may claim.

    An entry heading names its task either first (``### T042 导出策略``) or
    last (``### 2026 年 10 月 27 日 T042``). A passing mention in the middle,
    such as ``## 后续 T042 相关讨论``, claims nothing, which is what keeps the
    documentation check from being satisfied by an aside.
    """
    text = title.strip()
    found: set[str] = set()
    leading = _LEADING_TASK_ID_RE.match(text)
    if leading:
        found.add(leading.group(1))
    trailing = _TRAILING_TASK_ID_RE.search(text)
    if trailing:
        found.add(trailing.group(1))
    return found


def parse_prerequisites(cell: str) -> list[str]:
    """Return the dependency ids of a prerequisite cell.

    Only the text before the first ``；`` carries dependencies; the rest is a
    free-form note. ``T000；不依赖 T001 提交`` therefore depends on ``T000``
    alone, which is what the sentence says.
    """
    head = cell.partition("；")[0]
    return extract_task_ids(head)


def find_cycles(edges: Mapping[str, Sequence[str]]) -> list[list[str]]:
    """Return dependency cycles as paths whose first and last node match."""
    graph: dict[str, list[str]] = {node: list(deps) for node, deps in edges.items()}
    for dependencies in list(graph.values()):
        for dependency in dependencies:
            graph.setdefault(dependency, [])

    state: dict[str, int] = dict.fromkeys(graph, 0)
    path: list[str] = []
    cycles: list[list[str]] = []
    reported: set[frozenset[str]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        path.append(node)
        for dependency in graph[node]:
            if state[dependency] == 0:
                visit(dependency)
            elif state[dependency] == 1:
                start = path.index(dependency)
                cycle = [*path[start:], dependency]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    cycles.append(cycle)
        path.pop()
        state[node] = 2

    for node in sorted(graph):
        if state[node] == 0:
            visit(node)
    return cycles


def split_markdown_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line number, line)`` for lines outside fenced code blocks."""
    fence: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                marker = match.group(1)
                fence = (marker[0], len(marker))
                continue
            yield number, line
        elif match:
            marker = match.group(1)
            if marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None


def mask_inline_code(line: str) -> str:
    """Blank out inline code spans so ``[x](y)`` inside them is not a link."""
    parts = re.split(r"(`+[^`]*`+)", line)
    return "".join(
        " " * len(part) if part.startswith("`") else part for part in parts
    )


def document_anchors(text: str) -> set[str]:
    """Return heading slugs and explicit HTML anchors of a Markdown document."""
    headings: list[str] = []
    anchors: set[str] = set()
    for _, line in split_markdown_lines(text):
        heading = _HEADING_RE.match(line)
        if heading:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(2)).strip()
            headings.append(title)
        for regex in (_HTML_NAME_RE, _HTML_ID_RE):
            anchors.update(unquote(value).lower() for value in regex.findall(line))
    return anchors | heading_anchors(headings)


def is_external_target(target: str) -> bool:
    """Return whether ``target`` points outside the repository."""
    return target.lower().startswith(EXTERNAL_PREFIXES)


def table_cells(line: str) -> list[str] | None:
    """Split a Markdown table row into stripped cells, or return ``None``.

    Escaped pipes (``\\|``) stay inside their cell, so a cell such as
    ``a \\| b`` does not change the column count.
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    body = stripped[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.replace("\\|", "|").strip() for cell in _TABLE_SPLIT_RE.split(body)]


# ---------- checker ----------


@dataclass(frozen=True)
class Problem:
    """One reported inconsistency."""

    path: str
    line: int
    message: str


@dataclass(frozen=True)
class TaskRow:
    """One row of the status table in ``docs/development.md``."""

    task_id: str
    title: str
    status: str
    prerequisites: str
    line: int


class DocsChecker:
    """Scan one documentation tree and collect problems."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.problems: list[Problem] = []
        self.link_count = 0
        self.task_row_count = 0
        self.in_progress_count = 0
        self._anchors: dict[Path, set[str]] = {}

    # -- helpers ---------------------------------------------------------

    def display(self, path: Path) -> str:
        """Return ``path`` relative to the checked root when possible."""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def add_problem(self, path: str, line: int, message: str) -> None:
        self.problems.append(Problem(path, line, message))

    def anchors_for(self, path: Path) -> set[str]:
        resolved = path.resolve()
        anchors = self._anchors.get(resolved)
        if anchors is None:
            anchors = document_anchors(_read_text(resolved))
            self._anchors[resolved] = anchors
        return anchors

    def markdown_files(self) -> list[Path]:
        """Return the Markdown files this checker is responsible for."""
        files = [
            self.root / name for name in ROOT_DOCUMENTS if (self.root / name).is_file()
        ]
        docs = self.root / DOCS_DIRECTORY
        if docs.is_dir():
            for path in sorted(docs.rglob("*.md")):
                if SKIP_DIRECTORIES.intersection(path.relative_to(self.root).parts):
                    continue
                files.append(path)
        return files

    # -- links and anchors ----------------------------------------------

    def check_links(self, path: Path) -> None:
        """Check every inline link in ``path``."""
        relative = self.display(path)
        for number, line in split_markdown_lines(_read_text(path)):
            for match in _LINK_RE.finditer(mask_inline_code(line)):
                target = parse_link_target(match.group(1))
                if target is None or is_external_target(target):
                    continue
                self.link_count += 1
                path_part, _, anchor = target.partition("#")
                resolved = (
                    (path.parent / path_part).resolve()
                    if path_part
                    else path.resolve()
                )
                if not resolved.exists():
                    self.add_problem(
                        relative, number, f"link target does not exist: {target}"
                    )
                    continue
                if not anchor or resolved.suffix.lower() != ".md":
                    continue
                wanted = unquote(anchor).lower()
                if wanted not in self.anchors_for(resolved):
                    self.add_problem(
                        relative,
                        number,
                        f"anchor not found in {self.display(resolved)}: #{anchor}",
                    )

    # -- task table -----------------------------------------------------

    def documented_task_ids(self, status_lines: set[int]) -> set[str]:
        """Return ids with an entry heading or a non-status table row."""
        found: set[str] = set()
        paths = [self.root / TASK_TABLE_DOCUMENT]
        archive = self.root / ARCHIVE_DIRECTORY
        if archive.is_dir():
            paths.extend(sorted(archive.rglob("*.md")))
        table_document = (self.root / TASK_TABLE_DOCUMENT).resolve()
        for path in paths:
            if not path.is_file():
                continue
            is_table_document = path.resolve() == table_document
            for number, line in split_markdown_lines(_read_text(path)):
                if is_table_document and number in status_lines:
                    continue
                heading = _HEADING_RE.match(line)
                if heading and len(heading.group(1)) >= 2:
                    found.update(_heading_task_ids(heading.group(2)))
                cells = table_cells(line)
                if cells is not None and cells and _TASK_ID_RE.fullmatch(cells[0]):
                    found.add(cells[0])
        return found

    def check_task_table(self) -> set[str]:
        """Check the status table and return the ids it defines."""
        document = TASK_TABLE_DOCUMENT.as_posix()
        path = self.root / TASK_TABLE_DOCUMENT
        if not path.is_file():
            self.add_problem(document, 1, "task table document is missing")
            return set()

        lines = list(split_markdown_lines(_read_text(path)))
        rows: list[TaskRow] = []
        headings: list[tuple[int, str]] = []
        status_lines: set[int] = set()
        for number, line in lines:
            cells = table_cells(line)
            if cells is not None and len(cells) == 4:
                if _TASK_ID_RE.fullmatch(cells[0]):
                    status_lines.add(number)
                    rows.append(
                        TaskRow(cells[0], cells[1], cells[2], cells[3], number)
                    )
            heading = _ENTRY_HEADING_RE.match(line)
            if heading:
                headings.append((number, heading.group(1)))
        self.task_row_count = len(rows)
        if not rows:
            self.add_problem(
                document, 1, "no task rows (four cells, first cell like T001) found"
            )
            return set()

        by_id: dict[str, TaskRow] = {}
        for row in rows:
            if row.status not in TASK_STATUSES:
                self.add_problem(
                    document,
                    row.line,
                    f"task {row.task_id} has status {row.status!r}; "
                    "expected one of 待办/进行中/阻塞/完成",
                )
            if row.task_id in by_id:
                first = by_id[row.task_id]
                self.add_problem(
                    document,
                    row.line,
                    f"duplicate task id {row.task_id} (first row at line {first.line})",
                )
            else:
                by_id[row.task_id] = row

        in_progress = [row for row in rows if row.status == "进行中"]
        self.in_progress_count = len(in_progress)
        if len(in_progress) > 1:
            ids = ", ".join(row.task_id for row in in_progress)
            self.add_problem(
                document,
                in_progress[1].line,
                f"more than one task is in progress: {ids}",
            )

        known = set(by_id)
        edges: dict[str, list[str]] = {}
        for row in rows:
            prerequisites = parse_prerequisites(row.prerequisites)
            edges[row.task_id] = prerequisites
            for prerequisite in prerequisites:
                if prerequisite not in known:
                    self.add_problem(
                        document,
                        row.line,
                        f"task {row.task_id} lists unknown prerequisite "
                        f"{prerequisite}",
                    )
            if row.status in ACTIVE_STATUSES:
                for prerequisite in prerequisites:
                    required = by_id.get(prerequisite)
                    if required is not None and required.status in UNFINISHED_STATUSES:
                        self.add_problem(
                            document,
                            row.line,
                            f"task {row.task_id} is {row.status} but prerequisite "
                            f"{prerequisite} is {required.status}",
                        )

        for cycle in find_cycles(edges):
            first = by_id.get(cycle[0])
            line = first.line if first is not None else 1
            self.add_problem(
                document,
                line,
                "prerequisite cycle: " + " -> ".join(cycle),
            )

        for number, task_id in headings:
            if task_id not in known:
                self.add_problem(
                    document,
                    number,
                    f"heading {task_id} has no row in the task table",
                )

        documented = self.documented_task_ids(status_lines)
        reported: set[str] = set()
        for row in rows:
            if row.task_id in documented or row.task_id in reported:
                continue
            reported.add(row.task_id)
            self.add_problem(
                document,
                row.line,
                f"task {row.task_id} has no entry heading and no task table "
                "row in docs/development.md or docs/archive/",
            )
        return known

    # -- archived mentions ----------------------------------------------

    def check_record_mentions(self, table_ids: set[str]) -> None:
        """Require every task id in the completion-record archive to be known."""
        path = self.root / RECORDS_DOCUMENT
        if not table_ids or not path.is_file():
            return
        document = self.display(path)
        for number, line in split_markdown_lines(_read_text(path)):
            for task_id in extract_task_ids(line):
                if task_id not in table_ids:
                    self.add_problem(
                        document,
                        number,
                        f"{task_id} is not in the development task table",
                    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Markdown links, anchors, and the development task table."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print the scanned file list"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="documentation root to check (default: repository root)",
    )
    args = parser.parse_args(argv)

    checker = DocsChecker(args.root)
    files = checker.markdown_files()
    if args.verbose:
        for path in files:
            print(f"scanned: {checker.display(path)}")
    for path in files:
        checker.check_links(path)
    table_ids = checker.check_task_table()
    checker.check_record_mentions(table_ids)

    problems = sorted(
        checker.problems, key=lambda item: (item.path, item.line, item.message)
    )
    for problem in problems:
        print(f"{problem.path}:{problem.line}: {problem.message}")

    if problems:
        files_with_problems = len({problem.path for problem in problems})
        print(
            f"docs check: {len(problems)} problem(s) in {files_with_problems} "
            f"file(s); {len(files)} files, {checker.link_count} links, "
            f"{checker.task_row_count} task rows scanned."
        )
        return 1
    if checker.in_progress_count == 0:
        # Zero in-progress tasks is allowed at phase boundaries, so this is
        # reported as information rather than as a problem.
        print("info: no task is in progress; zero is allowed")
    print(
        f"docs check passed: {len(files)} files, {checker.link_count} links, "
        f"{checker.task_row_count} task rows scanned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
