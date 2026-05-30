from server.config import get_settings
from server.rag.vector_store import ChromaStore, load_product_documents


def main() -> None:
    settings = get_settings()
    documents = load_product_documents(settings.product_data_file)
    store = ChromaStore(settings.chroma_path)
    store.add(documents)
    print(f"Ingested {len(documents)} product documents into {settings.chroma_path}")
    print(f"Collection count: {store.count()}")


if __name__ == "__main__":
    main()
