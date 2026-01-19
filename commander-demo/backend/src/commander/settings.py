"""Application settings loaded from environment."""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SimMode(str, Enum):
    """Simulation mode."""
    STATE = "state"    # Simple state-based (instant teleport)
    MUJOCO = "mujoco"  # Full MuJoCo physics simulation


class AvoidPolicy(str, Enum):
    """Policy for handling paths that cross no-go zones."""
    REJECT = "reject"  # Reject command with error message
    DETOUR = "detour"  # Auto-insert detour waypoints around obstacle


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Server
    # ──────────────────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # ──────────────────────────────────────────────────────────────────────────
    # LLM (Gemini)
    # ──────────────────────────────────────────────────────────────────────────
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(
        default="gemini-1.5-flash", description="Gemini model name"
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Simulation
    # ──────────────────────────────────────────────────────────────────────────
    sim_mode: SimMode = Field(
        default=SimMode.STATE, description="Simulation mode: 'state' or 'mujoco'"
    )
    sim_tick_rate: float = Field(
        default=0.02, description="Simulation tick rate in seconds (50Hz default)"
    )
    sim_realtime: bool = Field(
        default=True, description="Run simulation in realtime"
    )
    avoid_policy: AvoidPolicy = Field(
        default=AvoidPolicy.REJECT, 
        description="Policy for paths crossing no-go zones: 'reject' or 'detour'"
    )
    sim_render_fps: int = Field(
        default=15, description="MuJoCo render frame rate for streaming"
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_dir: Path = Field(
        default=Path("./logs"), description="Directory for log files"
    )
    log_json: bool = Field(
        default=False, description="Use JSON format for logs"
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Application metadata
    # ──────────────────────────────────────────────────────────────────────────
    app_name: str = "Commander Demo"
    app_version: str = "0.1.0"


# Global settings instance (loaded once at import time)
settings = Settings()
