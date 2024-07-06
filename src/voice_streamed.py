import asyncio
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from azure.cognitiveservices.speech import AudioConfig, SpeechConfig, SpeechRecognizer, ResultReason, CancellationReason, audio, PropertyId, AudioStreamContainerFormat
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Your Azure Speech key and region
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
DEBUG=False

@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("voice_streamed.html", {"request": request})

@app.websocket("/ws/{language}")
async def websocket_endpoint(websocket: WebSocket, language: str):
    await websocket.accept()
    disconnected = False
    try:
        speech_config = SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        speech_config.speech_recognition_language = language

        if (DEBUG):
            speech_config.enable_audio_logging()
            speech_config.set_property(PropertyId.Speech_LogFilename, "../logs/trace.txt")
            is_audio_logging_enabled = speech_config.get_property(property_id=PropertyId.SpeechServiceConnection_EnableAudioLogging)
            logging.info(f"Audio logging {is_audio_logging_enabled}")
        
        audio_format = audio.AudioStreamFormat(compressed_stream_format=AudioStreamContainerFormat.ANY)
        stream = audio.PushAudioInputStream(stream_format=audio_format)
        audio_config = audio.AudioConfig(stream=stream)
        recognizer = SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        loop = asyncio.get_event_loop()

        def recognizing_cb(evt):
            logging.info(f"RECOGNIZING: {evt.result.text}")
            # Recognized event is already pushing the complete to web socket
            # loop.create_task(websocket.send_text(evt.result.text))

        def recognized_cb(evt):
            if evt.result.reason == ResultReason.RecognizedSpeech:
                logging.info(f"RECOGNIZED: {evt.result.text}")
                loop.create_task(websocket.send_text(evt.result.text))
            elif evt.result.reason == ResultReason.NoMatch:
                logging.info("No speech could be recognized")
                loop.create_task(websocket.send_text("No speech could be recognized"))
            elif evt.result.reason == ResultReason.Canceled:
                logging.info("Speech Recognition canceled: {}".format(evt.result.cancellation_details.reason))
                if evt.result.cancellation_details.reason == CancellationReason.Error:
                    logging.info("Error details: {}".format(evt.result.cancellation_details.error_details))
            else:
                logging.info(f"EVENT: {evt.result.text} - {evt.result.reason}")

        def session_started_cb(evt):
            logging.info(f'SESSION STARTED: {evt}')

        def session_stopped_cb(evt):
            logging.info(f'SESSION STOPPED: {evt}')

        def canceled_cb(evt):
            logging.error(f'CANCELED: {evt}')

        def speech_start_detected_cb(evt):
            logging.error(f'SPEEECH START DETECTED: {evt}')
        
        def speech_end_detected_cb(evt):
            logging.error(f'SPEECH STOP DETECTED: {evt}')
        
        def stop_cb(evt):
            logging.error('CLOSING on {}'.format(evt))
            recognizer.stop_continuous_recognition()
            nonlocal disconnected
            disconnected = True

        recognizer.recognizing.connect(recognizing_cb)
        recognizer.recognized.connect(recognized_cb)
        recognizer.session_started.connect(session_started_cb)
        recognizer.session_stopped.connect(session_stopped_cb)
        recognizer.canceled.connect(canceled_cb)
        recognizer.speech_start_detected.connect(speech_start_detected_cb)
        recognizer.speech_end_detected.connect(speech_end_detected_cb)
        recognizer.canceled.connect(stop_cb)
 
        recognizer.start_continuous_recognition_async()
        
        expected_bytes_per_chunk = 3200
        buffer = bytearray()

        try:

            while not disconnected:
                data = await websocket.receive_bytes()
                logging.info(f"Received audio data {len(data)} bytes")

                # Add received data to buffer
                buffer.extend(data)

                # Check if buffer has enough data to process a chunk
                while len(buffer) >= expected_bytes_per_chunk:
                    # Process the chunk
                    chunk = buffer[:expected_bytes_per_chunk]
                    stream.write(bytes(chunk))

                    # Log the processed chunk size
                    logging.info(f"Processed a chunk of {len(chunk)} bytes")

                    # Remove processed chunk from buffer
                    buffer = buffer[expected_bytes_per_chunk:]

                    # If the code reaches here, it means the buffer does not have enough data to form a complete chunk
                    # The loop will continue, and more data will be added to the buffer in the next iteration
        except WebSocketDisconnect:
            print("WebSocket disconnected")
            disconnected = True
        except Exception as e:
            logging.error(f"An error occurred reading data: {str(e)}")
            await websocket.send_text(f"An error occurred reading data: {str(e)}")

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        await websocket.send_text(f"An error occurred: {str(e)}")
    finally:
        if not disconnected:
            await websocket.close()
            logging.info('WebSocket connection closed')
        else:
            logging.info('WebSocket connection already closed')

