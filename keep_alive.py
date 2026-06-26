import requests
import json
import sys
import time

def send_keepalive():
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "gemma4",
        "prompt": "Reply with only the single word: pong",
        "stream": False,
        "options": {
            "think": False
        }
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=100)
        response.raise_for_status()
        result = response.json()
        # The response may contain 'response' field with the model's output
        output = result.get("response", "").strip()
        print(f"Ollama response: {output}")
        # Optionally, check if the output is as expected
        if output.lower() == "pong":
            print("Keep-alive successful: model responded with 'pong'.")
            return True
        else:
            print("Warning: model did not return expected 'pong'.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Ollama: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    print("Starting keep-alive loop (press Ctrl+C to stop)...")
    try:
        while True:
            send_keepalive()
            print("Waiting 2 minutes until next keep-alive...")
            time.sleep(120)  # 2 minutes
    except KeyboardInterrupt:
        print("\nKeep-alive stopped by user.")
        sys.exit(0)