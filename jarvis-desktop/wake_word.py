"""Detecção offline de wake word 'jarvis' via Vosk (PT-BR).

O modelo small de PT-BR não tem "jarvis" no vocabulário; ao ouvir "Jarvis",
transcreve as palavras reais mais próximas (homófonos). A grammar e a lista de
gatilhos cobrem os homófonos confirmados na prática.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import unicodedata
from pathlib import Path
from typing import Callable

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from audio_utils import TARGET_RATE, block_to_vosk_bytes, negotiate_input

logger = logging.getLogger("jarvis.desktop.wake_word")

_BLOCK_MS = 250   # janela de 250ms por bloco para o Vosk

# Palavras que o Vosk produz ao ouvir "Jarvis" com o modelo small PT-BR.
# A grammar restringe o vocabulário do Vosk a estas formas + [unk].
_GRAMMAR_WORDS = [
    "jarvis",
    "chaves",
    "já vez",
    "já vês",
    "já pense",
    "aves",
    "de aves",
]

# Gatilhos normalizados (sem acento, minúsculas) que causam o disparo de on_wake().
# "chaves" e "aves" são palavras comuns e podem gerar falso-positivo ocasional;
# use WAKE_WORDS no voice.env para enxugar a lista se isso incomodar em produção.
_DEFAULT_TRIGGERS = ["jarvis", "chaves", "ja vez", "ja ves", "ja pense", "aves"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Minúsculas + remove acentos (NFD → ASCII)."""
    nfd = unicodedata.normalize("NFD", text.lower())
    return nfd.encode("ascii", "ignore").decode()


def _build_grammar(words: list[str]) -> str:
    return json.dumps(words + ["[unk]"], ensure_ascii=False)


def _load_wake_config() -> tuple[str, list[str], bool]:
    """Retorna (grammar_json, triggers_normalizados, wake_debug).

    WAKE_WORDS: lista separada por vírgula com as formas naturais das palavras de
        ativação; substitui os defaults quando preenchida.
    WAKE_DEBUG: se "true", loga em INFO tudo que o Vosk reconhece durante a escuta
        — útil para descobrir novos homófonos a adicionar na lista.
    """
    raw = os.getenv("WAKE_WORDS", "").strip()
    if raw:
        grammar_words = [w.strip() for w in raw.split(",") if w.strip()]
    else:
        grammar_words = list(_GRAMMAR_WORDS)

    triggers = [_normalize(w) for w in grammar_words]
    grammar  = _build_grammar(grammar_words)
    debug    = os.getenv("WAKE_DEBUG", "").lower() in ("true", "1", "yes")
    return grammar, triggers, debug


def _matches(text: str, triggers: list[str]) -> bool:
    norm = _normalize(text)
    return any(t in norm for t in triggers)


# ── Detector ──────────────────────────────────────────────────────────────────

class WakeWordDetector:
    """Escuta continuamente o microfone e dispara callback ao ouvir 'jarvis'.

    O modelo Vosk small de PT-BR transcreve "Jarvis" como homófonos reais
    ("chaves", "já vez", "aves", …). A detecção baseia-se nesses homófonos.
    pause()/resume() cedem o microfone ao Listener sem fechar o stream.
    """

    def __init__(
        self,
        model_path: str = "models/vosk-model-small-pt-0.3",
        device: int | None = None,
        on_wake: Callable[[], None] | None = None,
    ) -> None:
        self._model_path = model_path
        self._device     = device
        self._on_wake    = on_wake
        self._running    = False
        self._active     = threading.Event()
        self._active.set()   # set = ativo; clear = pausado
        self._thread: threading.Thread | None = None
        self._model:  Model | None = None

        self._grammar, self._triggers, self._wake_debug = _load_wake_config()
        logger.info(
            "Gatilhos de wake word: %s%s",
            self._triggers,
            " [WAKE_DEBUG ativo — logs em INFO]" if self._wake_debug else "",
        )

    def register_on_wake(self, callback: Callable[[], None]) -> None:
        self._on_wake = callback

    def start(self) -> None:
        """Carrega modelo Vosk e inicia thread de escuta."""
        p = Path(self._model_path)
        model_abs = p if p.is_absolute() else Path(__file__).parent / p
        if not model_abs.is_dir():
            msg = (
                f"Modelo Vosk não encontrado em '{model_abs}'.\n"
                "Baixe vosk-model-small-pt-0.3 em https://alphacephei.com/vosk/models\n"
                "e descompacte em jarvis-desktop/models/vosk-model-small-pt-0.3/."
            )
            logger.error(msg)
            raise FileNotFoundError(msg)

        SetLogLevel(-1)
        logger.info("Carregando modelo Vosk de '%s'...", model_abs)
        self._model = Model(str(model_abs))
        logger.info(
            "WakeWordDetector pronto — escutando por 'jarvis' (via homófonos PT)."
        )

        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="wake-word"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._active.set()   # desbloqueia caso esteja pausado

    def pause(self) -> None:
        """Pausa o processamento (stream permanece aberto, buffers drenados)."""
        self._active.clear()

    def resume(self) -> None:
        """Retoma o processamento após pause()."""
        self._active.set()

    # ── Loop principal ────────────────────────────────────────────────────────

    def _run(self) -> None:
        params = negotiate_input(self._device, block_ms=_BLOCK_MS)
        if params is None:
            logger.warning(
                "WakeWordDetector: microfone indisponível — thread encerrando."
            )
            return
        native_rate, channels, block_size = params

        def _new_rec() -> KaldiRecognizer:
            return KaldiRecognizer(self._model, TARGET_RATE, self._grammar)

        rec = _new_rec()
        try:
            with sd.InputStream(
                samplerate=native_rate,
                channels=channels,
                dtype="float32",
                blocksize=block_size,
                device=self._device,
            ) as stream:
                while self._running:
                    block, _ = stream.read(block_size)

                    if not self._active.is_set():
                        self._active.wait()
                        rec = _new_rec()   # descarta estado acumulado durante a pausa
                        continue

                    vosk_bytes = block_to_vosk_bytes(block, native_rate)
                    if rec.AcceptWaveform(vosk_bytes):
                        text     = json.loads(rec.Result()).get("text", "")
                        is_final = True
                    else:
                        text     = json.loads(rec.PartialResult()).get("partial", "")
                        is_final = False

                    if not text:
                        continue

                    # Diagnóstico: ver o que o Vosk ouve em tempo real.
                    # Com WAKE_DEBUG=true sobe para INFO (visível no console normal).
                    log_fn = logger.info if self._wake_debug else logger.debug
                    log_fn(
                        "Vosk [%s]: %r", "final" if is_final else "parcial", text
                    )

                    if _matches(text, self._triggers):
                        matched = next(
                            t for t in self._triggers if t in _normalize(text)
                        )
                        logger.info(
                            "Wake word detectada (gatilho=%r em %r).", matched, text
                        )
                        rec = _new_rec()   # reinicia reconhecedor → evita re-disparo
                        if self._on_wake and self._running:
                            threading.Thread(
                                target=self._on_wake, daemon=True, name="wake-cb"
                            ).start()
        except Exception:
            logger.exception("Erro no loop do WakeWordDetector")
