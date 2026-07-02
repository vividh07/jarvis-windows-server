"""
Lightweight wake-word listener for Jarvis V1.

Uses RMS voice-activity detection on the PC mic, then Whisper to confirm
phrases like "hey jarvis". Custom training is V4 — this is the V1 concept.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Iterable

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK_MS = 100
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)
RMS_THRESHOLD = 0.012
SPEECH_START_CHUNKS = 4
SILENCE_END_CHUNKS = 10
MAX_UTTERANCE_SEC = 4.0
COOLDOWN_SEC = 5.0


def build_wake_phrases(agent_name: str = "Jarvis") -> list[str]:
    name = agent_name.strip().lower()
    phrases = [f"hey {name}", name]
    if name != "jarvis":
        phrases.extend(["hey jarvis", "jarvis"])
    # Longest first so "hey jarvis" wins over "jarvis"
    return sorted(set(phrases), key=len, reverse=True)


def strip_wake_prefix(text: str, phrases: Iterable[str]) -> str | None:
    """Return command after wake phrase, '' if only the wake phrase, None if no match."""
    lowered = text.lower().strip()
    if not lowered:
        return None

    for phrase in phrases:
        if lowered.startswith(phrase):
            rest = text[len(phrase):].lstrip(" ,.!-")
            return rest

        idx = lowered.find(phrase)
        if idx != -1:
            rest = text[idx + len(phrase):].lstrip(" ,.!-")
            return rest

    return None


def _chunk_rms(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(chunk))))


class WakeWordMonitor:
  """Background mic monitor that emits short utterance clips for wake-word checks."""

  def __init__(
      self,
      on_utterance: Callable[[np.ndarray], None],
      should_listen: Callable[[], bool],
      audio_busy: threading.Event,
  ):
    self._on_utterance = on_utterance
    self._should_listen = should_listen
    self._audio_busy = audio_busy
    self._thread: threading.Thread | None = None
    self._stop = threading.Event()
    self._last_trigger = 0.0

  def start(self):
    if self._thread and self._thread.is_alive():
      return
    self._stop.clear()
    self._thread = threading.Thread(target=self._run, name="jarvis-wakeword", daemon=True)
    self._thread.start()

  def stop(self):
    self._stop.set()
    if self._thread:
      self._thread.join(timeout=2)

  def _run(self):
    print("Wake-word listener started (say “Hey Jarvis”)")
    speech_chunks: list[np.ndarray] = []
    speech_active = False
    above_count = 0
    silence_count = 0

    def callback(indata, _frames, _time_info, status):
      nonlocal speech_active, above_count, silence_count
      if status:
        print(f"Wake mic status: {status}")
      if self._stop.is_set() or self._audio_busy.is_set() or not self._should_listen():
        speech_chunks.clear()
        speech_active = False
        above_count = 0
        silence_count = 0
        return

      chunk = indata[:, 0].copy()
      rms = _chunk_rms(chunk)
      if rms >= RMS_THRESHOLD:
        above_count += 1
        silence_count = 0
        if above_count >= SPEECH_START_CHUNKS:
          speech_active = True
          speech_chunks.append(chunk)
      elif speech_active:
        silence_count += 1
        speech_chunks.append(chunk)
        max_chunks = int(MAX_UTTERANCE_SEC * 1000 / CHUNK_MS)
        if silence_count >= SILENCE_END_CHUNKS or len(speech_chunks) >= max_chunks:
          self._emit_utterance(speech_chunks)
          speech_chunks.clear()
          speech_active = False
          above_count = 0
          silence_count = 0
      else:
        above_count = 0

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
        callback=callback,
    ):
      while not self._stop.is_set():
        time.sleep(0.1)

  def _emit_utterance(self, chunks: list[np.ndarray]):
    if not chunks:
      return
    now = time.time()
    if now - self._last_trigger < COOLDOWN_SEC:
      return
    if not self._should_listen() or self._audio_busy.is_set():
      return

    audio = np.concatenate(chunks)
    if audio.size < SAMPLE_RATE * 0.35:
      return

    self._last_trigger = now
    try:
      self._on_utterance(audio)
    except Exception as exc:
      print(f"Wake-word callback error: {exc}")
