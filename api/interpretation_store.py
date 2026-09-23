"""In-memory state for background interpretation jobs."""

from __future__ import annotations

import time


class InterpretationStore:
    def __init__(self):
        self.queue = {}
        self.errors = {}
        self.tokens = {}

    def token(self, job_key: str) -> int:
        return int(self.tokens.get(job_key, 0))

    def is_current(self, job_key: str, token: int) -> bool:
        return self.token(job_key) == int(token)

    def start(self, job_key: str) -> int:
        token = self.token(job_key)
        self.queue[job_key] = time.time()
        self.errors.pop(job_key, None)
        return token

    def cancel(self, job_key: str) -> bool:
        self.tokens[job_key] = self.token(job_key) + 1
        was_pending = job_key in self.queue
        self.queue.pop(job_key, None)
        self.errors.pop(job_key, None)
        return was_pending

    def clear_error(self, job_key: str):
        self.errors.pop(job_key, None)

    def finish(self, job_key: str, token: int):
        if self.is_current(job_key, token):
            self.queue.pop(job_key, None)

    def stale_jobs(self, max_pending_seconds: float) -> list[str]:
        now = time.time()
        return [
            key
            for key, started_at in self.queue.items()
            if max_pending_seconds > 0 and now - started_at > max_pending_seconds
        ]

    def expire(self, job_key: str, message: str):
        self.queue.pop(job_key, None)
        self.errors[job_key] = message