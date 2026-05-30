from server.config import get_settings
from server.rag.vector_store import LocalJsonVectorStore


def main() -> None:
    settings = get_settings()
    store = LocalJsonVectorStore(settings.product_data_file)
    print(f"Loaded {len(store.documents)} product documents from {settings.product_data_file}")


if __name__ == "__main__":
    main()
