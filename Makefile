#==================================================================================================
# gfp-cli Project Makefile
#==================================================================================================

.DEFAULT_GOAL := help
SHELL         := /bin/bash
PROJ_NAME     ?= gfp-cli
MAKEFILE_ICON := " "

#--------------------------------------------------------------------------------------------------
# UI Styling & Terminal Output
#--------------------------------------------------------------------------------------------------
CYAN   := \033[38;2;137;221;255m
ORANGE := \033[38;2;250;179;135m
BOLD   := \033[1m
NC     := \033[0m

ifndef StageInfo
define StageInfo
	@printf "$(BOLD)$(CYAN)-------------------------------$(NC)\n"
	@printf "$(BOLD)$(ORANGE)<<-$(NC)$(CYAN) %b Stage - %s $(BOLD)$(ORANGE)->>$(NC)\n" $(MAKEFILE_ICON) $(1)
	@printf "$(BOLD)$(CYAN)-------------------------------$(NC)\n"
endef
endif

#--------------------------------------------------------------------------------------------------
# Environment & Path Configuration
#--------------------------------------------------------------------------------------------------
WA          := $(CURDIR)
OUTPUT_DIR  ?= $(WA)/output
BIN_DIR     ?= $(OUTPUT_DIR)/bin
RESULTS_DIR ?= $(OUTPUT_DIR)/results
SRC_DIR     ?= $(WA)/commands
CLI_ARGS    ?=

# Python Interpreter & Tools Resolution (.venv fallback to system PATH)
PYTHON      ?= $(WA)/.venv/bin/python3
ifeq ($(wildcard $(PYTHON)),)
PYTHON      := python3
endif

RUFF        ?= $(WA)/.venv/bin/ruff
ifeq ($(wildcard $(RUFF)),)
RUFF        := ruff
endif

MYPY        ?= $(WA)/.venv/bin/mypy
ifeq ($(wildcard $(MYPY)),)
MYPY        := mypy
endif

PYTEST      ?= $(WA)/.venv/bin/pytest
ifeq ($(wildcard $(PYTEST)),)
PYTEST      := pytest
endif

TEST_FILTER ?=

# --- Optional Guardrails: Ensure mandatory tools are available ---
ifeq ($(filter help clean clean-all,$(or $(MAKECMDGOALS),$(.DEFAULT_GOAL))),)
CHECK_TOOLS := $(PYTHON)
$(foreach t,$(CHECK_TOOLS),$(if $(shell command -v $(t) 2>/dev/null),,$(warning Warning: Tool $(t) not found in PATH or .venv)))
endif

#--------------------------------------------------------------------------------------------------
# Enum Validation Helpers
#--------------------------------------------------------------------------------------------------
# Validates $(1) against options defined in $($(2)_OPTIONS)
define validate_var
    $(if $(filter $(1),$($(2)_OPTIONS)),,$(error Invalid $(2) '$(1)'. Must be one of: $($(2)_OPTIONS)))
endef

TEST_STAGE         ?= unit
TEST_STAGE_OPTIONS := unit e2e all

#==================================================================================================
# Targets
#==================================================================================================

# -----------------------------------------------------------------------------
# [Static Analysis]
# -----------------------------------------------------------------------------

.PHONY: lint
lint: lint-ruff lint-mypy ## [Static Analysis] Run all linters (ruff + mypy)

.PHONY: lint-ruff
lint-ruff: ## [Static Analysis] Run ruff linter on source code
	$(call StageInfo, $@)
	$(RUFF) check . $(CLI_ARGS)

.PHONY: lint-mypy
lint-mypy: ## [Static Analysis] Run mypy static type checking
	$(call StageInfo, $@)
	$(MYPY) . $(CLI_ARGS)

.PHONY: format
format: ## [Static Analysis] Auto-format source code in-place using ruff
	$(call StageInfo, $@)
	$(RUFF) format .
	$(RUFF) check --fix .

.PHONY: format-check
format-check: ## [Static Analysis] Verify code formatting and linting without modifying files
	$(call StageInfo, $@)
	$(RUFF) format --check .
	$(RUFF) check .

.PHONY: check-syntax
check-syntax: ## [Static Analysis] Verify Python bytecode compilation syntax
	$(call StageInfo, $@)
	$(PYTHON) -m py_compile gfp.py utils.py commands/*.py

.PHONY: check
check: check-syntax format-check lint ## [Static Analysis] Run syntax verification, format check, and linters

# -----------------------------------------------------------------------------
# [Test]
# -----------------------------------------------------------------------------

.PHONY: test
test: ## [Test] Run tests for chosen stage (Usage: make test [TEST_STAGE=unit|e2e|all] [TEST_FILTER=...])
	$(call StageInfo, $@)
	@$(call validate_var,$(TEST_STAGE),TEST_STAGE)
	@case "$(TEST_STAGE)" in \
		unit) $(MAKE) test-unit TEST_FILTER="$(TEST_FILTER)" ;; \
		e2e)  $(MAKE) test-e2e TEST_FILTER="$(TEST_FILTER)" ;; \
		all)  $(MAKE) test-all TEST_FILTER="$(TEST_FILTER)" ;; \
	esac

.PHONY: test-unit
test-unit: ## [Test] Run unit & regression test suite stage (tests/run_tests.py)
	$(call StageInfo, $@)
	@mkdir -p "$(RESULTS_DIR)"
	$(PYTHON) tests/run_tests.py $(if $(TEST_FILTER),-k "$(TEST_FILTER)",)

.PHONY: test-e2e
test-e2e: ## [Test] Run end-to-end integration test stage (Docker playground)
	$(call StageInfo, $@)
	@mkdir -p "$(RESULTS_DIR)"
	@if [ -d "$(WA)/docker" ]; then \
		$(MAKE) -C docker test $(if $(TEST_FILTER),ARGS="-k '$(TEST_FILTER)'",); \
	else \
		echo "Error: docker directory not found; cannot run E2E stage."; exit 1; \
	fi

.PHONY: test-all
test-all: test-unit test-e2e ## [Test] Run all test stages sequentially (unit -> e2e)
	$(call StageInfo, $@)

.PHONY: test-single
test-single: ## [Test] Run targeted single test (Usage: make test-single TEST_NAME=<pattern>)
	$(call StageInfo, $@)
	@if [ -z "$(TEST_NAME)" ]; then \
		echo "Error: TEST_NAME is required. Usage: make test-single TEST_NAME=<pattern>"; \
		exit 1; \
	fi
	@mkdir -p "$(RESULTS_DIR)"
	$(PYTHON) tests/run_tests.py -k "$(TEST_NAME)" -v

.PHONY: test-coverage
test-coverage: ## [Test] Run test suite and generate coverage report
	$(call StageInfo, $@)
	@mkdir -p "$(RESULTS_DIR)"
	@if $(PYTHON) -m coverage --version >/dev/null 2>&1; then \
		$(PYTHON) -m coverage run --source=gfp,utils,commands tests/run_tests.py && \
		$(PYTHON) -m coverage report -m && \
		$(PYTHON) -m coverage html -d "$(RESULTS_DIR)/coverage"; \
		echo "Coverage HTML report written to $(RESULTS_DIR)/coverage/index.html"; \
	elif $(PYTEST) --version >/dev/null 2>&1 && $(PYTEST) --help | grep -q -- '--cov'; then \
		$(PYTEST) --cov=. --cov-report=html:"$(RESULTS_DIR)/coverage" tests/; \
		echo "Coverage HTML report written to $(RESULTS_DIR)/coverage/index.html"; \
	else \
		echo "Coverage package not installed. Install via: pip install coverage pytest-cov"; \
		exit 1; \
	fi

# -----------------------------------------------------------------------------
# [Clean]
# -----------------------------------------------------------------------------

.PHONY: clean
clean: ## [Clean] Remove intermediate build and test outputs
	$(call StageInfo, $@)
	@if [ -n "$(OUTPUT_DIR)" ] && [ -d "$(OUTPUT_DIR)" ]; then \
		rm -rf "$(OUTPUT_DIR)"; \
		echo "Cleaned $(OUTPUT_DIR)"; \
	fi

.PHONY: clean-all
clean-all: clean ## [Clean] Remove all output artifacts, caches, and bytecode
	$(call StageInfo, $@)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache .cache .ruff_cache .mypy_cache
	@echo "Cleaned all cache directories and bytecode files."

# -----------------------------------------------------------------------------
# [Help]
# -----------------------------------------------------------------------------

.PHONY: help
help: ## [Help] Show this interactive help menu
	$(call StageInfo, $@)
	@grep -hE '^[a-zA-Z0-9_.-]+:[^#]*## .*$$' $(MAKEFILE_LIST) | \
	 sort -t "[" -k2 | \
	 awk 'BEGIN {FS = ":.*?## "}; { \
	    if ($$2 ~ /^\[[^]]+\]/) { \
	        category = substr($$2, 2, index($$2, "]") - 2); \
	        desc = substr($$2, index($$2, "]") + 2); \
	    } else { \
	        category = "General"; \
	        desc = $$2; \
	    } \
	    if (category != last_cat) { \
	        print "\n$(BOLD)$(ORANGE)" category ":$(NC)"; \
	        last_cat = category; \
	    } \
	    printf "  $(CYAN)%-22s$(NC) %s\n", $$1, desc \
	 }'
