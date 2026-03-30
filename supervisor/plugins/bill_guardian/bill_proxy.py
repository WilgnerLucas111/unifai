#!/usr/bin/env python3
"""
UnifAI Bill Guardian (The Gauge Proxy)
Minimalist zero-dependency HTTP proxy to throttle Anthropic API tokens.
Intercepts requests, checks a local budget, and cuts fuel returning HTTP 429 if exceeded.
Adheres strictly to the "execute, não enfeite" rule.
"""

import os
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import urllib.error

# Keep it strictly stealth and minimal.
BUDGET_FILE = "/tmp/unifai_budget.json"
DEFAULT_BUDGET = 1000  # Default total tokens allowed
PROXY_PORT = 7701
ANTHROPIC_REAL_URL = "https://api.anthropic.com"

logging.basicConfig(level=logging.INFO, format="[BILL PROXY] %(message)s")

def get_budget():
    """Reads current budget. If not existent, initializes it."""
    if not os.path.exists(BUDGET_FILE):
        set_budget(DEFAULT_BUDGET)
    try:
        with open(BUDGET_FILE, "r") as f:
            data = json.load(f)
            return data.get("budget", 0)
    except Exception:
        return 0

def set_budget(tokens):
    """Synchronously writes the new budget to the tracker."""
    with open(BUDGET_FILE, "w") as f:
        json.dump({"budget": tokens}, f)

class BillProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 1. Gauge Check (The Fuel)
        current_budget = get_budget()
        if current_budget <= 0:
            logging.warning("FUEL CUT: Budget exceeded. Striking OpenClaw with 429.")
            self.send_response(429)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": {"type": "rate_limit_error", "message": "UnifAI Budget Exceeded"}}')
            return

        # 2. Extract agent payload
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        # 3. Rebuild headers for the real Anthropic Matrix
        req_headers = {}
        for key, value in self.headers.items():
            if key.lower() not in ['host', 'connection', 'content-length']:
                req_headers[key] = value

        # 4. Proxy the request to the real world
        target_url = f"{ANTHROPIC_REAL_URL}{self.path}"
        req = urllib.request.Request(target_url, data=post_data, headers=req_headers, method="POST")

        try:
            with urllib.request.urlopen(req) as response:
                response_body = response.read()
                status = response.status
                response_headers = response.headers
        except urllib.error.HTTPError as e:
            response_body = e.read()
            status = e.code
            response_headers = e.headers

        # 5. Intercept usage from Anthropic's response body
        # Anthropic standard JSON contains {"usage": {"input_tokens": x, "output_tokens": y}}
        cost = 0
        if status == 200:
            try:
                body_json = json.loads(response_body)
                if "usage" in body_json:
                    cost = body_json["usage"].get("input_tokens", 0) + body_json["usage"].get("output_tokens", 0)
            except Exception:
                pass

        # 6. Debit fuel and return payload to Agent
        if cost > 0:
            new_budget = current_budget - cost
            set_budget(new_budget)
            logging.info(f"Consumed {cost} tokens. Remaining Fuel: {new_budget}")

        self.send_response(status)
        for key, value in response_headers.items():
            if key.lower() not in ['transfer-encoding', 'connection']: # Clean hop-by-hop headers
                self.send_header(key, value)
        self.send_header('Content-Length', str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format, *args):
        # Silence default BaseHTTPRequestHandler logging to avoid stdout leaks
        pass

if __name__ == "__main__":
    logging.info(f"Starting unseen UnifAI Bill Proxy on port {PROXY_PORT}...")
    # Reset budget on proxy start for testing purposes
    set_budget(DEFAULT_BUDGET)
    server = HTTPServer(('127.0.0.1', PROXY_PORT), BillProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down Bill Proxy.")

