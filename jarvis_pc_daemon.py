import asyncio
import websockets
import json
import subprocess
import os
import psutil
import time
from pathlib import Path

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
JARVIS_SERVER_IP   = "localhost"
JARVIS_SERVER_PORT = 8765
WATCH_PATH = "D:\\Project" # your main dev folder

# ─────────────────────────────────────────
#  GIT HELPERS
# ─────────────────────────────────────────
def get_git_status(path: str) -> dict:
    """Get git status for a repo."""
    try:
        # Current branch
        branch = subprocess.check_output(
            ['git', 'branch', '--show-current'],
            cwd=path, stderr=subprocess.DEVNULL
        ).decode().strip()

        # Last commit
        commit = subprocess.check_output(
            ['git', 'log', '-1', '--pretty=%s'],
            cwd=path, stderr=subprocess.DEVNULL
        ).decode().strip()

        # Changed files count
        status = subprocess.check_output(
            ['git', 'status', '--porcelain'],
            cwd=path, stderr=subprocess.DEVNULL
        ).decode().strip()

        changed = len(status.splitlines()) if status else 0

        return {
            'branch':  branch,
            'commit':  commit,
            'changed': changed,
            'path':    path,
        }
    except Exception:
        return {}


def get_active_window() -> str:
    """Get currently active window title on Windows."""
    try:
        import ctypes
        hwnd   = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf    = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return 'Unknown'


def run_git_command(command: str, path: str) -> str:
    """Run a git command and return output."""
    try:
        cmd_map = {
            'status': ['git', 'status', '--short'],
            'pull':   ['git', 'pull'],
            'push':   ['git', 'push'],
            'log':    ['git', 'log', '--oneline', '-5'],
        }

        if command not in cmd_map:
            return f"Unknown command: {command}"

        output = subprocess.check_output(
            cmd_map[command],
            cwd=path,
            stderr=subprocess.STDOUT
        ).decode().strip()

        return output if output else "Done!"
    except subprocess.CalledProcessError as e:
        return f"Error: {e.output.decode()}"
    except Exception as e:
        return f"Error: {str(e)}"


# ─────────────────────────────────────────
#  SYSTEM INFO
# ─────────────────────────────────────────
def get_pc_stats() -> dict:
    """Get PC system stats."""
    return {
        'cpu':    round(psutil.cpu_percent(interval=0.1)),
        'ram':    round(psutil.virtual_memory().percent),
        'window': get_active_window(),
    }


# ─────────────────────────────────────────
#  DAEMON
# ─────────────────────────────────────────
async def daemon():
    """Main daemon loop — connects to Jarvis server."""
    print("Jarvis PC Daemon starting...")
    print(f"Connecting to Jarvis at {JARVIS_SERVER_IP}:{JARVIS_SERVER_PORT}")

    while True:
        try:
            async with websockets.connect(
                f"ws://{JARVIS_SERVER_IP}:{JARVIS_SERVER_PORT}"
            ) as websocket:
                print("Connected to Jarvis server!")

                # Register as PC daemon
                await websocket.send(json.dumps({
                    "type":   "register",
                    "client": "pc_daemon"
                }))

                # Send stats loop
                async def send_stats():
                    while True:
                        try:
                            git    = get_git_status(WATCH_PATH)
                            stats  = get_pc_stats()
                            await websocket.send(json.dumps({
                                "type":   "pc_stats",
                                "git":    git,
                                "window": stats['window'],
                                "cpu":    stats['cpu'],
                                "ram":    stats['ram'],
                            }))
                            await asyncio.sleep(5)
                        except websockets.exceptions.ConnectionClosed:
                            break

                stats_task = asyncio.create_task(send_stats())

                # Handle commands from Jarvis
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        if data.get('type') == 'git_command':
                            command = data.get('command')
                            path    = data.get('path', WATCH_PATH)
                            output  = run_git_command(command, path)
                            await websocket.send(json.dumps({
                                "type":   "git_result",
                                "output": output,
                            }))
                    except Exception as e:
                        print(f"Command error: {e}")

                stats_task.cancel()

        except Exception as e:
            print(f"Connection error: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(daemon())
    except KeyboardInterrupt:
        print("Daemon stopped.")