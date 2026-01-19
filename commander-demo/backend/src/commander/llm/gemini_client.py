"""
Gemini API Client

Wrapper around the official google-genai library.
Handles API calls, retries, and response parsing.
"""

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from commander.settings import settings

logger = logging.getLogger("commander.llm.client")


class GeminiClientError(Exception):
    """Error from Gemini API."""

    pass


class GeminiClient:
    """
    Client for Google Gemini API.
    
    Configured for structured JSON output with strict parsing.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Initialize the Gemini client.

        Args:
            api_key: Gemini API key (defaults to settings)
            model: Model name (defaults to settings)
        """
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model or settings.gemini_model

        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set - client will fail on API calls")
            self._client = None
        else:
            self._client = genai.Client(api_key=self.api_key)

        logger.info(f"Gemini client initialized with model: {self.model_name}")

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key) and self._client is not None

    async def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.1,  # Low temp for deterministic JSON
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """
        Generate a JSON response from the model.

        Args:
            prompt: User prompt
            system_instruction: System instruction for the model
            temperature: Sampling temperature (low = more deterministic)
            max_tokens: Maximum tokens to generate

        Returns:
            Parsed JSON dict

        Raises:
            GeminiClientError: If API call fails or JSON parsing fails
        """
        if not self.is_configured:
            raise GeminiClientError("Gemini API key not configured")

        try:
            # Build config
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                system_instruction=system_instruction,
            )

            # Generate response
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            # Extract text
            if not response.text:
                raise GeminiClientError("Empty response from model")

            # Parse JSON
            return self._parse_json_response(response.text)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise GeminiClientError(f"Failed to parse JSON response: {e}")
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise GeminiClientError(f"Gemini API error: {e}")

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_instruction: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """
        Multi-turn chat with JSON output.

        Args:
            messages: List of {"role": "user"|"model", "content": "..."}
            system_instruction: System instruction
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Parsed JSON response
        """
        if not self.is_configured:
            raise GeminiClientError("Gemini API key not configured")

        try:
            # Build config
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                system_instruction=system_instruction,
            )

            # Convert messages to Gemini format
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part(text=msg["content"])],
                    )
                )

            # Generate response
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            if not response.text:
                raise GeminiClientError("Empty response from model")

            return self._parse_json_response(response.text)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise GeminiClientError(f"Failed to parse JSON response: {e}")
        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
            raise GeminiClientError(f"Gemini API error: {e}")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """
        Parse JSON from response text.

        Handles common issues like markdown code blocks.
        """
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        return json.loads(text)


# Singleton client instance
_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    """Get or create the singleton Gemini client."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
