"""Local NeMo-Speech.cpp process and realtime protocol helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Callable, Iterable, Optional

from websockets.sync.client import ClientConnection, connect


def extract_hotword_phrases(text: str, max_phrases: int = 100) -> list[str]:
    """Extract concise decoder phrases from the LLM's course-topic response."""
    if not text or not text.strip():
        return []

    body = text.strip()
    marker = re.search(r"key\s+technical\s+terms\s+include\s*:\s*", body, re.I)
    if marker:
        body = body[marker.end() :]

    body = re.split(
        r"all\s+technical\s+terms\s+should\s+be\s+transcribed",
        body,
        maxsplit=1,
        flags=re.I,
    )[0]

    phrases: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,;\n]+", body):
        phrase = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", item).strip()
        phrase = phrase.strip(" \t\r\n.:")
        if not phrase or len(phrase) > 100:
            continue
        lowered = phrase.casefold()
        if lowered.startswith("this lecture discusses") or lowered in seen:
            continue
        seen.add(lowered)
        phrases.append(phrase)
        if len(phrases) >= max_phrases:
            break
    return phrases


class NemoSpeechServer:
    """Own a local ``nemo-speech serve`` subprocess when one isn't running."""

    def __init__(
        self,
        *,
        executable: str,
        model_path: str,
        server_url: str,
        host: str,
        port: int,
        device: str,
        endpointing_ms: int,
        startup_timeout_s: float,
        log: Callable[[str], None],
    ) -> None:
        self.executable = os.path.abspath(executable)
        self.model_path = os.path.abspath(model_path)
        self.server_url = server_url.rstrip("/")
        self.host = host
        self.port = port
        self.device = device
        self.endpointing_ms = endpointing_ms
        self.startup_timeout_s = startup_timeout_s
        self.log = log
        self.process: Optional[subprocess.Popen[str]] = None
        self._owns_process = False
        self._output_tail: deque[str] = deque(maxlen=80)
        self._reader_thread: Optional[threading.Thread] = None

    @property
    def owns_process(self) -> bool:
        return self._owns_process

    def _ready(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.server_url}/ready", timeout=1.0) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _loaded_model_matches(self) -> bool:
        expected = os.path.splitext(os.path.basename(self.model_path))[0]
        try:
            with urllib.request.urlopen(f"{self.server_url}/v1/models", timeout=2.0) as response:
                payload = json.load(response)
        except (OSError, ValueError, urllib.error.URLError):
            return False
        return any(
            item.get("capability") == "transcription" and item.get("id") == expected
            for item in payload.get("data", [])
        )

    def start(self) -> None:
        if not os.path.isfile(self.executable):
            raise FileNotFoundError(f"NeMo-Speech runtime not found: {self.executable}")
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"Nemotron model not found: {self.model_path}")

        if self._ready():
            if not self._loaded_model_matches():
                raise RuntimeError(
                    f"Port {self.port} already has a different NeMo-Speech model loaded"
                )
            self.log(f"Reusing NeMo-Speech server at {self.server_url}")
            self._owns_process = False
            return

        command = [
            self.executable, "serve",
            "--host", self.host,
            "--port", str(self.port),
            "--threads", "2",
            "--no-ui",
            "--asr-model", self.model_path,
            "--device", self.device,
            # 6 个右上下文帧（约 560ms）在准确率和实时延迟之间更适合课堂转录。
            "--asr.streaming.rnnt_right_context", "6",
            "--asr.endpointing.enable=true",
            "--asr.endpointing.stop_history_eou_ms", str(self.endpointing_ms),
            "--asr.batching.enabled=false",
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            command,
            cwd=os.path.dirname(self.executable),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )
        self._owns_process = True
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()

        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if self._ready():
                self.log(f"NeMo-Speech server ready at {self.server_url}")
                return
            if self.process.poll() is not None:
                detail = "\n".join(self._output_tail)
                raise RuntimeError(
                    f"NeMo-Speech server exited with code {self.process.returncode}.\n{detail}"
                )
            time.sleep(0.25)

        self.stop()
        raise TimeoutError(
            f"NeMo-Speech server was not ready after {self.startup_timeout_s:.0f}s"
        )

    def _read_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in iter(self.process.stdout.readline, ""):
            clean = line.rstrip()
            if clean:
                self._output_tail.append(clean)
                self.log(f"[NeMo] {clean}")

    def stop(self) -> None:
        process = self.process
        if not process or not self._owns_process:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self.process = None
        self._owns_process = False
        self.log("NeMo-Speech server stopped")


class NemoRealtimeSession:
    """One realtime PCM16 recognition session."""

    DELTA_EVENT = "conversation.item.input_audio_transcription.delta"
    COMPLETED_EVENT = "conversation.item.input_audio_transcription.completed"

    def __init__(
        self,
        *,
        url: str,
        sample_rate: int,
        language: str,
        endpointing_ms: int,
        hotwords: Iterable[str],
        hotword_boost: float,
    ) -> None:
        self.url = url
        self.sample_rate = sample_rate
        self.language = language
        self.endpointing_ms = endpointing_ms
        self.hotwords = list(hotwords)
        self.hotword_boost = hotword_boost
        self.socket: Optional[ClientConnection] = None

    def open(self) -> None:
        self.socket = connect(self.url, open_timeout=10, close_timeout=3)
        created = self.receive(timeout=10)
        if created.get("type") != "session.created":
            raise RuntimeError(f"Unexpected NeMo session event: {created}")

        settings: dict[str, object] = {
            "sample_rate": self.sample_rate,
            "language": self.language,
            "automatic_punctuation": True,
            "endpointing_ms": self.endpointing_ms,
        }
        if self.hotwords:
            settings["speech_contexts"] = [
                {"phrases": self.hotwords, "boost": self.hotword_boost}
            ]
        self.socket.send(json.dumps({"type": "session.update", "session": settings}))
        updated = self.receive(timeout=10)
        if updated.get("type") == "error":
            raise RuntimeError(f"NeMo rejected session settings: {updated}")
        if updated.get("type") != "session.updated":
            raise RuntimeError(f"Unexpected NeMo settings event: {updated}")

    def send_audio(self, pcm16: bytes) -> None:
        if not self.socket:
            raise RuntimeError("NeMo realtime session is not open")
        self.socket.send(pcm16)

    def receive(self, timeout: Optional[float] = None) -> dict:
        if not self.socket:
            raise RuntimeError("NeMo realtime session is not open")
        message = self.socket.recv(timeout=timeout)
        if isinstance(message, bytes):
            raise RuntimeError("Unexpected binary response from NeMo realtime server")
        return json.loads(message)

    def commit(self) -> None:
        if self.socket:
            self.socket.send(json.dumps({"type": "input_audio_buffer.commit"}))

    def close(self) -> None:
        if self.socket:
            self.socket.close()
            self.socket = None
