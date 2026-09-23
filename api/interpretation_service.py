"""Background interpretation orchestration."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from api.interpretation_store import InterpretationStore


class InterpretationService:
    def __init__(
        self,
        store: InterpretationStore,
        run_job_fn: Callable,
        load_config_fn: Callable,
        write_interpretation_fn: Callable,
        normalize_timeout_fn: Callable,
        logger=None,
    ):
        self.store = store
        self.run_job_fn = run_job_fn
        self.load_config_fn = load_config_fn
        self.write_interpretation_fn = write_interpretation_fn
        self.normalize_timeout_fn = normalize_timeout_fn
        self.log = logger or logging.getLogger(__name__)

    def cleanup_stale(self):
        config = self.load_config_fn()
        max_pending = int(config.get("interpretation", {}).get("max_pending_seconds", 180))
        if max_pending <= 0:
            return
        for job_key in self.store.stale_jobs(max_pending):
            self.store.expire(job_key, f"Timed out after {max_pending}s")
            self.log.error(f"Interpretation job expired: {job_key} (>{max_pending}s)")

    def is_current(self, job_key: str, token: int) -> bool:
        return self.store.is_current(job_key, token)

    def start(
        self,
        entry_dir: Path,
        timestamp: str,
        interpreter_key: str,
        text: str,
        job_key: str,
        prompt_signature: str,
    ) -> int:
        worker_token = self.store.start(job_key)

        def worker():
            try:
                success, error = self.run_job_fn(
                    entry_dir=entry_dir,
                    timestamp=timestamp,
                    interpreter_key=interpreter_key,
                    text=text,
                    job_key=job_key,
                    worker_token=worker_token,
                    current_prompt_signature=prompt_signature,
                    load_config_fn=self.load_config_fn,
                    is_job_current_fn=self.is_current,
                    write_interpretation_fn=self.write_interpretation_fn,
                    normalize_timeout_fn=self.normalize_timeout_fn,
                )
                if success:
                    self.store.clear_error(job_key)
                    self.log.info(
                        f"Interpretation ({interpreter_key}) done: {timestamp} via job runner"
                    )
                elif error and self.is_current(job_key, worker_token):
                    self.store.errors[job_key] = error
            except Exception as error:
                if self.is_current(job_key, worker_token):
                    self.store.errors[job_key] = str(error)
                self.log.error(f"Interpretation failed: {error}")
            finally:
                self.store.finish(job_key, worker_token)

        threading.Thread(target=worker, daemon=True).start()
        return worker_token