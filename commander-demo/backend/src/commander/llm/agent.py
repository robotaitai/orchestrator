"""
Commander Agent

Converts natural language to validated playbook commands using Gemini.
Maintains conversation context and enforces strict output schema.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from commander.core.models import FleetState
from commander.llm.gemini_client import GeminiClient, GeminiClientError, get_client
from commander.llm.prompts import build_system_prompt, format_fleet_state

logger = logging.getLogger("commander.llm.agent")


# ──────────────────────────────────────────────────────────────────────────────
# Output Schemas
# ──────────────────────────────────────────────────────────────────────────────


class ResponseType(str, Enum):
    """Type of agent response."""

    COMMANDS = "commands"
    CLARIFICATION = "clarification"
    RESPONSE = "response"
    ERROR = "error"


class CommandEnvelope(BaseModel):
    """A single command from the agent."""

    command: str
    target: str
    params: dict[str, Any] = Field(default_factory=dict)


class AgentCommandsResponse(BaseModel):
    """Agent response with commands to execute."""

    type: ResponseType = ResponseType.COMMANDS
    commands: list[CommandEnvelope]
    explanation: str = ""


class AgentClarificationResponse(BaseModel):
    """Agent response requesting clarification."""

    type: ResponseType = ResponseType.CLARIFICATION
    question: str
    options: list[str] = Field(default_factory=list)


class AgentInfoResponse(BaseModel):
    """Agent informational response."""

    type: ResponseType = ResponseType.RESPONSE
    message: str


class AgentErrorResponse(BaseModel):
    """Agent error response."""

    type: ResponseType = ResponseType.ERROR
    error: str
    details: str = ""


# Union type for all responses
AgentResponse = (
    AgentCommandsResponse
    | AgentClarificationResponse
    | AgentInfoResponse
    | AgentErrorResponse
)


# ──────────────────────────────────────────────────────────────────────────────
# Conversation Memory
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str = ""


@dataclass
class ConversationMemory:
    """Maintains conversation context for the agent."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    turns: list[ConversationTurn] = field(default_factory=list)
    max_turns: int = 20  # Keep last N turns for context

    def add_user_message(self, content: str, trace_id: str = "") -> None:
        """Add a user message to the conversation."""
        self.turns.append(
            ConversationTurn(role="user", content=content, trace_id=trace_id)
        )
        self._trim()

    def add_assistant_message(self, content: str, trace_id: str = "") -> None:
        """Add an assistant message to the conversation."""
        self.turns.append(
            ConversationTurn(role="assistant", content=content, trace_id=trace_id)
        )
        self._trim()

    def get_messages(self) -> list[dict[str, str]]:
        """Get messages in Gemini format."""
        return [
            {"role": "user" if t.role == "user" else "model", "content": t.content}
            for t in self.turns
        ]

    def clear(self) -> None:
        """Clear conversation history."""
        self.turns.clear()

    def _trim(self) -> None:
        """Trim to max_turns."""
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]


# ──────────────────────────────────────────────────────────────────────────────
# Trace Logging
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class AgentTrace:
    """Trace record for an agent interaction."""

    trace_id: str
    session_id: str
    timestamp: datetime
    user_input: str
    system_prompt_hash: str  # Don't log full prompt (may contain sensitive info)
    raw_response: str
    parsed_response: AgentResponse | None
    parse_error: str | None
    duration_ms: float


# ──────────────────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────────────────


# Valid playbook commands (from PRD 7.2)
VALID_COMMANDS = {
    "go_to",
    "return_home",
    "hold_position",
    "patrol",
    "form_formation",
    "follow_leader",
    "orbit",
    "spotlight",
    "point_laser",
    "report_status",
    "stop",
}


class CommanderAgent:
    """
    LLM-powered agent for converting natural language to playbook commands.

    Features:
    - Strict JSON output schema
    - Conversation memory
    - Command validation against playbook
    - Trace logging for auditability
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        fleet_state: FleetState | None = None,
    ) -> None:
        """
        Initialize the Commander agent.

        Args:
            client: Gemini client (uses singleton if not provided)
            fleet_state: Current fleet state for context
        """
        self.client = client or get_client()
        self.fleet_state = fleet_state or FleetState()
        self.memory = ConversationMemory()
        self.traces: list[AgentTrace] = []

    def set_fleet_state(self, state: FleetState) -> None:
        """Update the fleet state context."""
        self.fleet_state = state

    async def process_message(self, user_input: str) -> AgentResponse:
        """
        Process a user message and return structured response.

        Args:
            user_input: Natural language input from user

        Returns:
            Structured AgentResponse (commands, clarification, or error)
        """
        import hashlib
        import time

        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        start_time = time.time()

        logger.info(f"[{trace_id}] Processing: {user_input[:100]}...")

        # Build system prompt with current state
        fleet_str = format_fleet_state(self.fleet_state.platforms)
        system_prompt = build_system_prompt(fleet_state_str=fleet_str)
        prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]

        # Add user message to memory
        self.memory.add_user_message(user_input, trace_id)

        # Call Gemini
        raw_response = ""
        try:
            if len(self.memory.turns) > 1:
                # Multi-turn conversation
                response_dict = await self.client.chat(
                    messages=self.memory.get_messages(),
                    system_instruction=system_prompt,
                )
            else:
                # Single turn
                response_dict = await self.client.generate_json(
                    prompt=user_input,
                    system_instruction=system_prompt,
                )

            raw_response = str(response_dict)
            parsed = self._parse_response(response_dict)

            # Validate commands if present
            if isinstance(parsed, AgentCommandsResponse):
                parsed = self._validate_commands(parsed)

            # Add to memory
            self.memory.add_assistant_message(raw_response, trace_id)

            # Log trace
            duration_ms = (time.time() - start_time) * 1000
            self._log_trace(
                trace_id=trace_id,
                user_input=user_input,
                prompt_hash=prompt_hash,
                raw_response=raw_response,
                parsed=parsed,
                duration_ms=duration_ms,
            )

            logger.info(f"[{trace_id}] Response type: {parsed.type.value}")
            return parsed

        except GeminiClientError as e:
            logger.error(f"[{trace_id}] Gemini error: {e}")
            return AgentErrorResponse(
                error="LLM service error",
                details=str(e),
            )
        except Exception as e:
            logger.exception(f"[{trace_id}] Unexpected error: {e}")
            return AgentErrorResponse(
                error="Processing error",
                details=str(e),
            )

    def _parse_response(self, response_dict: dict[str, Any]) -> AgentResponse:
        """Parse and validate the LLM response."""
        response_type = response_dict.get("type", "")

        try:
            if response_type == "commands":
                return AgentCommandsResponse(**response_dict)
            elif response_type == "clarification":
                return AgentClarificationResponse(**response_dict)
            elif response_type == "response":
                return AgentInfoResponse(**response_dict)
            else:
                # Try to infer type
                if "commands" in response_dict:
                    response_dict["type"] = "commands"
                    return AgentCommandsResponse(**response_dict)
                elif "question" in response_dict:
                    response_dict["type"] = "clarification"
                    return AgentClarificationResponse(**response_dict)
                else:
                    return AgentErrorResponse(
                        error="Unknown response type",
                        details=f"Got type: {response_type}",
                    )
        except ValidationError as e:
            logger.error(f"Response validation error: {e}")
            return AgentErrorResponse(
                error="Invalid response format",
                details=str(e),
            )

    def _validate_commands(
        self, response: AgentCommandsResponse
    ) -> AgentResponse:
        """Validate that commands are in the playbook."""
        invalid_commands = []

        for cmd in response.commands:
            if cmd.command not in VALID_COMMANDS:
                invalid_commands.append(cmd.command)

        if invalid_commands:
            logger.warning(f"Invalid commands detected: {invalid_commands}")
            return AgentErrorResponse(
                error="Invalid commands",
                details=f"Commands not in playbook: {', '.join(invalid_commands)}. "
                f"Valid commands: {', '.join(sorted(VALID_COMMANDS))}",
            )

        return response

    def _log_trace(
        self,
        trace_id: str,
        user_input: str,
        prompt_hash: str,
        raw_response: str,
        parsed: AgentResponse,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """Log a trace record for auditability."""
        trace = AgentTrace(
            trace_id=trace_id,
            session_id=self.memory.session_id,
            timestamp=datetime.now(timezone.utc),
            user_input=user_input,
            system_prompt_hash=prompt_hash,
            raw_response=raw_response[:1000],  # Truncate
            parsed_response=parsed,
            parse_error=error,
            duration_ms=duration_ms,
        )
        self.traces.append(trace)

        # Keep last 100 traces
        if len(self.traces) > 100:
            self.traces = self.traces[-100:]

        # Log to structured logger
        logger.info(
            f"[{trace_id}] Trace: session={self.memory.session_id}, "
            f"type={parsed.type.value if parsed else 'error'}, "
            f"duration={duration_ms:.1f}ms"
        )

    def reset_conversation(self) -> None:
        """Reset conversation memory (start fresh)."""
        self.memory.clear()
        logger.info(f"Conversation reset for session {self.memory.session_id}")

    def get_traces(self, limit: int = 10) -> list[AgentTrace]:
        """Get recent traces for debugging/audit."""
        return self.traces[-limit:]


# ──────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ──────────────────────────────────────────────────────────────────────────────


async def process_user_message(
    message: str,
    fleet_state: FleetState | None = None,
) -> AgentResponse:
    """
    Convenience function to process a single message.

    For stateless use (no conversation memory between calls).
    """
    agent = CommanderAgent(fleet_state=fleet_state)
    return await agent.process_message(message)
