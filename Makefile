UV ?= uv
RUN = $(UV) run --no-sync

CHECK_LOCK = $(UV) lock --check --offline --python 3.12
CHECK_LINT = $(RUN) ruff check src tools tests
CHECK_TEST = PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(RUN) python -B -m pytest -q tests --basetemp="$$check_dir/pytest" -o "cache_dir=$$check_dir/pytest-cache"
CHECK_MODEL = $(RUN) python -B tools/check_robot.py
CHECK_DOCS = $(RUN) python -B tools/check_docs.py
CHECK_DIFF = git diff --check && git diff --cached --check

# 每次调用使用独立目录；保留失败现场，由本次任务的负责人清理。
define run_check
	@set -eu; \
	if [ -L "$(CURDIR)/.artifacts" ] || [ -L "$(CURDIR)/.artifacts/checks" ]; then \
	  printf '%s\n' 'Check artifact directories must not be symlinks.' >&2; exit 1; \
	fi; \
	mkdir -p "$(CURDIR)/.artifacts/checks"; \
	check_dir=$$(mktemp -d "$(CURDIR)/.artifacts/checks/run-XXXXXXXX"); \
	mkdir -p "$$check_dir/tmp"; \
	export TMPDIR="$$check_dir/tmp" PYTHONDONTWRITEBYTECODE=1; \
	export RUFF_CACHE_DIR="$$check_dir/ruff" WARP_CACHE_PATH="$$check_dir/warp"; \
	export TORCHINDUCTOR_CACHE_DIR="$$check_dir/torch"; \
	printf 'Check artifacts: %s\n' "$$check_dir"; \
	$(1)
endef

.DEFAULT_GOAL := help
.PHONY: help check lint test model docs lock-check viewer

help:
	@printf '%s\n' \
	  'make check       检查锁文件、代码、测试、模型、文档和差异空白' \
	  'make lint        Ruff 代码检查' \
	  'make test        运行项目测试，隔离自动加载的外部插件' \
	  'make model       模型编译与关节映射检查' \
	  'make docs        检查文档链接、锚点与任务表一致性' \
	  'make lock-check  离线检查锁文件一致性' \
	  'make viewer      打开静态模型预览，需要图形桌面' \
	  '检查产物按次保存于 .artifacts/checks/run-*，任务结束后按实际路径清理'

check:
	$(call run_check,$(CHECK_LOCK); $(CHECK_LINT); $(CHECK_TEST); $(CHECK_MODEL); $(CHECK_DOCS); $(CHECK_DIFF))

lint:
	$(call run_check,$(CHECK_LINT))

test:
	$(call run_check,$(CHECK_TEST))

model:
	$(call run_check,$(CHECK_MODEL))

docs:
	$(call run_check,$(CHECK_DOCS))

lock-check:
	$(call run_check,$(CHECK_LOCK))

viewer:
	$(call run_check,$(CHECK_MODEL) --viewer)
