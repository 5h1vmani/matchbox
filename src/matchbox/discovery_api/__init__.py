"""Discovery backend — rules, serialization (DB job -> Role), and decisions.

Mirrors the tracker's pure-rules / DAL / action-effects split. Renders only
what the upstream scoring + eligibility judge already wrote into
``job.score_breakdown_json``; it never scores or judges in the request path.
"""
