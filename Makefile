.PHONY: help test lint install uninstall demo doctor ruler clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test:  ## Run the test suite
	python3 -m unittest discover -s tests -v

lint:  ## Byte-compile and check the example config stays in sync
	python3 -m py_compile statusline.py
	python3 -m unittest tests.test_statusline.ConfigTests -v

install:  ## Symlink into ~/.claude and patch settings.json
	./install.sh

uninstall:  ## Restore the previous statusline
	./install.sh --uninstall

demo:  ## Render a sample payload
	@python3 statusline.py --demo

doctor:  ## Report resolved config and detected width
	@python3 statusline.py --doctor

ruler:  ## Print calibration rulers
	@python3 statusline.py --ruler

clean:  ## Remove caches
	rm -rf __pycache__ tests/__pycache__ .pytest_cache
	rm -rf "$${XDG_RUNTIME_DIR:-/tmp}/claude-statusline"
