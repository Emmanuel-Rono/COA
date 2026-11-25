"""Real local inference, schema-constrained output and embeddings over HTTP."""
import httpx
from pydantic import ValidationError
from .errors import AppError


class LocalModel:
    def __init__(self, settings):
        self.settings = settings

    def _post(self, path, payload):
        try:
            response = httpx.post(self.settings.ollama_url + path, json=payload,
                                  timeout=self.settings.model_timeout, trust_env=False)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise AppError("model_unavailable", "Ollama failed. Check the server and configured local models.", 503)

    def chat(self, messages, schema=None, tools=None):
        payload = {"model": self.settings.model, "messages": messages, "stream": False,
                   "think": False, "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1800}}
        if schema:
            payload["format"] = schema.model_json_schema()
        if tools:
            payload["tools"] = tools
        result = self._post("/api/chat", payload)
        if not isinstance(result.get("message"), dict):
            raise AppError("model_invalid", "Ollama returned no message; review required.")
        return result["message"]

    def structured(self, messages, schema):
        for attempt in range(2):
            message = self.chat(messages, schema=schema)
            try:
                return schema.model_validate_json(message.get("content", ""))
            except (ValidationError, ValueError):
                if attempt:
                    raise AppError("model_invalid", "Model output failed validation after one repair; review required.")
                messages = messages + [{"role": "assistant", "content": message.get("content", "")},
                                       {"role": "user", "content": "Return only valid JSON matching the schema. Do not invent missing facts."}]

    def embed(self, texts, query=False):
        prefix = "search_query: " if query else "search_document: "
        result = self._post("/api/embed", {"model": self.settings.embedding_model,
                            "input": [prefix + text for text in texts], "truncate": False})
        vectors = result.get("embeddings", [])
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise AppError("embedding_invalid", "Embedding response does not match the input.", 503)
        return vectors

    def ready(self):
        try:
            result = httpx.get(self.settings.ollama_url + "/api/tags", timeout=5, trust_env=False)
            result.raise_for_status()
            available = {item["name"] for item in result.json()["models"]}
            return all(name in available for name in (self.settings.model, self.settings.embedding_model))
        except (httpx.HTTPError, KeyError, ValueError):
            return False
