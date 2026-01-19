"""
Logging Configuration and Trace Storage

Provides structured logging with trace ID support for auditability.
"""

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    json_format: bool = False,
) -> logging.Logger:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Optional directory for log files
        json_format: Use JSON format for logs (for production)

    Returns:
        Configured root logger
    """
    # Create log directory if specified
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    # Get the root logger for commander
    logger = logging.getLogger("commander")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if json_format:
        # JSON format for production/structured logging
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"}'
        )
    else:
        # Human-readable format for development
        formatter = logging.Formatter(
            "%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S",
        )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if log_dir specified)
    if log_dir:
        file_handler = logging.FileHandler(log_dir / "commander.log")
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_formatter = logging.Formatter(
            "%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.

    Args:
        name: Logger name (will be prefixed with 'commander.')

    Returns:
        Logger instance
    """
    return logging.getLogger(f"commander.{name}")


# ──────────────────────────────────────────────────────────────────────────────
# Trace ID Generation
# ──────────────────────────────────────────────────────────────────────────────


def generate_trace_id() -> str:
    """Generate a unique trace ID for request tracking."""
    return f"tr_{uuid.uuid4().hex[:12]}"


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"sess_{uuid.uuid4().hex[:8]}"


# ──────────────────────────────────────────────────────────────────────────────
# Trace Storage (for LLM interactions)
# ──────────────────────────────────────────────────────────────────────────────


class TraceStore:
    """
    Store for LLM interaction traces.

    Provides auditability for every LLM call.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir
        self.traces: list[dict[str, Any]] = []
        self._trace_file: Path | None = None

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._trace_file = log_dir / f"traces_{timestamp}.jsonl"

    def log_llm_interaction(
        self,
        trace_id: str,
        session_id: str,
        user_input: str,
        system_prompt_summary: str,
        raw_response: str,
        parsed_response: dict[str, Any] | None,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """
        Log an LLM interaction for audit.

        Args:
            trace_id: Unique trace identifier
            session_id: Session identifier
            user_input: User's input text
            system_prompt_summary: Summary/hash of system prompt (not full text)
            raw_response: Raw LLM response (truncated if too long)
            parsed_response: Parsed response dict
            duration_ms: Time taken in milliseconds
            error: Error message if any
        """
        trace = {
            "trace_id": trace_id,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_input": user_input,
            "system_prompt_summary": system_prompt_summary,
            "raw_response": raw_response[:2000] if raw_response else None,
            "parsed_type": parsed_response.get("type") if parsed_response else None,
            "duration_ms": duration_ms,
            "error": error,
        }

        self.traces.append(trace)

        # Write to file if configured
        if self._trace_file:
            with open(self._trace_file, "a") as f:
                f.write(json.dumps(trace) + "\n")

        # Keep only last 1000 traces in memory
        if len(self.traces) > 1000:
            self.traces = self.traces[-1000:]

    def get_traces(
        self,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get traces, optionally filtered by session.

        Args:
            session_id: Filter by session ID
            limit: Maximum number of traces to return

        Returns:
            List of trace dicts
        """
        traces = self.traces
        if session_id:
            traces = [t for t in traces if t.get("session_id") == session_id]
        return traces[-limit:]

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Get a specific trace by ID."""
        for trace in reversed(self.traces):
            if trace.get("trace_id") == trace_id:
                return trace
        return None


# Global trace store (initialized lazily)
_trace_store: TraceStore | None = None


def get_trace_store(log_dir: Path | None = None) -> TraceStore:
    """Get or create the global trace store."""
    global _trace_store
    if _trace_store is None:
        _trace_store = TraceStore(log_dir)
    return _trace_store
