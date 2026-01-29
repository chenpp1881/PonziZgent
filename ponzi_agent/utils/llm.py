
# -*- coding: utf-8 -*-
import os, json, requests

class LLMClient:
    def __init__(self, api_key: str, base_url: str = None, model: str = None, timeout: int = 120):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY","").strip()
        if not self.api_key:
            raise RuntimeError("Please provide API key or set OPENAI_API_KEY.")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout = timeout

    def chat_json(self, system: str, user: str, temperature: float = 0.1) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role":"system", "content": system},
                {"role":"user", "content": user}
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
