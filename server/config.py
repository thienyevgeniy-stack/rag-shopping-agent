from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str = "development"
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "ep-20260514111645-lmgt2"

    use_chroma: bool = False
    chroma_dir: str = "server/chroma_db"
    product_data_path: str = "data/products_ref.json"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def product_data_file(self) -> Path:
        path = Path(self.product_data_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def chroma_path(self) -> Path:
        path = Path(self.chroma_dir)
        return path if path.is_absolute() else ROOT_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
