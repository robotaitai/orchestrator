"""
MuJoCo Offscreen Rendering

Renders the MuJoCo simulation to frames for streaming to the frontend.
"""

import asyncio
import base64
import io
import logging
import time
from typing import Any, Callable, Coroutine

from commander.settings import settings

logger = logging.getLogger("commander.sim.renderer")

# Check if MuJoCo rendering is available
try:
    import mujoco
    from PIL import Image
    RENDERING_AVAILABLE = True
except ImportError as e:
    RENDERING_AVAILABLE = False
    logger.warning(f"MuJoCo rendering not available: {e}")


class MuJoCoRenderer:
    """
    Offscreen renderer for MuJoCo simulation.
    
    Renders frames at a configurable FPS and encodes them as JPEG/PNG
    for streaming to the frontend.
    """
    
    def __init__(
        self,
        width: int = 800,
        height: int = 600,
        fps: int | None = None,
    ) -> None:
        """Initialize the renderer."""
        self.width = width
        self.height = height
        self.fps = fps or settings.sim_render_fps
        
        self._renderer: Any = None
        self._model: Any = None
        self._data: Any = None
        
        # Frame callbacks
        self._frame_callbacks: list[Callable[[str], Coroutine]] = []
        
        # Render loop
        self._render_task: asyncio.Task | None = None
        self._running = False
        
        # Camera settings
        self.camera = CameraSettings()
        
        logger.info(f"MuJoCoRenderer initialized ({width}x{height} @ {self.fps}fps)")
    
    def attach(self, model: Any, data: Any) -> bool:
        """Attach to a MuJoCo model and data."""
        if not RENDERING_AVAILABLE:
            logger.warning("Cannot attach renderer - MuJoCo not available")
            return False
        
        self._model = model
        self._data = data
        
        try:
            self._renderer = mujoco.Renderer(model, height=self.height, width=self.width)
            logger.info("Renderer attached to MuJoCo model")
            return True
        except Exception as e:
            logger.error(f"Failed to create renderer: {e}")
            return False
    
    def render_frame(self) -> bytes | None:
        """Render a single frame and return as JPEG bytes."""
        if not RENDERING_AVAILABLE or self._renderer is None:
            return None
        
        try:
            # Update scene
            self._renderer.update_scene(self._data, camera=self.camera.name)
            
            # Render
            pixels = self._renderer.render()
            
            # Convert to JPEG
            image = Image.fromarray(pixels)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=80)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Render error: {e}")
            return None
    
    def render_frame_base64(self) -> str | None:
        """Render a frame and return as base64-encoded JPEG."""
        frame_bytes = self.render_frame()
        if frame_bytes:
            return base64.b64encode(frame_bytes).decode("utf-8")
        return None
    
    async def start(self) -> None:
        """Start the render loop."""
        if self._render_task is not None:
            return
        
        self._running = True
        self._render_task = asyncio.create_task(self._render_loop())
        logger.info(f"Render loop started at {self.fps} FPS")
    
    async def stop(self) -> None:
        """Stop the render loop."""
        self._running = False
        if self._render_task:
            self._render_task.cancel()
            try:
                await self._render_task
            except asyncio.CancelledError:
                pass
            self._render_task = None
        logger.info("Render loop stopped")
    
    async def _render_loop(self) -> None:
        """Main render loop."""
        frame_interval = 1.0 / self.fps
        
        while self._running:
            try:
                start_time = time.time()
                
                # Render frame
                frame_b64 = self.render_frame_base64()
                
                if frame_b64:
                    # Broadcast to callbacks
                    await self._broadcast_frame(frame_b64)
                
                # Sleep to maintain FPS
                elapsed = time.time() - start_time
                sleep_time = max(0, frame_interval - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Render loop error: {e}")
                await asyncio.sleep(0.1)
    
    async def _broadcast_frame(self, frame_b64: str) -> None:
        """Broadcast frame to all registered callbacks."""
        for callback in self._frame_callbacks:
            try:
                await callback(frame_b64)
            except Exception as e:
                logger.error(f"Frame callback error: {e}")
    
    def on_frame(self, callback: Callable[[str], Coroutine]) -> None:
        """Register a callback for frame updates."""
        self._frame_callbacks.append(callback)
    
    def set_camera(
        self,
        azimuth: float | None = None,
        elevation: float | None = None,
        distance: float | None = None,
        lookat: tuple[float, float, float] | None = None,
    ) -> None:
        """Update camera settings."""
        if azimuth is not None:
            self.camera.azimuth = azimuth
        if elevation is not None:
            self.camera.elevation = elevation
        if distance is not None:
            self.camera.distance = distance
        if lookat is not None:
            self.camera.lookat = lookat


class CameraSettings:
    """Camera configuration for rendering."""
    
    def __init__(self) -> None:
        # Camera name (empty for free camera)
        self.name: str = ""
        
        # Free camera settings
        self.azimuth: float = 135.0  # degrees
        self.elevation: float = -30.0  # degrees
        self.distance: float = 40.0  # meters
        self.lookat: tuple[float, float, float] = (0.0, 0.0, 0.0)


# Singleton instance
_renderer: MuJoCoRenderer | None = None


def get_renderer() -> MuJoCoRenderer:
    """Get or create the global renderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = MuJoCoRenderer()
    return _renderer
