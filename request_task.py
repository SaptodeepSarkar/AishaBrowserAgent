#!/usr/bin/env python3
"""
External task requester for AISha Browser Agent.
Sends a prompt to the headless agent API and prints the result.
"""

import json
import sys
import urllib.request
import urllib.error

def main():
    if len(sys.argv) < 2:
        print("Usage: python request_task.py <prompt> [chat_id]")
        print("Example: python request_task.py 'Search YouTube for lo-fi music'")
        sys.exit(1)

    prompt = sys.argv[1]
    chat_id = sys.argv[2] if len(sys.argv) > 2 else None

    url = "http://localhost:8763/api/query"
    data = {
        "prompt": prompt,
    }
    if chat_id:
        data["chat_id"] = chat_id

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("Answer:", result.get("answer"))
            print("Chat ID:", result.get("chat_id"))
            print("Steps taken:", result.get("steps_taken"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()