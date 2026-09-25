.PHONY: help test test-unit test-install lint install uninstall configure preview doctor bench catalog gallery clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: test-unit test-install  ## Run every test

test-unit:  ## The Python suite
	python3 -m unittest discover -s tests

test-install:  ## install.sh against throwaway homes
	bash tests/test_install.sh

lint:  ## Byte-compile everything; check the catalog and docs are in sync
	python3 -m compileall -q claude_statusline statusline.py tools
	python3 -m unittest tests.test_docs tests.test_system.CliTests.test_catalog_in_sync

install:  ## Install into ~/.claude (a shim that runs this checkout)
	./install.sh

uninstall:  ## Put the previous status line back
	./install.sh --uninstall

configure:  ## The interactive configurator
	@python3 statusline.py configure

preview:  ## Your config at three widths
	@python3 statusline.py preview --width 80,120,$${COLUMNS:-160}

doctor:  ## What is installed and in force
	@python3 statusline.py doctor

bench:  ## How long a refresh takes
	@python3 statusline.py bench

catalog:  ## Regenerate the skill's segment catalog from the code
	@python3 statusline.py segments --markdown > skills/design/reference/catalog.md

gallery:  ## Redraw docs/gallery.png (needs pycairo)
	@python3 tools/gallery.py

clean:  ## Remove caches
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf "$${XDG_RUNTIME_DIR:-/tmp}/claude-statusline"
