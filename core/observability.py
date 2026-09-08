"""LangFuse instrumentation with local JSONL fallback when keys are absent."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from core.config import ROOT, get_settings
from core.logging import get_logger

logger = get_logger("observability")

_LOCAL_TRACE_DIR = ROOT / "runs"


class LLMTracer:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.settings = get_settings()
        self._langfuse = None
        self._handler = None
        self._local_path = _LOCAL_TRACE_DIR / run_id / "langfuse_local_traces.jsonl"
        self._local_path.parent.mkdir(parents=True, exist_ok=True)
        if self.settings.langfuse_enabled:
            self._init_langfuse()

    def _init_langfuse(self) -> None:
        try:
            from langfuse import Langfuse

            secret = (
                self.settings.langfuse_secret_key.get_secret_value()
                if self.settings.langfuse_secret_key
                else None
            )
            self._langfuse = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=secret,
                host=self.settings.langfuse_host,
            )
            try:
                from langfuse.langchain import CallbackHandler

                self._handler = CallbackHandler()
            except Exception:
                try:
                    from langfuse.callback import CallbackHandler as LegacyHandler

                    self._handler = LegacyHandler()
                except Exception as exc:  # pragma: no cover
                    logger.warning("LangFuse LangChain handler unavailable: %s", exc)
            logger.info("LangFuse tracing enabled (host=%s)", self.settings.langfuse_host)
        except Exception as exc:
            logger.warning("LangFuse SDK init failed; falling back to local traces: %s", exc)
            self._langfuse = None
            self._handler = None

    @property
    def callback(self) -> Any | None:
        return self._handler

    def langchain_config(self) -> dict[str, Any]:
        if self._handler is None:
            return {}
        return {"callbacks": [self._handler]}

    @contextmanager
    def span(
        self,
        name: str,
        *,
        prompt_id: str,
        input_payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        record: dict[str, Any] = {
            "trace_id": uuid4().hex,
            "run_id": self.run_id,
            "name": name,
            "prompt_id": prompt_id,
            "input": input_payload,
            "metadata": metadata or {},
            "output": None,
            "error": None,
            "latency_ms": None,
        }
        lf_span = None
        if self._langfuse is not None:
            try:
                lf_span = self._langfuse.start_span(
                    name=name,
                    input=input_payload,
                    metadata={"prompt_id": prompt_id, "run_id": self.run_id, **(metadata or {})},
                )
            except Exception:
                try:
                    trace = self._langfuse.trace(name=name, metadata={"run_id": self.run_id})
                    lf_span = trace.span(name=name, input=input_payload)
                except Exception as exc:
                    logger.debug("LangFuse span start failed: %s", exc)
        try:
            yield record
        except Exception as exc:
            record["error"] = str(exc)
            raise
        finally:
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self._write_local(record)
            if lf_span is not None:
                try:
                    if hasattr(lf_span, "update"):
                        lf_span.update(output=record.get("output"), metadata={"error": record.get("error")})
                    if hasattr(lf_span, "end"):
                        lf_span.end()
                except Exception as exc:
                    logger.debug("LangFuse span close failed: %s", exc)

    def flush(self) -> None:
        if self._langfuse is not None:
            try:
                self._langfuse.flush()
            except Exception as exc:
                logger.debug("LangFuse flush failed: %s", exc)

    def _write_local(self, record: dict[str, Any]) -> None:
        with self._local_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
