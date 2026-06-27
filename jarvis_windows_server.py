import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

import asyncio
import multiprocessing
import websockets
import json
import json as json_lib
import time
import threading
import queue
import sys
import re
import requests
import xml.etree.ElementTree as ET
import psutil
import numpy as np
import sounddevice as sd
import whisper
import tempfile
import edge_tts
import pygame
import pyttsx3
import torch
from datetime import datetime

torch.cuda.is_available = lambda: False

# Try importing face — skip if pygame not installed
try:
    from jarvis_face import create_face_controller
    FACE_AVAILABLE = True
except ImportError:
    FACE_AVAILABLE = False
    print("Pygame not available — running without face animations")

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
WEBSOCKET_HOST = _env("WEBSOCKET_HOST", "0.0.0.0")
WEBSOCKET_PORT = _env_int("WEBSOCKET_PORT", 8765)
WHISPER_MODEL = "small"
USER_NAME = _env("USER_NAME", "Vividh")

GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")

AI_PROVIDER = _env("AI_PROVIDER", "groq")

GROQ_API_KEY = _env("GROQ_API_KEY")
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY_HERE")
GEMINI_API_KEY = _env("GEMINI_API_KEY")

WEATHER_API_KEY = _env("WEATHER_API_KEY")
WEATHER_CITY = _env("WEATHER_CITY", "Noida")
NEWS_API_KEY = _env("NEWS_API_KEY")
NEWS_COUNTRY = _env("NEWS_COUNTRY", "in")

HISTORY_FILE = "jarvis_memory.json"
MAX_MESSAGES = 30   # recent raw messages
MAX_FACTS = 20       # long-term remembered facts

# Microsoft neural voice — en-GB-RyanNeural for a British Jarvis feel
TTS_VOICE = "en-GB-RyanNeural"
TTS_RATE = "-8%"

# ─────────────────────────────────────────
#  IDENTITY / SYSTEM PROMPT
# ─────────────────────────────────────────
JARVIS_IDENTITY = f"""You are Jarvis, a personal AI assistant built by {USER_NAME} as a passion project.
You run locally on a small desk device with a retro pixel-art animated face.
Your purpose is to help {USER_NAME} with daily tasks — reminders, weather updates,
controlling Spotify, casual conversation, and being a helpful desk companion.
You were created for fun and learning, combining hardware (mic, speaker, screen)
with AI to create a personal Jarvis-like assistant, inspired by Iron Man's AI."""

SYSTEM_PROMPT = f"""{JARVIS_IDENTITY}

You talk like a real person — warm, relaxed, casual. You're {USER_NAME}'s desk buddy, not a corporate bot.
Use 2-4 natural sentences. It's okay to be a little witty or friendly ("Yeah, sure thing" / "Oh nice").
Never sound stiff or robotic. Never say "I am functioning" or similar machine phrases.
Don't mention being an AI unless asked. Answer what was asked — don't ramble or stack questions.
Never pretend to play music or describe beats playing — the app handles real Spotify playback when you trigger it.
Never invent news headlines or weather — if you don't have real data, say you can't fetch it.
Never use asterisks or describe physical actions like *smiles* or *nods* — you are text and voice only."""

# ─────────────────────────────────────────
#  MEMORY — persistent messages + long-term facts
# ─────────────────────────────────────────
def load_history():
    """Load conversation history and facts from disk."""
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json_lib.load(f)
            return data.get('messages', []), data.get('facts', [])
    except FileNotFoundError:
        return [], []
    except Exception as e:
        print(f"Failed to load history: {e}")
        return [], []


def save_history():
    """Save conversation history and facts to disk."""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json_lib.dump({
                'messages': conversation_history,
                'facts': long_term_facts
            }, f, indent=2)
    except Exception as e:
        print(f"Failed to save history: {e}")


def add_to_history(role: str, content: str):
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > MAX_MESSAGES:
        conversation_history.pop(0)
    save_history()


def add_fact(fact: str):
    """Add a permanent fact Jarvis should always remember."""
    if fact not in long_term_facts:
        long_term_facts.append(fact)
        if len(long_term_facts) > MAX_FACTS:
            long_term_facts.pop(0)
        save_history()
        print(f"Remembered: {fact}")


def get_facts_context() -> str:
    """Format facts for inclusion in system prompt."""
    if not long_term_facts:
        return ""
    facts_text = "\n".join(f"- {f}" for f in long_term_facts)
    return f"\n\nImportant things to remember about {USER_NAME}:\n{facts_text}"


# ─────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────
connected_clients = set()
current_mode = "idle"
conversation_history, long_term_facts = load_history()
start_time = datetime.now()
whisper_model = None
message_queue = queue.Queue()
briefing_time = "08:00"
face = None

fun_facts_list = [
    "Did you know honey never spoils?",
    "Did you know octopuses have three hearts?",
    "Did you know a day on Venus is longer than its year?",
    "Did you know bananas are berries, but strawberries aren't?",
    "Did you know your nose can detect over a trillion scents?",
    "Did you know sharks existed before trees?",
    "Did you know there are more stars than grains of sand on Earth?",
]

# ─────────────────────────────────────────
#  TTS — edge-tts neural voice (pyttsx3 fallback)
# ─────────────────────────────────────────
_tts_mixer_ready = False


def _ensure_tts_mixer():
    global _tts_mixer_ready
    if not _tts_mixer_ready:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        _tts_mixer_ready = True


async def _edge_tts_to_file(text: str, path: str):
    communicate = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE)
    await communicate.save(path)


def _play_mp3(path: str):
    _ensure_tts_mixer()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(50)


def _speak_edge(text: str):
    path = tempfile.mktemp(suffix=".mp3")
    try:
        asyncio.run(_edge_tts_to_file(text, path))
        _play_mp3(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _speak_pyttsx3(text: str):
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for voice in voices:
        if 'male' in voice.name.lower() or 'david' in voice.name.lower():
            engine.setProperty('voice', voice.id)
            break
    engine.setProperty('rate', 165)
    engine.setProperty('volume', 1.0)
    engine.say(text)
    engine.runAndWait()
    engine.stop()
    del engine


def speak(text: str):
    global current_mode
    try:
        clean = strip_roleplay(text)
        clean = clean.encode('ascii', 'ignore').decode('ascii')
        if not clean.strip():
            return
        print(f"Speaking: {clean}")
        if face:
            face.set_state('speaking')
        try:
            _speak_edge(clean)
        except Exception as e:
            print(f"edge-tts failed ({e}), falling back to pyttsx3")
            _speak_pyttsx3(clean)
        if face:
            face.set_state('idle')
        current_mode = "idle"
    except Exception as e:
        print(f"TTS error: {e}")
        if face:
            face.set_state('idle')
        current_mode = "idle"


# ─────────────────────────────────────────
#  STT — Whisper
# ─────────────────────────────────────────
def load_whisper():
    global whisper_model
    print("Loading Whisper model...")
    whisper_model = whisper.load_model(WHISPER_MODEL, device="cpu")
    print("Whisper ready!")


def record_audio(duration: int = 5, sample_rate: int = 16000) -> np.ndarray:
    print(f"Recording for {duration} seconds... Speak now!")
    if face:
        face.set_state('listening')
    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype='float32'
    )
    sd.wait()
    print("Recording done!")
    return audio.flatten()


def transcribe(audio: np.ndarray) -> str:
    try:
        if face:
            face.set_state('thinking')
        result = whisper_model.transcribe(audio, language='en')
        text = result['text'].strip()
        print(f"Transcribed: {text}")
        return text
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""


# ─────────────────────────────────────────
#  LLM — multi-provider (Groq / Claude / Gemini)
# ─────────────────────────────────────────
def ask_llm(user_message: str) -> str:
    if face:
        face.set_state('thinking')

    dynamic_prompt = SYSTEM_PROMPT + get_facts_context()
    messages = [{"role": "system", "content": dynamic_prompt}]
    messages += conversation_history[-10:]
    messages.append({"role": "user", "content": user_message})

    try:
        if AI_PROVIDER == "groq":
            return ask_groq(messages)
        elif AI_PROVIDER == "claude":
            return ask_claude(messages)
        elif AI_PROVIDER == "gemini":
            return ask_gemini(messages)
        else:
            return ask_groq(messages)
    except Exception as e:
        print(f"LLM error: {e}")
        if face:
            face.set_state('confused')
        return "Sorry something went wrong!"


def ask_groq(messages: list, max_tokens: int = 250) -> str:
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        },
        timeout=15
    )
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"].strip()
    return "Groq had an issue, try again!"


def ask_claude(messages: list) -> str:
    if ANTHROPIC_API_KEY.startswith("YOUR_"):
        return "Claude is not configured yet. Switch to Groq or Gemini in Settings."

    system_msg = messages[0]["content"]
    chat_messages = messages[1:]

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5",
            "max_tokens": 250,
            "system": system_msg,
            "messages": chat_messages,
        },
        timeout=15
    )
    if response.status_code == 200:
        return response.json()["content"][0]["text"].strip()
    return "Claude had an issue, try again!"


def ask_gemini(messages: list) -> str:
    system_msg = messages[0]["content"]
    history = messages[1:-1]
    user_msg = messages[-1]["content"]

    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_msg}]})

    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        f"?key={GEMINI_API_KEY}",
        json={
            "systemInstruction": {"parts": [{"text": system_msg}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.85,
                "maxOutputTokens": 250,
            },
        },
        timeout=15,
    )
    if response.status_code == 200:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    print(f"Gemini error {response.status_code}: {response.text[:300]}")
    if response.status_code == 403:
        return "Gemini API not enabled. Enable Generative Language API in Google Cloud Console."
    return "Gemini had an issue, try again!"


# ─────────────────────────────────────────
#  NOTIFICATION SUMMARY — app + heading, spoken by Jarvis
# ─────────────────────────────────────────
APP_FRIENDLY_NAMES = {
    "com.whatsapp": "WhatsApp",
    "com.whatsapp.w4b": "WhatsApp Business",
    "org.telegram.messenger": "Telegram",
    "com.google.android.gm": "Gmail",
    "com.instagram.android": "Instagram",
    "com.facebook.orca": "Messenger",
    "com.slack": "Slack",
    "com.discord": "Discord",
    "com.twitter.android": "X",
    "com.spotify.music": "Spotify",
    "com.android.mms": "Messages",
    "sms": "SMS",
}

NOTIFICATION_LLM_PROMPT = """You announce phone notifications out loud for someone at their desk.
Always mention which app sent it and the heading/sender name.
If there is message text, hint at the topic in a few words — do NOT read the full message.
One short casual sentence. Max 25 words. No asterisks."""


def normalize_app_name(app: str) -> str:
    if not app:
        return "Unknown app"
    key = app.lower().strip()
    if key in APP_FRIENDLY_NAMES:
        return APP_FRIENDLY_NAMES[key]
    for pkg, name in APP_FRIENDLY_NAMES.items():
        if pkg in key or name.lower() in key:
            return name
    if "." in app:
        segment = app.split(".")[-1]
        if segment not in ("android", "com", "app", "mobile"):
            return segment.replace("_", " ").title()
    return app if len(app) <= 24 else app[:24]


def build_notification_summary_rule(app: str, sender: str, body: str) -> str:
    app_name = normalize_app_name(app)
    heading = (sender or "Someone").strip()
    if body and body.strip():
        preview = body.strip()
        if len(preview) > 80:
            preview = preview[:77] + "..."
        return f"You got a {app_name} notification — {heading}: {preview}"
    return f"You got a {app_name} notification from {heading}."


def summarize_notification(app: str, sender: str, body: str) -> str:
    app_name = normalize_app_name(app)
    heading = (sender or "Someone").strip()
    body_text = (body or "").strip()[:200]
    rule = build_notification_summary_rule(app, sender, body)

    messages = [
        {"role": "system", "content": NOTIFICATION_LLM_PROMPT},
        {
            "role": "user",
            "content": f"App: {app_name}\nHeading: {heading}\nMessage: {body_text or '(empty)'}",
        },
    ]

    try:
        if AI_PROVIDER == "gemini":
            reply = ask_gemini(messages)
        elif AI_PROVIDER == "claude":
            reply = ask_claude(messages)
        else:
            reply = ask_groq(messages, max_tokens=80)

        reply = strip_roleplay(reply).strip()
        bad = ("try again", "not configured", "API not enabled", "had an issue")
        if reply and len(reply) > 8 and not any(b in reply.lower() for b in bad):
            return reply
    except Exception as e:
        print(f"Notification LLM error: {e}")

    return rule


async def announce_notification(notif: dict):
    """Analyze notification with AI, broadcast to app, speak summary."""
    global current_mode

    app = notif.get("app", "Unknown")
    sender = notif.get("sender", "Unknown")
    body = notif.get("body", "")

    if face:
        face.set_state("thinking")
    current_mode = "thinking"

    loop = asyncio.get_event_loop()
    summary = await loop.run_in_executor(None, summarize_notification, app, sender, body)
    summary = strip_roleplay(summary)

    payload = json.dumps({
        "type": "notification",
        "app": app,
        "sender": sender,
        "body": body,
        "summary": summary,
    })

    for client in connected_clients.copy():
        try:
            await client.send(payload)
        except Exception:
            pass

    print(f"Notification: {summary}")
    if face:
        face.set_state("speaking")
    current_mode = "speaking"
    await loop.run_in_executor(None, speak, summary)


# ─────────────────────────────────────────
#  SYSTEM STATS
# ─────────────────────────────────────────
def get_llm_display_name() -> str:
    if AI_PROVIDER == "groq":
        return "Llama 3.3 70B"
    if AI_PROVIDER == "gemini":
        return "Gemini Flash"
    if AI_PROVIDER == "claude":
        return "Claude Haiku"
    return AI_PROVIDER


def get_stats() -> dict:
    uptime_seconds = (datetime.now() - start_time).seconds
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    return {
        "type": "stats",
        "cpu": round(psutil.cpu_percent(interval=0.1)),
        "ram": round(psutil.virtual_memory().percent),
        "uptime": uptime_str,
        "mode": current_mode,
        "llm_model": get_llm_display_name(),
    }


# ─────────────────────────────────────────
#  SPOTIFY PLAY DETECTION (app executes via WebSocket)
# ─────────────────────────────────────────
async def send_spotify_play(query: str):
    for client in connected_clients.copy():
        try:
            await client.send(json.dumps({"type": "spotify_play", "query": query}))
        except Exception:
            pass


def extract_remember_fact(text: str) -> str | None:
    match = re.match(r"^remember\s+(?:that\s+)?(.+)$", text.strip(), re.IGNORECASE)
    if not match:
        return None
    fact = match.group(1).strip()
    fact = re.sub(r"[.!?]+$", "", fact)
    if not fact or len(fact) < 2:
        return None
    return fact[0].upper() + fact[1:]


def detect_spotify_play(text: str) -> str | None:
    lowered = text.lower().strip()
    vague = {
        "music", "something", "a song", "songs", "some music", "spotify",
        "songs from spotify", "on spotify", "from spotify", "something on spotify",
    }
    patterns = [
        r"(?:can you |could you |please )?play\s+(.+)",
        r"put on\s+(.+)",
        r"start\s+playing\s+(.+)",
        r"listen to\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        query = match.group(1).strip()
        query = re.sub(r"[.!?]+$", "", query)
        query = re.sub(r"\s+on spotify$", "", query)
        query = re.sub(r"\s+please$", "", query)
        query = re.sub(r"^some\s+", "", query)
        if query and query not in vague and len(query) > 2:
            return query
    return None


# ─────────────────────────────────────────
#  WEATHER + NEWS (real APIs for briefing)
# ─────────────────────────────────────────
def fetch_weather_text() -> str:
    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": WEATHER_CITY, "appid": WEATHER_API_KEY, "units": "metric"},
            timeout=10,
        )
        if response.status_code != 200:
            print(f"Weather API error: {response.status_code}")
            return "Weather's unavailable right now."
        data = response.json()
        temp = round(data["main"]["temp"])
        city = data.get("name", WEATHER_CITY)
        condition = data["weather"][0]["description"]
        return f"It's {temp} degrees in {city}, {condition}."
    except Exception as e:
        print(f"Weather fetch error: {e}")
        return "Weather's unavailable right now."


def fetch_news_from_rss(limit: int = 3) -> list[str]:
    """Free fallback — NewsAPI blocks many server IPs on the free plan."""
    feeds = [
        "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
        "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
    ]
    headers = {"User-Agent": "JarvisAssistant/1.0"}
    for url in feeds:
        try:
            response = requests.get(url, timeout=10, headers=headers)
            if response.status_code != 200:
                continue
            root = ET.fromstring(response.content)
            titles = []
            for item in root.iter("item"):
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()
                    if title and title not in titles:
                        titles.append(title)
                if len(titles) >= limit:
                    break
            if titles:
                print(f"News loaded from RSS ({len(titles)} headlines)")
                return titles[:limit]
        except Exception as e:
            print(f"RSS news error: {e}")
    return []


def fetch_top_news_titles(limit: int = 3) -> list[str]:
    try:
        response = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"country": NEWS_COUNTRY, "pageSize": limit, "apiKey": NEWS_API_KEY},
            timeout=10,
        )
        if response.status_code == 200:
            articles = response.json().get("articles", [])
            titles = [a["title"] for a in articles if a.get("title")]
            if titles:
                return titles[:limit]
        print(f"News API error: {response.status_code} {response.text[:200]}")
    except Exception as e:
        print(f"News API error: {e}")

    return fetch_news_from_rss(limit)


def get_time_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def build_news_briefing() -> str:
    headlines = fetch_top_news_titles(3)
    if not headlines:
        return "I couldn't pull headlines right now. Try the Briefing button on your phone."
    parts = ". ".join(headlines)
    return f"Here are today's top headlines. {parts}."


def build_morning_briefing() -> str:
    greeting = get_time_greeting()
    weather = fetch_weather_text()
    headlines = fetch_top_news_titles(3)

    text = f"{greeting} {USER_NAME}! {weather}"
    if headlines:
        text += " Top headlines: " + ". ".join(headlines) + "."
    else:
        text += " I couldn't fetch news headlines just now."
    return text


def detect_briefing_request(text: str) -> bool:
    lowered = text.lower()
    phrases = [
        "morning briefing", "daily briefing", "give me briefing", "give me my briefing",
        "my briefing", "briefing please", "start briefing", "run briefing",
    ]
    return any(p in lowered for p in phrases)


def detect_news_request(text: str) -> bool:
    lowered = text.lower().strip()
    if lowered in ("news", "headlines", "top news", "latest news", "the news"):
        return True
    if any(p in lowered for p in ("give me news", "tell me news", "what's the news", "whats the news")):
        return True
    if lowered in ("yes", "yeah", "yep", "sure", "go ahead", "please", "ok", "okay"):
        for msg in reversed(conversation_history[-4:]):
            if msg.get("role") == "assistant":
                content = msg.get("content", "").lower()
                return "news" in content or "headlines" in content or "briefing" in content
        return False
    return False


async def resolve_user_message(text: str, websocket) -> str:
    lowered = text.lower()

    remember_fact = extract_remember_fact(text)
    if remember_fact:
        add_fact(remember_fact)
        return f"Got it — I'll remember that."

    if "fun fact" in lowered or "tell me a fact" in lowered:
        import random
        return random.choice(fun_facts_list)

    if "find my phone" in lowered or "where's my phone" in lowered or "where is my phone" in lowered:
        await websocket.send(json.dumps({"type": "find_phone"}))
        return "Ringing your phone now!"

    if detect_briefing_request(text):
        return build_morning_briefing()

    if detect_news_request(text):
        return build_news_briefing()

    play_query = detect_spotify_play(text)
    if play_query:
        await send_spotify_play(play_query)
        return f"On it — playing {play_query} on Spotify."

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ask_llm, text)


def strip_roleplay(text: str) -> str:
    cleaned = re.sub(r"\*[^*]*\*", "", text).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned if cleaned else text


# ─────────────────────────────────────────
#  WEBSOCKET HANDLERS
# ─────────────────────────────────────────
async def send_stats_loop(websocket):
    while True:
        try:
            await asyncio.sleep(3)
            await websocket.send(json.dumps(get_stats()))
        except websockets.exceptions.ConnectionClosed:
            break


async def handle_message(websocket, message: str):
    global current_mode, AI_PROVIDER, briefing_time

    try:
        data = json.loads(message)
        msg_type = data.get("type")

        # ── Chat ──
        if msg_type == "chat":
            text = data.get("text", "")
            print(f"\nUser: {text}")

            current_mode = "thinking"
            if face:
                face.set_state('thinking')
            await websocket.send(json.dumps({"type": "mode", "mode": "thinking"}))

            add_to_history("user", text)

            loop = asyncio.get_event_loop()

            response = await resolve_user_message(text, websocket)
            response = strip_roleplay(response)

            print(f"Jarvis: {response}")
            add_to_history("assistant", response)

            current_mode = "speaking"
            if face:
                face.set_state('speaking')
            await websocket.send(json.dumps({"type": "response", "text": response}))

            loop.run_in_executor(None, speak, response)
            current_mode = "idle"

        # ── Voice ──
        elif msg_type == "voice":
            current_mode = "listening"
            if face:
                face.set_state('listening')
            await websocket.send(json.dumps({"type": "mode", "mode": "listening"}))

            loop = asyncio.get_event_loop()
            audio = await loop.run_in_executor(None, record_audio, 5)
            text = await loop.run_in_executor(None, transcribe, audio)

            if text:
                await websocket.send(json.dumps({"type": "transcription", "text": text}))

                current_mode = "thinking"
                if face:
                    face.set_state('thinking')
                add_to_history("user", text)

                response = await resolve_user_message(text, websocket)
                response = strip_roleplay(response)
                add_to_history("assistant", response)

                current_mode = "speaking"
                if face:
                    face.set_state('speaking')
                await websocket.send(json.dumps({"type": "response", "text": response}))

                loop.run_in_executor(None, speak, response)
                current_mode = "idle"
                if face:
                    face.set_state('idle')
            else:
                if face:
                    face.set_state('confused')
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": "Sorry I didn't catch that. Try again!"
                }))
                current_mode = "idle"
                if face:
                    face.set_state('idle')

        # ── Clear memory ──
        elif msg_type == "clear_memory":
            conversation_history.clear()
            save_history()
            await websocket.send(json.dumps({
                "type": "response",
                "text": "Memory cleared! Starting fresh."
            }))

        # ── Facts management ──
        elif msg_type == "get_facts":
            await websocket.send(json.dumps({
                "type": "facts_list",
                "facts": long_term_facts
            }))

        elif msg_type == "delete_fact":
            index = data.get("index")
            if index is not None and 0 <= index < len(long_term_facts):
                long_term_facts.pop(index)
                save_history()

        elif msg_type == "get_history":
            await websocket.send(json.dumps({
                "type": "history_list",
                "messages": conversation_history,
            }))

        elif msg_type == "set_briefing_time":
            briefing_time = data.get("time", briefing_time)
            print(f"Briefing time set to: {briefing_time}")
            await websocket.send(json.dumps({
                "type": "response",
                "text": f"Morning briefing set for {briefing_time}.",
            }))

        # ── AI provider switching ──
        elif msg_type == "set_ai_provider":
            AI_PROVIDER = data.get("provider", "groq")
            print(f"AI Provider switched to: {AI_PROVIDER}")

        # ── Commands ──
        elif msg_type == "command":
            action = data.get("action")
            print(f"Command: {action}")

            if action == "restart":
                if face:
                    face.set_state('confused')
                await websocket.send(json.dumps({"type": "response", "text": "Restarting now!"}))

            elif action == "sleep":
                current_mode = "idle"
                if face:
                    face.set_state('idle')
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": "Going to sleep. Wake me from the app!"
                }))

            elif action == "wake":
                if face:
                    face.set_state('idle')
                await websocket.send(json.dumps({
                    "type": "response",
                    "text": f"Good to see you {USER_NAME}!"
                }))

            elif action == "mute":
                await websocket.send(json.dumps({"type": "response", "text": "Microphone muted!"}))

        # ── Register PC daemon ──
        elif msg_type == "register":
            client_type = data.get("client")
            print(f"Registered: {client_type}")

        # ── PC Stats from daemon ──
        elif msg_type == "pc_stats":
            for client in connected_clients.copy():
                try:
                    await client.send(json.dumps({
                        "type": "pc_stats",
                        "git": data.get("git", {}),
                        "window": data.get("window", ""),
                    }))
                except Exception:
                    pass

        # ── App launching (PC remote control) ──
        elif msg_type == "launch_app":
            app_name = data.get("app", "")
            result = launch_app(app_name)
            if face:
                face.set_state('speaking')
            await websocket.send(json.dumps({"type": "response", "text": result}))
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, speak, result)

        elif msg_type == "get_apps":
            await websocket.send(json.dumps({
                "type": "apps_list",
                "apps": list(APP_REGISTRY.keys())
            }))

        # ── Sensor data from ESP32 ──
        elif msg_type == "sensor_data":
            temp = data.get("temperature")
            humidity = data.get("humidity")
            presence = data.get("presence")

            for client in connected_clients.copy():
                try:
                    await client.send(json.dumps({
                        "type": "sensor_data",
                        "temperature": temp,
                        "humidity": humidity,
                        "presence": presence
                    }))
                except Exception:
                    pass

        # ── Music face sync (Spotify beats from app) ──
        elif msg_type == "music_sync":
            playing = data.get("playing", False)
            if playing:
                if current_mode in ("thinking", "listening", "speaking"):
                    pass
                else:
                    tempo = int(data.get("tempo", 120))
                    tempo = max(60, min(tempo, 200))
                    current_mode = "music"
                    if face:
                        face.set_state(f"music_{tempo}")
            elif current_mode == "music":
                current_mode = "idle"
                if face:
                    face.set_state("idle")

        # ── Phone notification relay (from app or test) ──
        elif msg_type in ("phone_notification", "test_notification"):
            if msg_type == "test_notification":
                notif = {
                    "app": "WhatsApp",
                    "sender": "John",
                    "body": "Hey bro are you coming tonight?",
                }
            else:
                notif = {
                    "app": data.get("app", "Unknown"),
                    "sender": data.get("sender", "Unknown"),
                    "body": data.get("body", ""),
                }
            asyncio.create_task(announce_notification(notif))

    except json.JSONDecodeError:
        print("Invalid JSON")
    except Exception as e:
        print(f"Handler error: {e}")


# ─────────────────────────────────────────
#  APP LAUNCHER — PC Remote Control
# ─────────────────────────────────────────
import subprocess as sp

APP_REGISTRY = {
    "spotify": r"C:\Users\user\AppData\Roaming\Spotify\Spotify.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "vscode": r"C:\Users\user\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "steam": r"C:\Program Files (x86)\Steam\steam.exe",
    "discord": r"C:\Users\user\AppData\Local\Discord\Update.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
}


def launch_app(app_name: str) -> str:
    app_key = app_name.lower().strip()
    if app_key not in APP_REGISTRY:
        available = ", ".join(APP_REGISTRY.keys())
        return f"App '{app_name}' not found. Available: {available}"
    try:
        path = APP_REGISTRY[app_key]
        sp.Popen(path, shell=True)
        return f"Opening {app_name}!"
    except Exception as e:
        print(f"Launch error: {e}")
        return f"Couldn't open {app_name}. Check if it's installed."


# ─────────────────────────────────────────
#  CONNECTION HANDLER
# ─────────────────────────────────────────
async def handler(websocket):
    print(f"\nApp connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    if face:
        face.set_state('idle')

    await websocket.send(json.dumps({
        "type": "response",
        "text": f"Hey {USER_NAME}! Jarvis is online and ready."
    }))

    stats_task = asyncio.create_task(send_stats_loop(websocket))

    try:
        async for message in websocket:
            await handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        print("App disconnected")
    finally:
        connected_clients.discard(websocket)
        stats_task.cancel()


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
async def main():
    global face

    print("=" * 40)
    print("  JARVIS WINDOWS SERVER")
    print("=" * 40)

    load_whisper()

    os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
    print("Starting Jarvis face...")
    face = create_face_controller() if FACE_AVAILABLE else None

    import socket
    local_ip = socket.gethostbyname(socket.gethostname())

    try:
        tailscale_result = sp.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, timeout=5)
        tailscale_ip = tailscale_result.stdout.strip()
    except Exception:
        tailscale_ip = "Not available (Tailscale not running?)"

    print(f"\nLocal IP: {local_ip}")
    print(f"Tailscale IP: {tailscale_ip}")
    print("Use Tailscale IP in the app for remote access from anywhere!")
    print("=" * 40)

    async with websockets.serve(handler, WEBSOCKET_HOST, WEBSOCKET_PORT):
        print("\nJarvis is ready! Waiting for app connection...")
        await asyncio.Future()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nJarvis shutting down...")
        sys.exit(0)
