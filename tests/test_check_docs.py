"""Unit tests for the pure helpers in ``tools/check_docs.py``.

The parsing and graph helpers take strings and mappings and never touch the
filesystem. Whole-repository consistency is covered by ``make docs``, so these
tests do not depend on the current documentation content. The few end-to-end
cases at the end build a throw-away tree under ``tmp_path`` and call the
checker through ``--root``, which is how the failure paths stay covered by
``make test`` instead of by a manual demonstration.

Chinese text appears here as *test data* (CJK heading slugs, task status words),
which is why those strings stay in Chinese.
"""

from __future__ import annotations

import pytest
from tools import check_docs
from tools.check_docs import (
    document_anchors,
    extract_task_ids,
    find_cycles,
    heading_anchors,
    mask_inline_code,
    parse_link_target,
    parse_prerequisites,
    slugify,
    split_markdown_lines,
    table_cells,
)

# ---------- slug generation ----------


def test_slugify_lowercases_and_replaces_spaces():
    assert slugify("Hello World") == "hello-world"


def test_slugify_keeps_cjk_characters():
    assert slugify("中文标题") == "中文标题"
    assert slugify("T038 标定 HOME 站姿") == "t038-标定-home-站姿"


def test_slugify_drops_punctuation_but_keeps_dash_and_underscore():
    assert slugify("T030 两类执行器/IMU 标定配置、原始轨迹、对比报告和 DR 事件") == (
        "t030-两类执行器imu-标定配置原始轨迹对比报告和-dr-事件"
    )
    assert slugify("a_b-c") == "a_b-c"


def test_slugify_collapses_whitespace_runs_and_strips_dashes():
    assert slugify("  spaced   out  ") == "spaced-out"
    assert slugify("---wrapped---") == "wrapped"


def test_slugify_keeps_inline_code_backticks_out():
    assert slugify("`make docs` check") == "make-docs-check"


# ---------- duplicate headings and HTML anchors ----------


def test_heading_anchors_suffix_duplicates_in_document_order():
    anchors = heading_anchors(["Notes", "Notes", "Notes"])
    assert anchors == {"notes", "notes-1", "notes-2"}


def test_heading_anchors_keep_duplicates_independent_per_slug():
    anchors = heading_anchors(["Notes", "Other", "Notes"])
    assert anchors == {"notes", "notes-1", "other"}


def test_heading_anchors_avoid_collision_with_generated_suffixes():
    anchors = heading_anchors(["Notes", "Notes", "Notes 1"])
    assert anchors == {"notes", "notes-1", "notes-1-1"}


def test_document_anchors_collect_headings_and_html_targets():
    text = "\n".join(
        [
            "# Title",
            '<a name="manual"></a>',
            '<span id="explicit-id"></span>',
            "## 中文标题",
            "## 中文标题",
        ]
    )
    assert document_anchors(text) == {
        "title",
        "manual",
        "explicit-id",
        "中文标题",
        "中文标题-1",
    }


def test_document_anchors_ignore_fenced_code_blocks():
    text = "\n".join(
        [
            "# Real",
            "```bash",
            "## Not A Heading",
            "```",
            "Keep `# inline` as text.",
        ]
    )
    assert document_anchors(text) == {"real"}


def test_document_anchors_ignore_closing_hashes():
    assert document_anchors("## Section ##") == {"section"}


# ---------- link target parsing ----------


def test_parse_link_target_returns_plain_path():
    assert parse_link_target("docs/setup.md") == "docs/setup.md"


def test_parse_link_target_strips_angle_wrapper():
    assert parse_link_target("<docs/a b.md>") == "docs/a b.md"


def test_parse_link_target_strips_title():
    assert parse_link_target('docs/setup.md "安装说明"') == "docs/setup.md"
    assert parse_link_target('<docs/a b.md> "标题"') == "docs/a b.md"


def test_parse_link_target_keeps_anchor():
    assert parse_link_target("../development.md#t035-实现并接入-3532-nt-pd-执行器") == (
        "../development.md#t035-实现并接入-3532-nt-pd-执行器"
    )


@pytest.mark.parametrize("raw", ["", "   ", "<>"])
def test_parse_link_target_rejects_empty_targets(raw):
    assert parse_link_target(raw) is None


def test_mask_inline_code_hides_code_spans_only():
    line = "`[a](missing.md)` then [b](ok.md)"
    masked = mask_inline_code(line)
    assert "missing.md" not in masked
    assert "[b](ok.md)" in masked
    assert len(masked) == len(line)


# ---------- task-id extraction ----------


def test_extract_task_ids_returns_unique_ids_in_order():
    text = "T003、T001 依赖 T003；T001 已完成"
    assert extract_task_ids(text) == ["T003", "T001"]


def test_extract_task_ids_rejects_embedded_digits():
    text = "T170157 and T0012 and T12 and T999; T042 valid"
    assert extract_task_ids(text) == ["T999", "T042"]


def test_extract_task_ids_handles_prose_without_ids():
    assert extract_task_ids("无前置条件") == []


# ---------- prerequisite cells ----------


def test_parse_prerequisites_reads_ids_before_the_note():
    assert parse_prerequisites("T023、T025；入口形态已被 T046/T047 取代") == [
        "T023",
        "T025",
    ]
    assert parse_prerequisites("T000；不依赖 T001 提交，仅只读评审代码") == ["T000"]


def test_parse_prerequisites_keeps_every_id_without_a_note():
    assert parse_prerequisites("T028、T029、T030") == ["T028", "T029", "T030"]
    assert parse_prerequisites("无") == []


# ---------- cycle detection ----------


def test_find_cycles_accepts_acyclic_graph():
    edges = {"T001": ["T000"], "T002": ["T001"], "T003": ["T001", "T002"]}
    assert find_cycles(edges) == []


def test_find_cycles_reports_self_loop():
    assert find_cycles({"T001": ["T001"]}) == [["T001", "T001"]]


def test_find_cycles_reports_path_in_dependency_order():
    edges = {"T001": ["T003"], "T002": ["T001"], "T003": ["T002"]}
    cycles = find_cycles(edges)
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"T001", "T002", "T003"}
    assert len(cycle) == 4


def test_find_cycles_reports_each_cycle_once():
    edges = {"T001": ["T002"], "T002": ["T001"], "T003": ["T001"]}
    assert find_cycles(edges) == [["T001", "T002", "T001"]]


def test_find_cycles_tolerates_unknown_nodes():
    assert find_cycles({"T001": ["T999"]}) == []


# ---------- line and table scanning ----------


def test_split_markdown_lines_skips_fenced_blocks():
    text = "\n".join(
        ["first", "```", "hidden", "```", "second", "~~~", "also hidden", "~~~"]
    )
    assert list(split_markdown_lines(text)) == [
        (1, "first"),
        (5, "second"),
    ]


def test_table_cells_splits_and_strips():
    assert table_cells("| T001 | title | 完成 | T000 |") == [
        "T001",
        "title",
        "完成",
        "T000",
    ]


def test_table_cells_keeps_escaped_pipes_in_one_cell():
    assert table_cells(r"| T001 | a \| b | 完成 | 无 |") == [
        "T001",
        "a | b",
        "完成",
        "无",
    ]


def test_table_cells_rejects_prose():
    assert table_cells("Task T001 is done") is None


# ---------- end-to-end checks on a throw-away tree ----------


def _tree(root, tasks, extra_files=None):
    """Write a minimal documentation tree and return its root."""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    rows = "\n".join(
        f"| {task_id} | {title} | {status} | {prerequisites} |"
        for task_id, title, status, prerequisites in tasks
    )
    entries = "\n\n".join(
        f"### {task_id} {title}" for task_id, title, _, _ in tasks
    )
    (root / "docs/development.md").write_text(
        f"# dev\n\n| 编号 | 任务 | 状态 | 前置条件 |\n|---|---|---|---|\n{rows}\n\n{entries}\n",
        encoding="utf-8",
    )
    for name, text in (extra_files or {}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _run(root, capsys):
    """Run the checker against ``root`` and return ``(exit code, output)``."""
    code = check_docs.main(["--root", str(root)])
    return code, capsys.readouterr().out


def test_end_to_end_accepts_a_consistent_tree(tmp_path, capsys):
    root = _tree(
        tmp_path,
        [("T001", "first", "完成", "无"), ("T002", "second", "进行中", "T001")],
    )
    code, output = _run(root, capsys)
    assert code == 0
    assert "docs check passed" in output


def test_end_to_end_reports_a_missing_link(tmp_path, capsys):
    root = _tree(tmp_path, [("T001", "first", "完成", "无")])
    (root / "docs/development.md").write_text(
        (root / "docs/development.md").read_text(encoding="utf-8")
        + "\n[gone](missing.md)\n",
        encoding="utf-8",
    )
    code, output = _run(root, capsys)
    assert code == 1
    assert "link target does not exist: missing.md" in output


def test_end_to_end_reports_a_missing_anchor(tmp_path, capsys):
    root = _tree(
        tmp_path,
        [("T001", "first", "完成", "无")],
        {"docs/other.md": "# other\n"},
    )
    (root / "docs/development.md").write_text(
        (root / "docs/development.md").read_text(encoding="utf-8")
        + "\n[x](other.md#nope)\n",
        encoding="utf-8",
    )
    code, output = _run(root, capsys)
    assert code == 1
    assert "anchor not found in docs/other.md: #nope" in output


def test_end_to_end_reports_a_duplicate_id(tmp_path, capsys):
    root = _tree(
        tmp_path,
        [("T001", "first", "完成", "无"), ("T001", "again", "完成", "无")],
    )
    code, output = _run(root, capsys)
    assert code == 1
    assert "duplicate task id T001" in output


def test_end_to_end_reports_a_cycle(tmp_path, capsys):
    root = _tree(
        tmp_path,
        [("T001", "first", "完成", "T002"), ("T002", "second", "完成", "T001")],
    )
    code, output = _run(root, capsys)
    assert code == 1
    assert "prerequisite cycle: T001 -> T002 -> T001" in output


def test_end_to_end_ignores_a_prerequisite_note(tmp_path, capsys):
    root = _tree(
        tmp_path,
        [
            ("T001", "first", "完成", "无"),
            ("T002", "second", "完成", "T001；实现已被 T003 取代"),
            ("T003", "third", "待办", "无"),
        ],
    )
    code, output = _run(root, capsys)
    assert code == 0, output
