"""
transcriber.py — Whisper transcription pipeline for Sandman
- Transcribes audio using faster-whisper large-v3
- Supports vocabulary prompt injection for better accuracy
- Chunks long audio for crash recovery
- Disables VAD for short recordings (< 10 seconds)
- Runs at low CPU priority
- Updates meta.json with results and confidence scores
"""

import json
import logging
import math
import os
import queue
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import yaml

# ── Logging ────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / "dreamserver" / "config.yaml"


def _load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


class Transcriber:
    """
    Background transcription worker for Sandman.

    Processes a queue of entry folders, transcribing audio.* in each.
    Supports chunking for crash recovery and vocabulary prompt injection.

    Usage:
        t = Transcriber(on_complete=my_callback)
        t.start()
        t.enqueue(Path("/home/sandman/dreamserver/storage/entries/2024-03-01_06h12"))
        t.resume_pending()  # call once at startup
    """

    CHUNK_SECONDS = 60
    LOW_CONF_THRESHOLD = 0.6

    def __init__(self, on_complete=None, on_progress=None):
        self.on_complete = on_complete
        self.on_progress = on_progress
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._model = None
        self._active = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        self._thread.start()
        log.info("Transcriber started")

    def enqueue(self, entry_path: Path):
        self._queue.put(entry_path)
        log.info(f"Queued for transcription: {entry_path.name}")

    def resume_pending(self):
        """Scan entries/ for unfinished transcriptions and re-queue them."""
        config = _load_config()
        entries_dir = Path(config["storage"]["entries_dir"])
        if not entries_dir.exists():
            return
        for entry in sorted(entries_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta = _read_meta(entry)
            if meta and not meta.get("transcribed", False):
                audio = next(entry.glob("audio.*"), None)
                if audio:
                    log.info(f"Resuming pending transcription: {entry.name}")
                    self.enqueue(entry)

    @property
    def is_active(self):
        return self._active

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            config = _load_config()
            whisper_cfg = config.get("whisper", {})
            model_name = whisper_cfg.get("model", "large-v3")
            device = whisper_cfg.get("device", "cpu")
            compute_type = whisper_cfg.get("compute_type", "int8")
            log.info(f"Loading Whisper model '{model_name}'...")
            self._model = WhisperModel(
                model_name, device=device, compute_type=compute_type
            )
            log.info("Model loaded")

    def _worker(self):
        os.nice(10)
        while True:
            entry_path = self._queue.get()
            try:
                self._active = True
                self._transcribe_entry(entry_path)
            except Exception as e:
                import traceback

                log.error(f"Transcription failed for {entry_path.name}: {e}")
                log.error(traceback.format_exc())
                _update_meta(
                    entry_path,
                    {
                        "transcription_error": str(e),
                        "error_time": datetime.now().isoformat(),
                    },
                )
            finally:
                self._active = False
                self._queue.task_done()

    def _transcribe_entry(self, entry_path: Path):
        audio_file = next(entry_path.glob("audio.*"), None)
        if audio_file is None:
            log.warning(f"No audio file in {entry_path.name}, skipping")
            return

        meta = _read_meta(entry_path) or {}
        if meta.get("transcribed"):
            log.info(f"{entry_path.name} already transcribed, skipping")
            return

        log.info(f"Transcribing: {entry_path.name}")
        self._load_model()

        prompt = self._build_prompt()

        chunks_dir = entry_path / "chunks"
        chunks_dir.mkdir(exist_ok=True)
        chunk_files = _split_audio(audio_file, chunks_dir, self.CHUNK_SECONDS)
        chunks_total = len(chunk_files)

        _update_meta(
            entry_path,
            {"chunks_total": chunks_total, "chunks_done": meta.get("chunks_done", 0)},
        )

        all_segments = []
        confidence_scores = []

        for i, chunk_file in enumerate(chunk_files):
            chunk_transcript = chunk_file.with_suffix(".txt")

            if chunk_transcript.exists():
                log.info(f"  Chunk {i+1}/{chunks_total} already done, skipping")
                with open(chunk_transcript) as f:
                    all_segments.append(f.read().strip())
                continue

            log.info(f"  Transcribing chunk {i+1}/{chunks_total}...")
            text, avg_conf = self._transcribe_chunk(chunk_file, prompt)

            with open(chunk_transcript, "w") as f:
                f.write(text)

            all_segments.append(text)
            confidence_scores.append(avg_conf)

            _update_meta(entry_path, {"chunks_done": i + 1})

            if self.on_progress:
                self.on_progress(entry_path, i + 1, chunks_total)

        full_transcript = " ".join(s for s in all_segments if s)
        with open(entry_path / "transcript_raw.txt", "w") as f:
            f.write(full_transcript)

        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 1.0
        )
        is_fuzzy = avg_confidence < self.LOW_CONF_THRESHOLD

        _update_meta(
            entry_path,
            {
                "transcribed": True,
                "transcribed_at": datetime.now().isoformat(),
                "confidence": round(avg_confidence, 2),
                "fuzzy": is_fuzzy,
                "chunks_done": chunks_total,
            },
        )

        log.info(
            f"Transcription done: {entry_path.name} "
            f"({'⚠ fuzzy' if is_fuzzy else 'OK'}, conf={avg_confidence:.2f})"
        )

        if self.on_complete:
            self.on_complete(entry_path, full_transcript)
        self._model = None
        import gc

        gc.collect()
        log.info("Whisper model unloaded from memory")

    def _transcribe_chunk(self, chunk_file: Path, prompt: str):
        config = _load_config()
        whisper_cfg = config.get("whisper", {})
        language = whisper_cfg.get("language", "fr")

        # Check duration — disable VAD for short clips
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(chunk_file),
            ],
            capture_output=True,
            text=True,
        )
        duration = float(result.stdout.strip() or "0")
        use_vad = duration > 10  # only use VAD for clips longer than 10 seconds

        segments, _ = self._model.transcribe(
            str(chunk_file),
            language=language,
            task="transcribe",
            initial_prompt=prompt if prompt else None,
            vad_filter=use_vad,
            vad_parameters={"min_silence_duration_ms": 500} if use_vad else {},
        )

        texts = []
        scores = []
        for seg in segments:
            texts.append(seg.text.strip())
            if hasattr(seg, "avg_logprob"):
                score = min(1.0, max(0.0, math.exp(seg.avg_logprob)))
                scores.append(score)

        text = " ".join(t for t in texts if t)
        avg_conf = sum(scores) / len(scores) if scores else 1.0
        return text, avg_conf

    def _build_prompt(self):
        """Load vocabulary file and build Whisper initial prompt."""
        config = _load_config()
        vocab_file = Path(config.get("vocabulary_file", ""))
        if not vocab_file.exists():
            return ""
        words = vocab_file.read_text().strip()
        if not words:
            return ""
        return f"Journal de rêves en français. Noms et mots importants: {words}."


# ── Audio chunking ─────────────────────────────────────────────────────────────


def _split_audio(audio_file: Path, output_dir: Path, chunk_seconds: int):
    # First convert to WAV if needed
    wav_file = output_dir / "converted.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_file),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-loglevel",
            "error",
            str(wav_file),
        ],
        check=True,
    )

    pattern = str(output_dir / "chunk_%03d.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_file),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-c",
        "copy",
        "-loglevel",
        "error",
        pattern,
    ]
    subprocess.run(cmd, check=True)
    return sorted(output_dir.glob("chunk_*.wav"))


# ── meta.json helpers ──────────────────────────────────────────────────────────


def _read_meta(entry_path: Path):
    meta_file = entry_path / "meta.json"
    if not meta_file.exists():
        return None
    with open(meta_file) as f:
        return json.load(f)


def _update_meta(entry_path: Path, updates: dict):
    meta_file = entry_path / "meta.json"
    meta = _read_meta(entry_path) or {}
    meta.update(updates)
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [transcriber] %(message)s"
    )

    def on_complete(path, text):
        print(f"\n✓ Transcript:\n{text}\n")

    def on_progress(path, done, total):
        print(f"  Progress: {done}/{total} chunks")

    t = Transcriber(on_complete=on_complete, on_progress=on_progress)
    t.start()
    t.resume_pending()

    t._queue.join()
    print("Done.")
