"""Realtime microphone transcription backed by local Nemotron Streaming ASR."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from src.config import (
    AUDIO_Q_MAX,
    BLOCK_SAMPLES,
    CHANNELS,
    LOGS_DIR,
    MIN_CHARS_TO_PRINT,
    NEMO_DEVICE,
    NEMO_ENDPOINTING_MS,
    NEMO_HOTWORD_BOOST,
    NEMO_LANGUAGE,
    NEMO_MAX_HOTWORDS,
    NEMO_MODEL_PATH,
    NEMO_REALTIME_URL,
    NEMO_RUNTIME_EXE,
    NEMO_SERVER_HOST,
    NEMO_SERVER_PORT,
    NEMO_SERVER_URL,
    NEMO_STARTUP_TIMEOUT_S,
    OUT_TXT,
    SR,
)
from src.services.nemo_streaming import (
    NemoRealtimeSession,
    NemoSpeechServer,
    extract_hotword_phrases,
)


@dataclass
class CaptionOutput:
    type: str
    text: str
    timestamp: str
    no_speech_prob: Optional[float] = None
    avg_logprob: Optional[float] = None


def safe_put_drop_oldest(target: queue.Queue, item) -> None:
    try:
        target.put_nowait(item)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        try:
            target.put_nowait(item)
        except queue.Full:
            pass


def setup_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = False
    os.makedirs(LOGS_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(
        os.path.join(LOGS_DIR, filename), encoding="utf-8", mode="a"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


class AudioTranscriptionService:
    """Keep the legacy UI contract while using one native streaming ASR model."""

    def __init__(self) -> None:
        self.audio_q: queue.Queue[bytes] = queue.Queue(maxsize=AUDIO_Q_MAX)
        self.partial_output_q: queue.Queue[CaptionOutput] = queue.Queue(maxsize=100)
        self.accurate_output_q: queue.Queue[CaptionOutput] = queue.Queue(maxsize=100)

        self.stop_event = threading.Event()
        self.restart_session_event = threading.Event()
        self.session_ready_event = threading.Event()
        self.is_running = False
        self.transcriber_thread: Optional[threading.Thread] = None
        self.audio_stream = None

        self.partial_callback: Optional[Callable[[CaptionOutput], None]] = None
        self.accurate_callback: Optional[Callable[[CaptionOutput], None]] = None

        self.logger = setup_logger("AudioService", "audio_service.log")
        self.transcriber_logger = setup_logger("Transcriber", "transcriber.log")
        self._hotword_lock = threading.Lock()
        self._hotwords: list[str] = []
        self._last_error: Optional[str] = None
        self._asr_ready = False

        self.server = NemoSpeechServer(
            executable=NEMO_RUNTIME_EXE,
            model_path=NEMO_MODEL_PATH,
            server_url=NEMO_SERVER_URL,
            host=NEMO_SERVER_HOST,
            port=NEMO_SERVER_PORT,
            device=NEMO_DEVICE,
            endpointing_ms=NEMO_ENDPOINTING_MS,
            startup_timeout_s=NEMO_STARTUP_TIMEOUT_S,
            log=self.logger.info,
        )

    @property
    def asr_ready(self) -> bool:
        return self._asr_ready

    @property
    def model_path(self) -> str:
        return NEMO_MODEL_PATH

    @property
    def hotword_count(self) -> int:
        with self._hotword_lock:
            return len(self._hotwords)

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def initialize(self) -> None:
        self.logger.info("Starting local Nemotron ASR engine...")
        self.server.start()
        self._asr_ready = True
        self.logger.info("Nemotron ASR initialized: %s", NEMO_MODEL_PATH)

    def shutdown(self) -> None:
        self.stop_capture()
        self.server.stop()
        self._asr_ready = False

    def set_partial_callback(self, callback: Callable[[CaptionOutput], None]) -> None:
        self.partial_callback = callback

    def set_accurate_callback(self, callback: Callable[[CaptionOutput], None]) -> None:
        self.accurate_callback = callback

    def set_prof_words(self, prof_words: str) -> None:
        phrases = extract_hotword_phrases(prof_words, NEMO_MAX_HOTWORDS)
        with self._hotword_lock:
            self._hotwords = phrases
        self.logger.info(
            "Speech-context hotwords updated: %d phrases, boost %.1f",
            len(phrases),
            NEMO_HOTWORD_BOOST,
        )
        if self.is_running:
            # Session settings are immutable after audio starts. Commit the old
            # stream and reopen it while microphone blocks remain queued.
            self.restart_session_event.set()

    def _hotword_snapshot(self) -> list[str]:
        with self._hotword_lock:
            return list(self._hotwords)

    @staticmethod
    def _clear_queue(target: queue.Queue) -> None:
        while True:
            try:
                target.get_nowait()
            except queue.Empty:
                return

    def start_capture(self) -> None:
        if self.is_running:
            return
        if not self._asr_ready:
            raise RuntimeError("Nemotron ASR is not initialized")

        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Missing sounddevice. Install dependencies with pip install -r requirements.txt"
            ) from exc

        self._clear_queue(self.audio_q)
        self._clear_queue(self.partial_output_q)
        self._clear_queue(self.accurate_output_q)
        self.stop_event.clear()
        self.restart_session_event.clear()
        self.session_ready_event.clear()
        self._last_error = None

        self.transcriber_thread = threading.Thread(
            target=self._transcriber, name="nemotron-realtime", daemon=True
        )
        self.transcriber_thread.start()
        if not self.session_ready_event.wait(timeout=15):
            self.stop_event.set()
            raise TimeoutError("Timed out opening the Nemotron realtime session")
        if self._last_error:
            raise RuntimeError(self._last_error)

        def audio_callback(indata, frames, time_info, status) -> None:
            del time_info
            if status:
                self.logger.warning("Microphone status: %s", status)
            if frames <= 0 or self.stop_event.is_set():
                return
            pcm16 = np.ascontiguousarray(indata[:, 0], dtype=np.int16).tobytes()
            safe_put_drop_oldest(self.audio_q, pcm16)

        try:
            self.audio_stream = sd.InputStream(
                samplerate=SR,
                channels=CHANNELS,
                dtype="int16",
                blocksize=BLOCK_SAMPLES,
                callback=audio_callback,
            )
            self.audio_stream.start()
        except Exception:
            self.stop_event.set()
            if self.transcriber_thread:
                self.transcriber_thread.join(timeout=5)
            raise

        self.is_running = True
        self.logger.info("Microphone capture and realtime transcription started")

    def stop_capture(self) -> None:
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            finally:
                self.audio_stream = None

        if not self.is_running and not (
            self.transcriber_thread and self.transcriber_thread.is_alive()
        ):
            return

        self.stop_event.set()
        if self.transcriber_thread:
            self.transcriber_thread.join(timeout=20)
            if self.transcriber_thread.is_alive():
                self.logger.warning("Realtime transcription thread did not stop in time")
        self.transcriber_thread = None
        self.is_running = False
        self.logger.info("Microphone capture and realtime transcription stopped")

    def get_partial_caption(self, block=True, timeout=None) -> CaptionOutput:
        return self.partial_output_q.get(block=block, timeout=timeout)

    def get_accurate_caption(self, block=True, timeout=None) -> CaptionOutput:
        return self.accurate_output_q.get(block=block, timeout=timeout)

    def _new_session(self) -> NemoRealtimeSession:
        session = NemoRealtimeSession(
            url=NEMO_REALTIME_URL,
            sample_rate=SR,
            language=NEMO_LANGUAGE,
            endpointing_ms=NEMO_ENDPOINTING_MS,
            hotwords=self._hotword_snapshot(),
            hotword_boost=NEMO_HOTWORD_BOOST,
        )
        session.open()
        self.transcriber_logger.info(
            "Realtime session opened (language=%s, hotwords=%d)",
            NEMO_LANGUAGE,
            self.hotword_count,
        )
        return session

    def _emit_partial(self, text: str) -> None:
        caption = CaptionOutput(
            type="partial", text=text, timestamp=time.strftime("%H:%M:%S")
        )
        safe_put_drop_oldest(self.partial_output_q, caption)
        if self.partial_callback:
            try:
                self.partial_callback(caption)
            except Exception:
                self.transcriber_logger.exception("Partial caption callback failed")

    def _emit_accurate(self, text: str) -> None:
        cleaned = text.strip()
        if len(cleaned) < MIN_CHARS_TO_PRINT:
            return
        now = time.strftime("%H:%M:%S")
        caption = CaptionOutput(type="accurate", text=cleaned, timestamp=now)
        safe_put_drop_oldest(self.accurate_output_q, caption)
        if self.accurate_callback:
            try:
                self.accurate_callback(caption)
            except Exception:
                self.transcriber_logger.exception("Accurate caption callback failed")

        os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
        with open(OUT_TXT, "a", encoding="utf-8") as output:
            output.write(f"[{now}] {cleaned}\n")
        self.transcriber_logger.info("Final text: %s", cleaned)

    def _handle_event(self, event: dict, partial_text: str) -> str:
        event_type = event.get("type")
        if event_type == NemoRealtimeSession.DELTA_EVENT:
            delta = event.get("delta", "")
            if delta:
                partial_text += delta
                self._emit_partial(partial_text.strip())
        elif event_type == NemoRealtimeSession.COMPLETED_EVENT:
            self._emit_accurate(str(event.get("transcript", "")))
            partial_text = ""
            self._emit_partial("")
        elif event_type == "error":
            raise RuntimeError(f"NeMo realtime error: {event}")
        return partial_text

    def _drain_available(self, session: NemoRealtimeSession, partial_text: str) -> str:
        while True:
            try:
                event = session.receive(timeout=0)
            except TimeoutError:
                return partial_text
            partial_text = self._handle_event(event, partial_text)

    def _commit_and_drain(
        self, session: NemoRealtimeSession, partial_text: str, timeout_s: float = 20
    ) -> str:
        session.commit()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                event = session.receive(timeout=1)
            except TimeoutError:
                continue
            partial_text = self._handle_event(event, partial_text)
            if event.get("type") == "input_audio_buffer.committed":
                return partial_text
        raise TimeoutError("Timed out committing the Nemotron audio buffer")

    def _transcriber(self) -> None:
        session: Optional[NemoRealtimeSession] = None
        partial_text = ""
        try:
            session = self._new_session()
            self.session_ready_event.set()

            while True:
                if self.restart_session_event.is_set():
                    self.restart_session_event.clear()
                    partial_text = self._commit_and_drain(session, partial_text)
                    session.close()
                    session = self._new_session()
                    partial_text = ""

                if self.stop_event.is_set() and self.audio_q.empty():
                    break

                try:
                    pcm16 = self.audio_q.get(timeout=0.03)
                except queue.Empty:
                    partial_text = self._drain_available(session, partial_text)
                    continue

                session.send_audio(pcm16)
                partial_text = self._drain_available(session, partial_text)

            self._commit_and_drain(session, partial_text)
        except Exception as exc:
            self._last_error = f"Realtime transcription failed: {exc}"
            self.transcriber_logger.exception(self._last_error)
            self.session_ready_event.set()
        finally:
            if session:
                session.close()
