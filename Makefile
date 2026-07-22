.PHONY: test audit checksums

test:
	python -m unittest discover -s tests -v

audit:
	python tools/release_audit.py

checksums:
	python tools/make_checksums.py results/publication
