import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent

# Corporate proxies re-sign TLS; use the OS trust store when available.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


def _first(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip().strip('"')
    return default


@dataclass(frozen=True)
class Settings:
    qloo_base_url: str
    qloo_api_key: str
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    openai_fallback_models: tuple
    skills_dir: Path
    data_dir: Path
    qloo_call_budget: int
    qloo_concurrency: int
    allowed_origins: list = field(default_factory=list)

    @property
    def qloo_configured(self) -> bool:
        return bool(self.qloo_base_url and self.qloo_api_key)

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_base_url and self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env", override=False)
    load_dotenv(BACKEND_DIR / ".env", override=False)

    skills_raw = os.environ.get("SKILLS_DIR")
    skills_dir = Path(skills_raw) if skills_raw else PROJECT_DIR / "skills"
    if not skills_dir.is_absolute():
        skills_dir = (BACKEND_DIR / skills_dir).resolve()

    origins = _first("CFST_ALLOWED_ORIGINS", default="http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        qloo_base_url=_first("QLOO_API_URL", "Qloo_Hackathon_API_Server_URL").rstrip("/"),
        qloo_api_key=_first("QLOO_API_KEY", "API_Key"),
        openai_base_url=_first("OPENAI_BASE_URL").rstrip("/"),
        openai_api_key=_first("OPENAI_API_KEY"),
        openai_model=_first("OPENAI_MODEL", default="deepseek.v3.2"),
        openai_fallback_models=("zai.glm-5", "qwen.qwen3-235b-a22b-2507"),
        skills_dir=skills_dir,
        data_dir=Path(os.environ.get("CFST_DATA_DIR", BACKEND_DIR / "data")),
        qloo_call_budget=int(_first("CFST_QLOO_CALL_BUDGET", default="24")),
        qloo_concurrency=int(_first("CFST_QLOO_CONCURRENCY", default="4")),
        allowed_origins=[o.strip() for o in origins.split(",") if o.strip()],
    )
