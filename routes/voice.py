"""
Voice API routes.
WebSocket endpoint for real-time voice streaming with Deepgram Flux STT and TTS.
"""
import json
import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import logger
from flows.voice import VoiceFlow

router = APIRouter(tags=["voice"])


@router.websocket("/voice/stream")
async def voice_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time voice streaming.
    
    Protocol:
    - Client sends: Binary audio frames (WebM/Opus)
    - Client sends: JSON control messages
        - {"type": "start", "session_id": "..."} - Start voice session
        - {"type": "stop"} - End voice session
    
    - Server sends: Binary audio frames (Linear16 PCM at 16kHz)
    - Server sends: JSON control messages
        - {"type": "state", "state": "listening|processing|speaking"}
        - {"type": "transcript", "text": "...", "is_final": true/false}
        - {"type": "response", "text": "..."} - Response text chunks
        - {"type": "error", "message": "..."}
        - {"type": "ready"} - Voice flow ready
    """
    await websocket.accept()
    
    voice_flow: Optional[VoiceFlow] = None
    send_queue: asyncio.Queue = asyncio.Queue()
    
    async def send_json(data: dict):
        """Queue a JSON message to send."""
        await send_queue.put(("json", data))
    
    async def send_audio(audio: bytes):
        """Queue audio data to send."""
        await send_queue.put(("audio", audio))
    
    async def sender_task():
        """Background task to send messages from queue."""
        try:
            while True:
                msg_type, data = await send_queue.get()
                try:
                    if msg_type == "json":
                        await websocket.send_json(data)
                    else:
                        await websocket.send_bytes(data)
                except Exception as e:
                    logger.error(f"Error sending WebSocket message: {e}")
                    break
        except asyncio.CancelledError:
            pass
    
    # Callbacks for VoiceFlow
    def on_transcript(text: str, is_final: bool):
        asyncio.create_task(send_json({
            "type": "transcript",
            "text": text,
            "is_final": is_final
        }))
    
    def on_response_text(text: str):
        asyncio.create_task(send_json({
            "type": "response",
            "text": text
        }))
    
    def on_audio(audio: bytes):
        asyncio.create_task(send_audio(audio))
    
    def on_state_change(state: str):
        asyncio.create_task(send_json({
            "type": "state",
            "state": state
        }))
    
    def on_error(error: str):
        asyncio.create_task(send_json({
            "type": "error",
            "message": error
        }))
    
    def on_interrupt():
        asyncio.create_task(send_json({
            "type": "interrupt"
        }))
    
    # Start sender task
    sender = asyncio.create_task(sender_task())
    
    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Binary audio data (Linear16 PCM at 16kHz)
                audio_data = message["bytes"]
                if voice_flow:
                    await voice_flow.process_audio(audio_data)
                    
            elif "text" in message:
                # JSON control message
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")
                    
                    if msg_type == "start":
                        # Start voice session
                        session_id = data.get("session_id")
                        
                        if voice_flow:
                            await voice_flow.stop()
                        
                        voice_flow = VoiceFlow(
                            session_id=session_id,
                            on_transcript=on_transcript,
                            on_response_text=on_response_text,
                            on_audio=on_audio,
                            on_state_change=on_state_change,
                            on_interrupt=on_interrupt,
                            on_error=on_error,
                        )
                        
                        await voice_flow.start()
                        await send_json({"type": "ready"})
                        logger.info(f"Voice session started (session: {session_id})")
                        
                    elif msg_type == "stop":
                        if voice_flow:
                            await voice_flow.stop()
                            voice_flow = None
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in voice WebSocket: {message['text'][:100]}")
                except Exception as e:
                    logger.error(f"Error processing voice message: {e}")
                    await send_json({"type": "error", "message": str(e)})
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Voice WebSocket error: {e}")
    finally:
        sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass
        if voice_flow:
            await voice_flow.stop()
