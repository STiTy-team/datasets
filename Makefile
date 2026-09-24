.PHONY: manager

manager:
	uv run python manager/serve.py --open $(ROOT:%=--root %) $(HOST:%=--host %) $(PORT:%=--port %)
