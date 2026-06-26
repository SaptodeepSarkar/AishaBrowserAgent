import requests
import json

def test_aisha_api():
    url = "http://localhost:8763/api/query"
    
    # Define a test prompt
    payload = {
        "prompt": "open youtube.com and search for latest tech news",
        "chat_id": None  # Optional: omit to create a new chat
    }

    print(f"🚀 Sending request to AISha: {payload['prompt']}")
    print("⏳ This is a blocking call and may take a few moments...")

    try:
        response = requests.post(url, json=payload, timeout=120)
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ API Response Received:")
            print(f"-----------------------------------")
            print(f"Answer: {data.get('answer')}")
            print(f"Steps Taken: {data.get('steps_taken')}")
            print(f"Chat ID: {data.get('chat_id')}")
            print(f"-----------------------------------")
        else:
            print(f"\n❌ API Error: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection Error: Is the server running on port 8763?")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    test_aisha_api()
