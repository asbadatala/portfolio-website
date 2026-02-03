"""
Deepgram service for Speech-to-Text (Flux) and Text-to-Speech.
Handles WebSocket connections to Deepgram APIs for real-time streaming.
"""
import json
import asyncio
from typing import Callable, Optional
from enum import Enum

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import InvalidStatusCode

from config import logger, DEEPGRAM_API_KEY


class FluxEventType(Enum):
    """Event types from Deepgram Flux STT."""
    CONNECTED = "Connected"
    TRANSCRIPT = "Transcript"
    END_OF_TURN = "EndOfTurn"
    EAGER_END_OF_TURN = "EagerEndOfTurn"
    TURN_RESUMED = "TurnResumed"
    SPEECH_STARTED = "SpeechStarted"
    UTTERANCE_END = "UtteranceEnd"
    ERROR = "Error"
    CLOSE = "Close"


class FluxSTTClient:
    """
    Async WebSocket client for Deepgram Flux speech-to-text.
    
    Flux is the first conversational speech recognition model built for voice agents.
    Ref: https://developers.deepgram.com/docs/flux/quickstart
    
    Key features:
    - EndOfTurn: User finished speaking, ready for response
    - EagerEndOfTurn: Early signal to start preparing response  
    - TurnResumed: User continued speaking, cancel early response
    - ~260ms end-of-turn detection latency
    """
    
    # Flux requires /v2/listen endpoint
    FLUX_URL = "wss://api.deepgram.com/v2/listen"
    
    def __init__(
        self,
        on_transcript: Optional[Callable[[str, bool], None]] = None,
        on_end_of_turn: Optional[Callable[[str], None]] = None,
        on_eager_end_of_turn: Optional[Callable[[str], None]] = None,
        on_turn_resumed: Optional[Callable[[], None]] = None,
        on_speech_started: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize Flux STT client.
        
        Args:
            on_transcript: Called with (transcript, is_final) for each transcript
            on_end_of_turn: Called with full turn transcript when turn ends
            on_eager_end_of_turn: Called early when turn likely ending (for faster response)
            on_turn_resumed: Called when user continues speaking after eager signal
            on_speech_started: Called when user starts speaking
            on_error: Called on errors
        """
        self.on_transcript = on_transcript
        self.on_end_of_turn = on_end_of_turn
        self.on_eager_end_of_turn = on_eager_end_of_turn
        self.on_turn_resumed = on_turn_resumed
        self.on_speech_started = on_speech_started
        self.on_error = on_error
        
        self._ws: Optional[WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_connected = False
        self._current_turn_transcript = ""
    
    async def connect(
        self,
        encoding: str = "linear16",
        sample_rate: int = 16000,
        eot_threshold: float = 0.7,
        eager_eot_threshold: Optional[float] = 0.5,
        eot_timeout_ms: int = 5000,
    ):
        """
        Connect to Deepgram Flux STT via WebSocket.
        
        Flux requires /v2/listen endpoint with model=flux-general-en.
        Ref: https://developers.deepgram.com/docs/flux/quickstart
        
        Args:
            encoding: Audio encoding (linear16, mulaw, alaw, opus)
            sample_rate: Sample rate in Hz (8000, 16000, 24000, 44100, 48000)
            eot_threshold: Confidence for EndOfTurn (0.5-0.9, default 0.7)
            eager_eot_threshold: Confidence for EagerEndOfTurn (0.3-0.9, enables early response)
            eot_timeout_ms: Max silence before forcing EndOfTurn (500-10000, default 5000)
        """
        # Validate API key
        if not DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is not set in environment variables")
        
        # Build Flux URL with parameters
        # Ref: https://developers.deepgram.com/docs/flux/quickstart#audio-format-requirements
        # Ref: https://developers.deepgram.com/docs/flux/configuration
        params = {
            "model": "flux-general-en",
            "encoding": encoding,
            "sample_rate": str(sample_rate),
            # End-of-turn detection parameters (must be strings)
            "eot_threshold": str(eot_threshold),
            "eot_timeout_ms": str(eot_timeout_ms),
        }
        
        # EagerEndOfTurn enables early response generation
        if eager_eot_threshold is not None:
            params["eager_eot_threshold"] = str(eager_eot_threshold)
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        flux_url = f"{self.FLUX_URL}?{query_string}"
        logger.info(f"Connecting to Flux: {flux_url}")
        
        # Connect with Authorization header
        # Ref: https://developers.deepgram.com/reference/authentication
        auth_headers = [("Authorization", f"Token {DEEPGRAM_API_KEY}")]
        
        try:
            self._ws = await websockets.connect(flux_url, additional_headers=auth_headers)
            self._is_connected = True
            self._current_turn_transcript = ""
            
            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info("Connected to Deepgram Flux STT")
            
        except InvalidStatusCode as e:
            status_code = e.status_code
            logger.error(f"Flux connection rejected with HTTP {status_code}")
            
            if status_code == 401:
                error_msg = "Invalid Deepgram API key. Please check your DEEPGRAM_API_KEY."
            elif status_code == 403:
                error_msg = "Deepgram API key does not have access to Flux. Please check your plan."
            elif status_code == 400:
                error_msg = f"Bad request to Flux API. Check parameters. URL: {flux_url}"
                logger.error(f"Full URL was: {flux_url}")
            else:
                error_msg = f"Flux connection failed with HTTP {status_code}"
            
            if self.on_error:
                self.on_error(error_msg)
            raise ValueError(error_msg) from e
            
        except Exception as e:
            logger.error(f"Failed to connect to Flux: {type(e).__name__}: {e}")
            error_msg = f"Could not connect to Deepgram Flux: {e}"
            if self.on_error:
                self.on_error(error_msg)
            raise ValueError(error_msg) from e
    
    async def send_audio(self, audio_data: bytes):
        """Send audio data to Deepgram for transcription."""
        if self._ws and self._is_connected:
            try:
                await self._ws.send(audio_data)
            except Exception as e:
                logger.error(f"Error sending audio to Flux: {e}")
                if self.on_error:
                    self.on_error(str(e))
    
    async def close(self):
        """Close the WebSocket connection."""
        self._is_connected = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            try:
                # Send close frame
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing Flux connection: {e}")
        
        logger.info("Closed Deepgram STT connection")
    
    async def _receive_loop(self):
        """Background task to receive and process messages from Deepgram."""
        try:
            async for message in self._ws:
                if not self._is_connected:
                    break
                    
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from Deepgram: {message[:100]}")
                except Exception as e:
                    logger.error(f"Error handling Deepgram message: {e}")
                    
        except websockets.ConnectionClosed:
            logger.info("Deepgram STT connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Deepgram receive loop error: {e}")
            if self.on_error:
                self.on_error(str(e))
    
    async def _handle_message(self, data: dict):
        """Process a message from Deepgram Flux."""
        msg_type = data.get("type", "")
        
        if msg_type == FluxEventType.CONNECTED.value:
            logger.info("Flux STT ready")
            return
        
        # TurnInfo events: EndOfTurn, EagerEndOfTurn, TurnResumed, StartOfTurn
        if msg_type == "TurnInfo":
            event = data.get("event", "")
            transcript = data.get("transcript", "")
            
            if event == "EndOfTurn":
                logger.info(f"End of turn: '{transcript[:50]}...' " if len(transcript) > 50 else f"End of turn: '{transcript}'")
                if self.on_end_of_turn and transcript:
                    self.on_end_of_turn(transcript)
                self._current_turn_transcript = ""
                return
                
            elif event == "EagerEndOfTurn":
                if self.on_eager_end_of_turn and transcript:
                    self.on_eager_end_of_turn(transcript)
                return
                
            elif event == "TurnResumed":
                if self.on_turn_resumed:
                    self.on_turn_resumed()
                return
            
            elif event in ("SpeechStarted", "StartOfTurn"):
                if self.on_speech_started:
                    self.on_speech_started()
                return
            
            elif event == "Update":
                return
            
            return
        
        # Standalone SpeechStarted event
        if msg_type == FluxEventType.SPEECH_STARTED.value or msg_type == "SpeechStarted":
            if self.on_speech_started:
                self.on_speech_started()
            return
            
        # Handle Error event
        if msg_type == FluxEventType.ERROR.value:
            error_msg = data.get("message", "Unknown error")
            logger.error(f"Flux error: {error_msg}")
            if self.on_error:
                self.on_error(error_msg)
            return
        
        # Handle Transcript events (interim results)
        # Format: {"type": "Transcript", "transcript": "...", "is_final": false}
        if msg_type == FluxEventType.TRANSCRIPT.value:
            transcript = data.get("transcript", "")
            is_final = data.get("is_final", False)
            
            if transcript:
                # Track transcript for display
                if self.on_transcript:
                    self.on_transcript(transcript, is_final)
            return
        
        # Unknown message types (ignore silently)
        pass
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected


class DeepgramTTSClient:
    """
    Async WebSocket client for Deepgram Text-to-Speech.
    
    Streams text in chunks and receives audio output in real-time.
    """
    
    BASE_URL = "wss://api.deepgram.com/v1/speak"
    
    def __init__(
        self,
        on_audio: Optional[Callable[[bytes], None]] = None,
        on_flush: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize TTS client.
        
        Args:
            on_audio: Called with audio bytes as they arrive
            on_flush: Called when all queued text has been spoken
            on_error: Called on errors
        """
        self.on_audio = on_audio
        self.on_flush = on_flush
        self.on_error = on_error
        
        self._ws: Optional[WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_connected = False
        self._flush_event = asyncio.Event()  # For waiting on flush completion
        self._pending_flushes = 0  # Track pending flush requests
    
    async def connect(
        self,
        model: str = "aura-2-odysseus-en",
        encoding: str = "linear16",
        sample_rate: int = 16000,
        container: Optional[str] = None,
    ):
        """
        Connect to Deepgram TTS.
        
        Args:
            model: Voice model (aura-asteria-en, aura-luna-en, etc.)
            encoding: Audio encoding (linear16, mp3, opus, etc.)
            sample_rate: Sample rate in Hz
            container: Optional container format (wav, ogg, etc.)
        """
        # Validate API key
        if not DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is not set in environment variables")
        
        # Build URL with parameters
        params = {
            "model": model,
            "encoding": encoding,
            "sample_rate": str(sample_rate),
        }
        if container:
            params["container"] = container
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.BASE_URL}?{query_string}"
        
        logger.info(f"Connecting to Deepgram TTS (model: {model})")
        
        # Connect with Authorization header (same as STT)
        auth_headers = [("Authorization", f"Token {DEEPGRAM_API_KEY}")]
        
        try:
            self._ws = await websockets.connect(url, additional_headers=auth_headers)
            self._is_connected = True
            self._pending_flushes = 0  # Reset on new connection
            self._flush_event.clear()
            self._audio_chunks_received = 0  # Track audio chunks
            
            # Start receiving audio
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info("Connected to Deepgram TTS")
            
        except InvalidStatusCode as e:
            logger.error(f"Failed to connect to TTS: HTTP {e.status_code} - {e}")
            error_msg = f"Deepgram TTS API rejected connection (HTTP {e.status_code}). "
            if e.status_code == 400:
                error_msg += "Check API key and URL parameters."
            elif e.status_code == 401:
                error_msg += "Invalid API key."
            elif e.status_code == 403:
                error_msg += "API key lacks required permissions."
            else:
                error_msg += f"Server error: {e}"
            if self.on_error:
                self.on_error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            logger.error(f"Failed to connect to TTS: {e}")
            if self.on_error:
                self.on_error(str(e))
            raise
    
    async def send_text(self, text: str):
        """
        Send text to be synthesized.
        
        Args:
            text: Text to convert to speech
        """
        if self._ws and self._is_connected:
            try:
                message = {"type": "Speak", "text": text}
                await self._ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending text to TTS: {e}")
                if self.on_error:
                    self.on_error(str(e))
    
    async def flush(self):
        """
        Flush any remaining text and signal end of input.
        Call this after sending all text to ensure all audio is generated.
        """
        if self._ws and self._is_connected:
            try:
                self._pending_flushes += 1
                self._flush_event.clear()
                await self._ws.send(json.dumps({"type": "Flush"}))
            except Exception as e:
                logger.error(f"Error flushing TTS: {e}")
    
    async def flush_and_wait(self, timeout: float = 10.0):
        """
        Send flush and wait for all audio to be generated.
        
        Args:
            timeout: Maximum seconds to wait for flush to complete
        """
        await self.flush()
        try:
            await asyncio.wait_for(self._flush_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Flush wait timed out after {timeout}s")
    
    async def close(self, force: bool = False):
        """
        Close the WebSocket connection.
        
        Args:
            force: If True, close immediately without waiting (for interruptions)
        """
        self._is_connected = False
        
        if force:
            # Fast close for interruptions - don't wait for anything
            if self._receive_task:
                self._receive_task.cancel()
            if self._ws:
                try:
                    asyncio.create_task(self._ws.close())
                except Exception:
                    pass
            logger.debug("Force closed TTS")
            return
        
        # Graceful close
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "Close"}))
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing TTS connection: {e}")
        
        logger.info("Closed Deepgram TTS connection")
    
    async def _receive_loop(self):
        """Background task to receive audio from Deepgram."""
        try:
            async for message in self._ws:
                if not self._is_connected:
                    break
                
                if isinstance(message, bytes):
                    self._audio_chunks_received += 1
                    if self.on_audio:
                        self.on_audio(message)
                else:
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")
                        
                        if msg_type == "Flushed":
                            self._pending_flushes = max(0, self._pending_flushes - 1)
                            if self._pending_flushes == 0:
                                self._flush_event.set()
                            if self.on_flush:
                                self.on_flush()
                        elif msg_type == "Error":
                            error_msg = data.get("message", "Unknown TTS error")
                            logger.error(f"TTS error: {error_msg}")
                            if self.on_error:
                                self.on_error(error_msg)
                    except json.JSONDecodeError:
                        pass
                        
        except websockets.ConnectionClosed:
            logger.info("TTS connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"TTS receive loop error: {e}")
            if self.on_error:
                self.on_error(str(e))
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected


