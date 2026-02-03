"""
Voice flow - handles voice-based conversation logic.
Orchestrates Deepgram Flux STT, RAG retrieval, LLM streaming, and Deepgram TTS
for real-time voice interactions with interruption support.
"""
import json
import asyncio
from enum import Enum
from typing import Optional, Callable, Any

from config import logger, jinja_env, OPENAI_API_KEY
from services.session import get_session_history, save_session_message, format_chat_history
from services.retrieval import retrieve_context
from services.deepgram import FluxSTTClient, DeepgramTTSClient
import httpx


class VoiceState(Enum):
    """State machine for voice conversation."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class VoiceFlow:
    """
    Orchestrates the voice conversation flow with interruption support.
    
    Flow:
    1. LISTENING: Receive audio from client → Deepgram Flux STT
    2. PROCESSING: On EndOfTurn → RAG retrieval + LLM streaming
    3. SPEAKING: Stream LLM output → Deepgram TTS → Audio back to client
    4. Interruption: If user speaks during SPEAKING, cancel and return to LISTENING
    
    Uses callbacks to communicate with the WebSocket handler.
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        on_transcript: Optional[Callable[[str, bool], Any]] = None,
        on_response_text: Optional[Callable[[str], Any]] = None,
        on_audio: Optional[Callable[[bytes], Any]] = None,
        on_state_change: Optional[Callable[[str], Any]] = None,
        on_interrupt: Optional[Callable[[], Any]] = None,
        on_error: Optional[Callable[[str], Any]] = None,
    ):
        """
        Initialize voice flow.
        
        Args:
            session_id: Session ID for conversation history
            on_transcript: Called with (text, is_final) for user speech
            on_response_text: Called with response text chunks
            on_audio: Called with TTS audio bytes
            on_state_change: Called when state changes
            on_interrupt: Called when user interrupts (to stop audio playback)
            on_error: Called on errors
        """
        self.session_id = session_id
        self.on_transcript = on_transcript
        self.on_response_text = on_response_text
        self.on_audio = on_audio
        self.on_state_change = on_state_change
        self.on_interrupt = on_interrupt
        self.on_error = on_error
        
        self._state = VoiceState.IDLE
        self._stt_client: Optional[FluxSTTClient] = None
        self._tts_client: Optional[DeepgramTTSClient] = None
        
        # For interruption handling
        self._response_task: Optional[asyncio.Task] = None
        self._interrupted = asyncio.Event()
        self._current_user_message = ""
    
    @property
    def state(self) -> VoiceState:
        return self._state
    
    def _set_state(self, new_state: VoiceState):
        """Update state and notify callback."""
        if self._state != new_state:
            logger.info(f"Voice state: {self._state.value} → {new_state.value}")
            self._state = new_state
            if self.on_state_change:
                self.on_state_change(new_state.value)
    
    async def start(self):
        """
        Initialize the voice flow and connect to Deepgram.
        """
        logger.info(f"Starting voice flow (session: {self.session_id})")
        
        try:
            # Initialize STT client with callbacks
            self._stt_client = FluxSTTClient(
                on_transcript=self._handle_transcript,
                on_end_of_turn=self._handle_end_of_turn,
                on_eager_end_of_turn=self._handle_eager_end_of_turn,
                on_turn_resumed=self._handle_turn_resumed,
                on_speech_started=self._handle_speech_started,
                on_error=self._handle_stt_error,
            )
            
            # Connect to Flux STT
            # Use linear16 encoding - browser sends raw PCM at 16kHz
            # Config: "Low-Latency Mode" from https://developers.deepgram.com/docs/flux/configuration
            await self._stt_client.connect(
                encoding="linear16",
                sample_rate=16000,
                eot_threshold=0.7,           # Default confidence for EndOfTurn
                eager_eot_threshold=0.4,     # Lower threshold for early EagerEndOfTurn
                eot_timeout_ms=6000,         # 6 seconds of silence forces EndOfTurn
            )
            
            self._set_state(VoiceState.LISTENING)
            
        except Exception as e:
            logger.error(f"Failed to start voice flow: {e}")
            if self.on_error:
                self.on_error(f"Failed to start: {str(e)}")
            raise
    
    async def stop(self):
        """
        Stop the voice flow and clean up connections.
        """
        logger.info(f"Stopping voice flow (session: {self.session_id})")
        
        # Cancel any ongoing response
        await self._cancel_response()
        
        # Close STT connection
        if self._stt_client:
            await self._stt_client.close()
            self._stt_client = None
        
        # Close TTS connection if open
        if self._tts_client:
            await self._tts_client.close()
            self._tts_client = None
        
        self._set_state(VoiceState.IDLE)
    
    async def process_audio(self, audio_data: bytes):
        """
        Process incoming audio data from the client.
        
        Args:
            audio_data: Raw Linear16 PCM audio bytes at 16kHz
        """
        if not self._stt_client or not self._stt_client.is_connected:
            logger.warning("STT client not connected, dropping audio")
            return
        
        try:
            # Send PCM directly to Deepgram
            await self._stt_client.send_audio(audio_data)
        except Exception as e:
            logger.error(f"Error sending audio to Deepgram: {e}")
    
    def _handle_transcript(self, text: str, is_final: bool):
        """Handle transcript from STT."""
        if is_final:
            self._current_user_message += " " + text
            self._current_user_message = self._current_user_message.strip()
        
        if self.on_transcript:
            self.on_transcript(text, is_final)
    
    def _handle_speech_started(self):
        """Handle user starting to speak - triggers interruption if AI is speaking."""
        if self._state == VoiceState.SPEAKING:
            logger.info("Interruption detected")
            self._interrupted.set()
            if self.on_interrupt:
                self.on_interrupt()
            asyncio.create_task(self._cancel_response())
            self._set_state(VoiceState.LISTENING)
    
    def _handle_eager_end_of_turn(self, transcript: str):
        """
        Handle early end-of-turn signal.
        Could start preparing response early, but we wait for confirmed EndOfTurn
        to avoid wasted LLM calls on false positives.
        """
        logger.debug(f"Eager end of turn: {transcript[:100]}...")
        # For now, just log - we'll wait for confirmed EndOfTurn
    
    def _handle_turn_resumed(self):
        """Handle user continuing to speak after eager signal."""
        logger.debug("User continued speaking")
        # If we started early processing, we'd cancel here
    
    def _handle_end_of_turn(self, transcript: str):
        """Handle confirmed end of user's turn - start generating response."""
        if not transcript.strip():
            return
        
        user_message = self._current_user_message or transcript
        self._current_user_message = ""
        
        logger.info(f"Processing: {user_message[:80]}...")
        
        async def start_new_response():
            # Cancel any existing response first
            self._interrupted.set()
            if self._tts_client:
                await self._tts_client.close(force=True)
                self._tts_client = None
            if self._response_task and not self._response_task.done():
                self._response_task.cancel()
                try:
                    await asyncio.wait_for(self._response_task, timeout=0.1)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Start new response
            self._interrupted.clear()
            self._set_state(VoiceState.PROCESSING)
            self._response_task = asyncio.create_task(
                self._generate_response(user_message)
            )
        
        asyncio.create_task(start_new_response())
    
    def _handle_stt_error(self, error: str):
        """Handle STT error."""
        logger.error(f"STT error: {error}")
        if self.on_error:
            self.on_error(f"Speech recognition error: {error}")
    
    async def _cancel_response(self):
        """Cancel ongoing response generation."""
        self._interrupted.set()
        
        if self._tts_client:
            await self._tts_client.close(force=True)
            self._tts_client = None
        
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            try:
                await asyncio.wait_for(self._response_task, timeout=0.1)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
    
    async def _generate_response(self, user_message: str):
        """
        Generate and speak response to user message.
        
        1. Retrieve RAG context
        2. Get session history
        3. Stream LLM response
        4. Stream TTS audio
        """
        try:
            # Save user message to history (non-blocking)
            if self.session_id:
                asyncio.create_task(
                    save_session_message(self.session_id, "user", user_message)
                )
            
            # Parallel: Get context and history
            context_task = asyncio.create_task(retrieve_context(user_message, k=6))
            
            if self.session_id:
                history_task = asyncio.create_task(get_session_history(self.session_id))
            else:
                history_task = None
            
            context, _ = await context_task
            
            if history_task:
                history = await history_task
                chat_history = format_chat_history(history, max_exchanges=5)
            else:
                chat_history = ""
            
            if self._interrupted.is_set():
                return
            
            # Initialize TTS client
            self._tts_client = DeepgramTTSClient(
                on_audio=self._handle_tts_audio,
                on_error=self._handle_tts_error,
            )
            
            await self._tts_client.connect(
                model="aura-2-odysseus-en",
                encoding="linear16",
                sample_rate=16000,
            )
            
            self._set_state(VoiceState.SPEAKING)
            
            # Stream LLM response and send to TTS
            full_response = ""
            sentence_buffer = ""
            
            async for text_chunk in self._stream_llm_response(user_message, context, chat_history):
                if self._interrupted.is_set():
                    break
                
                full_response += text_chunk
                sentence_buffer += text_chunk
                
                # Send to callback for display
                if self.on_response_text:
                    self.on_response_text(text_chunk)
                
                # Send complete sentences to TTS for natural speech
                # Don't flush each sentence - just send text continuously
                # TTS will stream audio back as it processes
                while True:
                    # Find sentence boundary
                    end_idx = -1
                    for punct in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                        idx = sentence_buffer.find(punct)
                        if idx != -1 and (end_idx == -1 or idx < end_idx):
                            end_idx = idx + len(punct)
                    
                    if end_idx == -1:
                        break
                    
                    sentence = sentence_buffer[:end_idx]
                    sentence_buffer = sentence_buffer[end_idx:]
                    
                    if sentence.strip() and self._tts_client:
                        await self._tts_client.send_text(sentence)
            
            # Send any remaining text and flush
            if sentence_buffer.strip() and self._tts_client and not self._interrupted.is_set():
                await self._tts_client.send_text(sentence_buffer)
            
            if self._tts_client and not self._interrupted.is_set():
                await self._tts_client.flush_and_wait(timeout=30.0)
            
            # Save assistant response to history
            if self.session_id and full_response and not self._interrupted.is_set():
                asyncio.create_task(
                    save_session_message(self.session_id, "assistant", full_response)
                )
            
            # Close TTS and return to listening
            if self._tts_client:
                await self._tts_client.close()
                self._tts_client = None
            
            if not self._interrupted.is_set():
                self._set_state(VoiceState.LISTENING)
            
        except asyncio.CancelledError:
            logger.info("Response generation cancelled")
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            if self.on_error:
                self.on_error(f"Response error: {str(e)}")
            self._set_state(VoiceState.LISTENING)
    
    def _handle_tts_audio(self, audio: bytes):
        """Handle audio from TTS."""
        if not self._interrupted.is_set() and self.on_audio:
            self.on_audio(audio)
    
    def _handle_tts_error(self, error: str):
        """Handle TTS error."""
        logger.error(f"TTS error: {error}")
        if self.on_error:
            self.on_error(f"Speech synthesis error: {error}")
    
    async def _stream_llm_response(self, message: str, context: str, chat_history: str):
        """
        Stream response from LLM.
        Yields text chunks.
        """
        # Render system prompt from voice-optimized Jinja template
        template = jinja_env.get_template("voice_prompt.j2")
        system_content = template.render(context=context, chat_history=chat_history)
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },
                json={
                    "model": "gpt-4.1",
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": message}
                    ],
                    "max_completion_tokens": 150,  # Very short for conversational voice
                    "stream": True
                },
                timeout=60.0
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_msg = error_text.decode('utf-8') if error_text else "Unknown error"
                    logger.error(f"OpenAI API error ({response.status_code}): {error_msg}")
                    yield "I'm sorry, I'm having trouble responding right now."
                    return
                
                async for line in response.aiter_lines():
                    if self._interrupted.is_set():
                        return
                    
                    if not line.strip():
                        continue
                    
                    if line.startswith("data: "):
                        data = line[6:].strip()
                        if data == "[DONE]":
                            return
                        
                        try:
                            parsed = json.loads(data)
                            choices = parsed.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            pass
