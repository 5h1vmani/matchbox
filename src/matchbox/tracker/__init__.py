"""Application tracker — the pipeline model behind the React dashboard.

* `rules`   — pure logic (stage flow, default actions, staleness, dates).
* `repo`    — persistence + serialization into the SPA view-model.
* `service` — the inline action effects (ported from the design store).
"""
