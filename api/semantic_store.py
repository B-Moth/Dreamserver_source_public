"""Persistent, thread-safe state for Dream Map semantic groups."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path


class SemanticStore:
    def __init__(self, path: Path, logger=None):
        self.path = Path(path)
        self.log = logger or logging.getLogger(__name__)
        self.lock = threading.Lock()
        self.loaded = False
        self.tag_to_group = {}
        self.pending_tags = set()
        self.generation = 0

    def ensure_loaded(self):
        if self.loaded:
            return
        with self.lock:
            if self.loaded:
                return
            if self.path.exists():
                try:
                    with open(self.path) as store_file:
                        data = json.load(store_file)
                    stored = data.get("tag_to_group", {}) if isinstance(data, dict) else {}
                    self.tag_to_group = {
                        str(key).strip().lower(): str(value).strip()
                        for key, value in stored.items()
                        if str(key).strip() and str(value).strip()
                    }
                except Exception as error:
                    self.log.warning(f"Failed to load semantic groups store: {error}")
                    self.tag_to_group = {}
            self.loaded = True

    def reset(self):
        with self.lock:
            self.generation += 1
            self.tag_to_group = {}
            self.pending_tags = set()
            self.loaded = True
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception as error:
            self.log.warning(f"Failed to clear semantic groups store: {error}")

    def current_generation(self) -> int:
        with self.lock:
            return int(self.generation)

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
                "generation": self.generation,
                "tag_to_group": self.tag_to_group,
            }
            temporary_path = self.path.with_suffix(".tmp")
            with open(temporary_path, "w") as store_file:
                json.dump(payload, store_file, indent=2, ensure_ascii=False)
            temporary_path.replace(self.path)

    def snapshot(self) -> tuple[dict, set]:
        with self.lock:
            return dict(self.tag_to_group), set(self.pending_tags)

    def groups(self) -> list[str]:
        with self.lock:
            return sorted({value for value in self.tag_to_group.values() if str(value).strip()})

    def begin_tag(self, tag: str, generation: int | None = None) -> int | None:
        self.ensure_loaded()
        with self.lock:
            if tag in self.tag_to_group or tag in self.pending_tags:
                return None
            current_generation = self.generation if generation is None else int(generation)
            self.pending_tags.add(tag)
            return current_generation

    def assign(self, tag: str, group: str, generation: int) -> bool:
        with self.lock:
            if generation != self.generation:
                return False
            self.tag_to_group[tag] = group
            return True

    def finish_tag(self, tag: str):
        with self.lock:
            self.pending_tags.discard(tag)