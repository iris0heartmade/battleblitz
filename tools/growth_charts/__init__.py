"""Growth-chart visualization tool.

Public layout:
    dataset  — pure data layer (no matplotlib)
    render   — matplotlib-side, layout-A per the design spec
    __main__ — CLI: ``python -m tools.growth_charts [--out DIR] [--policy NAME] ...``

Why a tool (not a route, not a notebook)?
    - Deterministic, re-runnable artefact generation.
    - No HTTP / WS plumbing — just read registries and write PNGs.
    - The renderer is a thin consumer of ``app.progression.policies``
      so any policy swap propagates here without code edits.
"""
