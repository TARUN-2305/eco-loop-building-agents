import requests
import json

url = "http://localhost:11434/v1/chat/completions"
payload = {
    "model": "gemma4:e2b",
    "messages": [
        {"role": "system", "content": "You are a JSON generator. You must respond with valid JSON only."},
        {"role": "user", "content": "Generate JSON with keys 'thought' and 'tool_call'."}
    ],
    "response_format": {"type": "json_object"}
}

resp = requests.post(url, json=payload, timeout=30)
print("Status:", resp.status_code)
print("Content:", resp.json()["choices"][0]["message"]["content"])
