"""Tests for the Commander Agent."""

import pytest

from commander.llm.agent import (
    AgentClarificationResponse,
    AgentCommandsResponse,
    AgentErrorResponse,
    CommanderAgent,
    CommandEnvelope,
    ConversationMemory,
    ResponseType,
    VALID_COMMANDS,
)
from commander.core.models import FleetState, Platform, PlatformType, Position


# ──────────────────────────────────────────────────────────────────────────────
# Conversation Memory Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestConversationMemory:
    """Tests for conversation memory."""

    def test_add_messages(self):
        """Test adding messages to memory."""
        memory = ConversationMemory()

        memory.add_user_message("Hello")
        memory.add_assistant_message("Hi there")

        assert len(memory.turns) == 2
        assert memory.turns[0].role == "user"
        assert memory.turns[1].role == "assistant"

    def test_get_messages_format(self):
        """Test message format for Gemini."""
        memory = ConversationMemory()
        memory.add_user_message("Hello")
        memory.add_assistant_message("Hi")

        messages = memory.get_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "model"  # Gemini format
        assert messages[1]["content"] == "Hi"

    def test_trim_old_messages(self):
        """Test that old messages are trimmed."""
        memory = ConversationMemory(max_turns=5)

        for i in range(10):
            memory.add_user_message(f"Message {i}")

        assert len(memory.turns) == 5
        assert memory.turns[0].content == "Message 5"

    def test_clear(self):
        """Test clearing memory."""
        memory = ConversationMemory()
        memory.add_user_message("Hello")
        memory.clear()

        assert len(memory.turns) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Response Parsing Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestResponseParsing:
    """Tests for response parsing."""

    def test_parse_commands_response(self):
        """Test parsing a commands response."""
        agent = CommanderAgent()

        response_dict = {
            "type": "commands",
            "commands": [
                {"command": "go_to", "target": "ugv1", "params": {"x": 10, "y": 20}}
            ],
            "explanation": "Moving UGV1",
        }

        parsed = agent._parse_response(response_dict)

        assert isinstance(parsed, AgentCommandsResponse)
        assert parsed.type == ResponseType.COMMANDS
        assert len(parsed.commands) == 1
        assert parsed.commands[0].command == "go_to"
        assert parsed.commands[0].target == "ugv1"

    def test_parse_clarification_response(self):
        """Test parsing a clarification response."""
        agent = CommanderAgent()

        response_dict = {
            "type": "clarification",
            "question": "Which platform?",
            "options": ["UGV1", "UGV2"],
        }

        parsed = agent._parse_response(response_dict)

        assert isinstance(parsed, AgentClarificationResponse)
        assert parsed.type == ResponseType.CLARIFICATION
        assert "Which platform" in parsed.question

    def test_parse_info_response(self):
        """Test parsing an info response."""
        agent = CommanderAgent()

        response_dict = {
            "type": "response",
            "message": "All platforms are operational.",
        }

        parsed = agent._parse_response(response_dict)

        assert parsed.type == ResponseType.RESPONSE
        assert "operational" in parsed.message

    def test_infer_commands_type(self):
        """Test inferring type when not specified."""
        agent = CommanderAgent()

        response_dict = {
            "commands": [{"command": "stop", "target": "all", "params": {}}],
            "explanation": "Stop all",
        }

        parsed = agent._parse_response(response_dict)

        assert isinstance(parsed, AgentCommandsResponse)


# ──────────────────────────────────────────────────────────────────────────────
# Command Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCommandValidation:
    """Tests for command validation against playbook."""

    def test_valid_command_passes(self):
        """Test that valid commands pass validation."""
        agent = CommanderAgent()

        response = AgentCommandsResponse(
            commands=[
                CommandEnvelope(command="go_to", target="ugv1", params={"x": 10}),
                CommandEnvelope(command="stop", target="all", params={}),
            ],
            explanation="Test",
        )

        validated = agent._validate_commands(response)

        assert isinstance(validated, AgentCommandsResponse)
        assert len(validated.commands) == 2

    def test_invalid_command_rejected(self):
        """Test that invalid commands are rejected."""
        agent = CommanderAgent()

        response = AgentCommandsResponse(
            commands=[
                CommandEnvelope(command="invalid_command", target="ugv1", params={}),
            ],
            explanation="Test",
        )

        validated = agent._validate_commands(response)

        assert isinstance(validated, AgentErrorResponse)
        assert "invalid_command" in validated.details
        assert "not in playbook" in validated.details

    def test_all_playbook_commands_valid(self):
        """Test that all playbook commands are recognized."""
        expected = {
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

        assert VALID_COMMANDS == expected


# ──────────────────────────────────────────────────────────────────────────────
# Fleet State Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestFleetStateContext:
    """Tests for fleet state context."""

    def test_set_fleet_state(self):
        """Test setting fleet state."""
        agent = CommanderAgent()

        state = FleetState(
            platforms={
                "ugv1": Platform(
                    id="ugv1",
                    name="UGV Alpha",
                    type=PlatformType.UGV,
                    position=Position(x=10, y=20, z=0),
                )
            }
        )

        agent.set_fleet_state(state)

        assert agent.fleet_state.platforms["ugv1"].position.x == 10


# ──────────────────────────────────────────────────────────────────────────────
# Integration Tests (require API key - marked as skip by default)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason="Requires GEMINI_API_KEY")
class TestAgentIntegration:
    """Integration tests that require a real API key."""

    @pytest.mark.asyncio
    async def test_simple_command(self):
        """Test processing a simple command."""
        agent = CommanderAgent()
        response = await agent.process_message("Move UGV1 to checkpoint alpha")

        assert response.type in (ResponseType.COMMANDS, ResponseType.CLARIFICATION)

    @pytest.mark.asyncio
    async def test_ambiguous_command_asks_clarification(self):
        """Test that ambiguous commands ask for clarification."""
        agent = CommanderAgent()
        response = await agent.process_message("Move it over there")

        # Should ask for clarification, not guess
        assert response.type == ResponseType.CLARIFICATION

    @pytest.mark.asyncio
    async def test_conversation_memory(self):
        """Test that conversation context is maintained."""
        agent = CommanderAgent()

        # First message
        await agent.process_message("Move UGV1 to checkpoint alpha")

        # Follow-up
        response = await agent.process_message("Now do the same but slower")

        # Should understand context
        assert response.type == ResponseType.COMMANDS
