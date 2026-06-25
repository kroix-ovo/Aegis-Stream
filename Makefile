PYTHON ?= python3

.PHONY: test demo compile clean

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

demo:
	PYTHONPATH=src $(PYTHON) -m aegis_stream.pipeline --demo --json

compile:
	$(PYTHON) -m compileall src tests tools

clean:
	rm -rf .pytest_cache .mypy_cache htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
