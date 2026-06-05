"""The agent-task queue: the loop between the deterministic app and the agent.

The app (dashboard + discovery/tailoring effects) ENQUEUES typed intents; the
user's agent DRAINS them (claim -> work -> complete/fail). This replaces the
`runs/<id>/work-queue.json` copy-paste hand-off with a queryable queue, so the
user is no longer the message bus between the app and the agent.
"""
