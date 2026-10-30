# 审查记录：开发工作流完善（T048）

本页保留 T048 当时的审查证据与结论，其中语言、逐次任务记录与训练规则已由 T054 更新；
现行规则见 [开发工作流设计](../development_workflow.md)，不将本页历史意见作为当前规范。

## 审查范围与证据

- 任务与设计：[T048](../development.md)，[任务条目](../archive/development_tasks.md#t048-完善开发工作流并归档历史记录)，
  流程依据见 [开发工作流设计](../development_workflow.md)。
- 实现者：主代理与实现子代理（`tools/check_docs.py`、`tests/test_check_docs.py`、`Makefile`）。
  独立审查者由只读子代理担任，未参与被审查文件的编写。
- 文件范围：`AGENTS.md`、`README.md`、`docs/development.md`、
  `docs/development_workflow.md`、`docs/collaboration_review.md`、
  `docs/design/TEMPLATE.md`、`docs/review/TEMPLATE.md`、
  `docs/archive/development_tasks.md`、`docs/archive/development_records.md`、
  `tools/check_docs.py`、`tests/test_check_docs.py`、`Makefile`。
  含本次新建的未跟踪文件；用户既有的源码、`rsl_rl/` 与文档改动不在审查范围。
- 基准：本轮开始前的 `docs/development.md`（3751 行，工作区版本）。
- 验证证据：`make check`（含新增 `make docs`；219 passed + 8 subtests，
  `docs check passed: 17 files, 100 links, 49 task rows scanned`）、
  `ruff check src tools tests`、`pytest tests/test_check_docs.py`（39 passed）；
  归档一致性用切片比对脚本核对：任务条目 42 条（T001–T048）、
  完成记录 35 条，逐行与拆分前的对应区块一致，任务编号与前置依赖无变化。
- 依据：`quadruped_lab/docs/DEVELOPMENT_WORKFLOW.md` 与 `docs/COLLABORATION_REVIEW.md`
  （本机，2026-10-27 版本）作为流程参考；本仓库既有任务记录作为事实来源。
  参考仓库的做法只在适用时沿用，差异见[流程设计第 9 节](../development_workflow.md#9-与参考仓库的差异)。

## 问题与修复复核

| 编号与程度 | 文件位置 | 触发、影响、依据及建议 | 修复与验证 | 复核者及状态 |
|---|---|---|---|---|
| 1 阻塞 | `docs/development.md` 任务表 | 触发：拆分时压缩了 37 行的前置条件单元格，10 行丢失依赖编号（T009、T011、T014、T015、T016、T021、T032、T033、T035、T040 的 T001/T002/T013），3 行新增编号（T024/T025 增 T047，T026 增 T046/T047）。影响：依赖拓扑被静默改动，与「前置依赖逐项一致」的验收条件冲突。 | 37 行前置条件全部按 `git show` 重建的原文逐字恢复，依赖编号集合与拆分前一致；T024–T026 的「实现已被 T047 删除」等备注移入任务名，单元格只留编号与分号。复核：逐行比对 46 个共有编号的前置单元格，差异 0。 | 审查者：已复核通过 |
| 2 阻塞 | `docs/review/development_workflow.md`；`docs/development.md` T048 行 | 触发：审查记录是模板占位（`待审查`/`待复核`），任务却已标完成，违反「大功能缺少独立审查时不能标为完成」。 | 本表填入审查者 15 条findings 与修复结果；任务状态待审查者复核通过后维持完成。 | 审查者：已复核通过 |
| 3 一般 | `docs/archive/development_tasks.md` 头部 | 触发：头部声明「不回填状态」，正文却有 11 处 `状态：完成。` 原文。 | 头部改为：搬移保留原文（含 `状态：…` 句），但当前状态只看任务表；规则与内容一致，不删原文。 | 审查者：已复核通过 |
| 4 一般 | `docs/development.md`、`README.md` | 触发：状态在任务表之外被重述 4 处（当前任务段、T027/T028 详情、README）。 | 删除“状态：进行中/待办”行与 README 的当前任务断言，改为「状态以上方任务表为准」。 | 审查者：已复核通过 |
| 5 一般 | `docs/development.md` 阶段段 | 触发：「M3 尚未开始」与 T027（M3 范围）进行中矛盾；M0「Git 基线均已具备」与 105 项未提交改动不符。 | 改为「M0、M1 已通过，M2 未通过」；T027 的恢复与回放明确写成 M3 前期准备、不作 M3 通过依据；M0 改为「基线在 `9840fa8`，此后改动未提交」。 | 审查者：已复核通过 |
| 6 一般 | `docs/development.md` 完成记录；本页证据段 | 触发：行数写 3749 / 约 310、链接数写 101，与实测 3751 / 321 / 100 不符。 | 全部换为实测值：拆分前 3751 行、当前 321 行、`17 files, 100 links, 49 task rows scanned`（连跑 3 次一致）。 | 审查者：已复核通过 |
| 7 一般 | `tools/check_docs.py` 文档化规则 | 触发：任意标题中出现该编号即算「已文档化」，`## 后续 T042 相关讨论` 这类顺带提及也能通过，规则可绕过。 | 收紧为「编号出现在标题开头或结尾」，`### T042 导出策略` 与 `### 2026 年 10 月 27 日 T042` 通过，顺带提及不通过；docstring 同步。新增 7 条端到端用例覆盖。 | 审查者：已复核通过 |
| 8 一般 | 前置条件单元格写法 | 触发：单元格里所有编号都被当依赖，「实现已被 T047 删除」变成硬依赖，T047 回退即误报。 | 二选一取两者：写法上单元格只留编号与 `；`（备注移入任务名）；解析上新增 `parse_prerequisites` 只读第一个 `；` 之前的内容。两条同时生效并有单元测试。 | 审查者：已复核通过 |
| 9 一般 | `AGENTS.md` 语言例外 | 触发：`tests/test_check_docs.py` 有 19 行中文（CJK slug、状态词），规则未覆盖。 | 语言段补「`tests/` 中的中文只作为被测数据保留，注释与断言消息仍用英文」；测试文件 docstring 说明同样内容。 | 审查者：已复核通过 |
| 10 一般 | `docs/archive/development_tasks.md` 头部；`docs/development.md` 完成记录 | 触发：头部称「按编号排列」，实际 T027–T031 合并、T042/T043 只有完成记录，与「42 条」的表述不符。 | 头部写明合并块与记录型的例外；完成记录改成「42 条条目；T027–T031 合并为前瞻块，T042/T043 只有完成记录」。 | 审查者：已复核通过 |
| 11 一般 | `docs/archive/development_tasks.md` T026 条目 | 触发：原文 3 行被就地改写，追加段带过期数字「180 项测试」。 | 3 行恢复原文，「2026-10-28 更新」改为「追加（2026-10-28）」，数字改为「当时 180 项测试」以免与当前 219 项混淆。 | 审查者：已复核通过 |
| 12 建议 | `tools/check_docs.py` 扫描范围 | 触发：`src/**/README.md` 三个文件（11 个本地链接）不在扫描范围，改路径不会被拦住。 | 暂不扩大范围（会把 `make docs` 绑到代码移动上）；在 docstring 与本节显式写明只覆盖 `AGENTS.md`、`README.md`、`docs/`，三个 README 由包评审时人工核对（当前 11 链接全有效）。 | 审查者：已复核通过 |
| 13 建议 | `tests/test_check_docs.py` | 触发：31 个用例全为纯函数，整树行为只靠手工演示，`make test` 不防回归。 | 新增 7 条 `tmp_path` + `--root` 端到端用例（一致树、坏链接、坏锚点、重复编号、依赖环、备注不算依赖），共 39 条；`pytest tests/test_check_docs.py` → 39 passed。 | 审查者：已复核通过 |
| 14 建议 | `docs/archive/development_tasks.md` T048 范围 | 触发：范围未列 `docs/setup.md` 与 `docs/review/development_workflow.md`，但两者都在本次交付内。 | 范围补齐这两个文件（`setup.md` 新增训练日志可视化一节、审查记录为交付件）。 | 审查者：已复核通过 |
| 15 建议 | `docs/development_workflow.md` §9 差异表 | 事实：5 行差异经审查者逐条核对全部成立，无编造。 | 无需修改；差异表的核对方式与日期留待下次补充。 | 审查者（已确认） |

## 最终结论

- 审查状态：**独立审查通过。** 审查者两轮复核（首轮 15 条问题，次轮逐条复验）后确认
  关闭，其中第 1、2 条阻塞项与第 3–11 条一般项全部修复，第 12–14 条建议项已落实或记录理由，
  第 15 条确认无需修改。第 4、6 条在次轮尚有文案残留（README 复述状态、行数 321/3749 与
  219/39 等旧值），已按复核意见改完并重跑验证。
- 最终集成验证：修复后 `make check` 通过（219 passed + 8 subtests），
  `make docs` 输出 `17 files, 100 links, 49 task rows scanned`，
  `pytest tests/test_check_docs.py` 39 passed，`ruff check src tools tests` 通过。
- 审查者的未验证项如实保留：`make lock-check` 的离网行为、GPU/训练类历史断言、
  拆分前 3751 行的原始文件已不可恢复（由 HEAD 3536 行 + 新增 215 行推算）。
- 限制与后续：T027 的定量评估与 T028 的导出仍未做；本轮未执行 Git 暂存、提交或推送。

审查通过不授予 Git 提交或发布权限，任务状态只在[开发流程与任务](../development.md)维护。
