"""Wrapper for hosts (Hugging Face Spaces) that require an HTTP health port.

Starts a tiny health server in a background thread, then runs the LiveKit agent.
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"agent worker running\n")

    def log_message(self, *_):
        pass


def _start_health_server():
    port = int(os.getenv("PORT", "7860"))
    server = HTTPServer(("0.0.0.0", port), _Health)
    print(f"[worker_runner] health server listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=_start_health_server, daemon=True).start()
    # Default to "start" mode if no LiveKit subcommand is provided.
    if len(sys.argv) == 1:
        sys.argv.append("start")
    import voice_agent_openai  # noqa  - triggers cli.run_app via __main__ guard
    # voice_agent_openai's __main__ block won't execute on import; call it manually.
    from voice_agent_openai import entrypoint, prewarm
    from livekit.agents import WorkerOptions, cli
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
