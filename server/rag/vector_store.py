"""Compatibility exports for the RAG vector stack.

The concrete implementations live in narrower modules:
- `types.py` for shared protocols/data classes
- `stores.py` for local JSON and Chroma stores
- `embeddings.py` for embedding providers
- `documents.py` for catalog document loading
- `scoring.py` and `chroma_metadata.py` for retrieval helpers
"""

from server.rag.chroma_metadata import (
    build_chroma_where,
    from_chroma_metadata,
    metadata_matches_vector_filters,
    to_chroma_metadata,
)
from server.rag.documents import load_product_documents
from server.rag.embeddings import (
    ArkEmbeddingFunction,
    ArkMultimodalEmbeddingFunction,
    HashingEmbeddingFunction,
    build_chroma_embedding_function,
    image_data_url,
    parse_embedding_response,
    parse_multimodal_embedding_response,
)
from server.rag.identifiers import (
    bounded_chroma_collection_name,
    category_filter_key,
    product_type_filter_key,
    safe_identifier,
)
from server.rag.scoring import (
    build_document_feature_index,
    build_document_features,
    hashing_embedding,
    score_chroma_hit,
    score_document,
    score_document_features,
    tokenize,
)
from server.rag.stores import ChromaStore, LocalJsonVectorStore, build_product_type_index
from server.rag.types import DocumentFeatures, VectorDocument, VectorSearchFilters, VectorStore


__all__ = [
    "ArkEmbeddingFunction",
    "ArkMultimodalEmbeddingFunction",
    "ChromaStore",
    "DocumentFeatures",
    "HashingEmbeddingFunction",
    "LocalJsonVectorStore",
    "VectorDocument",
    "VectorSearchFilters",
    "VectorStore",
    "bounded_chroma_collection_name",
    "category_filter_key",
    "build_chroma_embedding_function",
    "build_chroma_where",
    "build_document_feature_index",
    "build_document_features",
    "build_product_type_index",
    "from_chroma_metadata",
    "hashing_embedding",
    "image_data_url",
    "load_product_documents",
    "metadata_matches_vector_filters",
    "parse_embedding_response",
    "parse_multimodal_embedding_response",
    "product_type_filter_key",
    "safe_identifier",
    "score_chroma_hit",
    "score_document",
    "score_document_features",
    "to_chroma_metadata",
    "tokenize",
]
