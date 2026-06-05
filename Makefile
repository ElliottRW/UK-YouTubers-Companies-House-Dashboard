PY = .venv/bin/python

run:
	$(PY) main.py

fetch:
	$(PY) scripts/fetch_all.py

fetch-%:
	$(PY) scripts/fetch_all.py $*

sheets:
	$(PY) scripts/export_to_sheets.py

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
