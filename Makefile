.PHONY: help test test-unit test-install lint install uninstall demo doctor ruler catalog validate preview clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: test-unit test-install  ## Run every test

test-unit:  ## Run the Python test suite
	python3 -m unittest discover -s tests -v

test-install:  ## Run the install.sh bootstrap tests (isolated $$HOME)
	bash tests/test_install.sh

lint:  ## Byte-compile; check the example config and skill catalog stay in sync
	python3 -m compileall -q claude_statusline statusline.py
	python3 -m unittest tests.test_statusline.ConfigTests tests.test_skill -v

install:  ## Symlink into ~/.claude and patch settings.json
	./install.sh

uninstall:  ## Restore the previous statusline
	./install.sh --uninstall

demo:  ## Render a sample payload
	@python3 statusline.py --demo

catalog:  ## Regenerate the skill's segment catalog from the code
	@python3 statusline.py segments --markdown > skills/design/reference/catalog.md

validate:  ## Validate the config file in use
	@python3 statusline.py validate

preview:  ## Preview the config in use at three widths
	@python3 statusline.py preview --width 80,120,$${COLUMNS:-160}

doctor:  ## Report resolved config and detected width
	@python3 statusline.py --doctor

ruler:  ## Print calibration rulers
	@python3 statusline.py --ruler

clean:  ## Remove caches
	rm -rf __pycache__ tests/__pycache__ .pytest_cache
	rm -rf "$${XDG_RUNTIME_DIR:-/tmp}/claude-statusline"
