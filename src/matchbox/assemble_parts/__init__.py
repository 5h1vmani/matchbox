"""Helper modules extracted from assemble.py.

assemble.py stayed a 1200-line god module doing loading, selection, CV-document
building, coverage diagnostics, changes.md reporting, and PDF rendering. Those
responsibilities now live here as focused modules; assemble.py keeps only the
orchestrators (assemble_one, polish_run, re_render_cv, assemble_cover), drift
detection, and the CLI. Nothing here imports assemble.py, so the dependency
graph is a DAG with assemble.py at the root.
"""
