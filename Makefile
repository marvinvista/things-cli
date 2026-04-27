.PHONY: install install-pipx test live-test validate-public diagnose export-smoke clean

VENV := .venv
PY := $(VENV)/bin/python
THINGS := $(VENV)/bin/things

install:
	python3 -m venv $(VENV)
	$(PY) -m pip install setuptools wheel
	$(PY) -m pip install --no-build-isolation -e .

install-pipx:
	scripts/install-pipx.sh

test:
	python3 -m unittest discover -s tests
	python3 -m py_compile things_cli/client.py things_cli/cli.py things_cli/workflows.py things_cli/audit.py things_cli/schemas.py things_cli/snapshots.py things_cli/__main__.py
	python3 scripts/validate_public_surface.py

live-test:
	THINGS_LIVE_TESTS=1 $(PY) -m unittest tests.test_live_things

validate-public:
	python3 scripts/validate_public_surface.py

diagnose:
	$(THINGS) diagnose

export-smoke:
	$(THINGS) export --output things-snapshot.json

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	rm -rf things_cli.egg-info build dist
