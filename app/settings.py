import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    api_token: str
    mode: str = "fixture"
    store_id: str = "demo-store"
    data_dir: Path = ROOT / "data"
    spree_url: str = "http://localhost:3000"
    spree_key: str = ""
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen3:1.7b"
    embedding_model: str = "nomic-embed-text:latest"
    model_timeout: int = 180
    local_demo_access: bool = True
    order_reference: str = ""

    def __post_init__(self):
        if len(self.api_token) < 16 or self.api_token == "replace-with-a-long-private-token":
            raise ValueError("Set APP_API_TOKEN to a private value of at least 16 characters in .env")
        if self.mode not in {"fixture", "live"}:
            raise ValueError("SPREE_MODE must be fixture or live")
        if self.mode == "live" and not self.spree_key.startswith("sk_"):
            raise ValueError("Live mode requires a read-only Spree secret key (sk_) on the server")
        for url in (self.spree_url, self.ollama_url):
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
                raise ValueError("Service URLs must be origins, without credentials or paths")
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        return cls(api_token=os.getenv("APP_API_TOKEN", ""), mode=os.getenv("SPREE_MODE", "fixture"),
                   store_id=os.getenv("STORE_ID", "demo-store"), data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data"))),
                   spree_url=os.getenv("SPREE_BASE_URL", "http://localhost:3000").rstrip("/"),
                   spree_key=os.getenv("SPREE_API_KEY", ""), ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
                   model=os.getenv("OLLAMA_MODEL", "qwen3:1.7b"), embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest"),
                   local_demo_access=os.getenv("LOCAL_DEMO_ACCESS", "true").lower() == "true",
                   order_reference=os.getenv("DEFAULT_ORDER_REFERENCE", "").strip())
