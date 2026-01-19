#!/usr/bin/env python3
"""
Quick test script for the Gemini agent.

Usage:
    cd backend
    source .venv/bin/activate
    export GEMINI_API_KEY=your-key-here
    python scripts/test_chat.py
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from commander.llm.agent import CommanderAgent
from commander.core.models import FleetState, Platform, PlatformType, Position


async def main():
    # Create demo fleet
    fleet = FleetState(
        platforms={
            "ugv1": Platform(
                id="ugv1", name="UGV Alpha", type=PlatformType.UGV,
                position=Position(x=0, y=0, z=0),
            ),
            "ugv2": Platform(
                id="ugv2", name="UGV Bravo", type=PlatformType.UGV,
                position=Position(x=5, y=0, z=0),
            ),
            "uav1": Platform(
                id="uav1", name="UAV Delta", type=PlatformType.UAV,
                position=Position(x=0, y=0, z=15),
            ),
        }
    )

    agent = CommanderAgent(fleet_state=fleet)

    print("=" * 60)
    print("Commander Agent Test")
    print("=" * 60)
    print()

    # Test cases
    test_messages = [
        "Move UGV1 to checkpoint alpha",
        "Now do the same but slower",
        "What's the status of all platforms?",
        "Move it over there",  # Should ask for clarification
        "Stop all platforms",
    ]

    for msg in test_messages:
        print(f"User: {msg}")
        print("-" * 40)

        try:
            response = await agent.process_message(msg)
            print(f"Type: {response.type.value}")

            if hasattr(response, "commands"):
                for cmd in response.commands:
                    print(f"  Command: {cmd.command}")
                    print(f"  Target: {cmd.target}")
                    print(f"  Params: {cmd.params}")
                if hasattr(response, "explanation"):
                    print(f"  Explanation: {response.explanation}")
            elif hasattr(response, "question"):
                print(f"  Question: {response.question}")
                if response.options:
                    print(f"  Options: {response.options}")
            elif hasattr(response, "message"):
                print(f"  Message: {response.message}")
            elif hasattr(response, "error"):
                print(f"  Error: {response.error}")
                print(f"  Details: {response.details}")

        except Exception as e:
            print(f"  Error: {e}")

        print()

    print("=" * 60)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
