.PHONY: manager install

manager:
	uv run python manager/serve.py --open $(ROOT:%=--root %) $(HOST:%=--host %) $(PORT:%=--port %)

install:
	uv run --no-project --with PyYAML python install.py "$(NAME)" $(if $(STATUS),--status) $(if $(ADOPT),--adopt)
