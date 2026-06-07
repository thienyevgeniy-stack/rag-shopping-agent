import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TAXONOMY_PATH = ROOT_DIR / "data" / "product_taxonomy.json"


@dataclass(frozen=True)
class ProductType:
    id: str
    display_name: str
    aliases: tuple[str, ...]
    compound_aliases: tuple[tuple[str, ...], ...]
    match_fields: tuple[str, ...]


@dataclass(frozen=True)
class ProductTypeMatch:
    product_type_id: str
    alias: str


@lru_cache
def load_product_taxonomy(path: str | None = None) -> dict[str, ProductType]:
    taxonomy_path = Path(path) if path else DEFAULT_TAXONOMY_PATH
    payload = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    product_types: dict[str, ProductType] = {}
    for item in payload.get("product_types", []):
        product_type = ProductType(
            id=item["id"],
            display_name=item["display_name"],
            aliases=tuple(item.get("aliases", [])),
            compound_aliases=tuple(tuple(group) for group in item.get("compound_aliases", [])),
            match_fields=tuple(item.get("match_fields", ["name", "sub_category", "tags"])),
        )
        product_types[product_type.id] = product_type
    return product_types


def extract_product_type_matches(message: str) -> list[ProductTypeMatch]:
    matches: list[ProductTypeMatch] = []
    for product_type in load_product_taxonomy().values():
        for alias in sorted(product_type.aliases, key=len, reverse=True):
            if alias and alias in message:
                matches.append(ProductTypeMatch(product_type_id=product_type.id, alias=alias))
                break
        else:
            for group in product_type.compound_aliases:
                if group and all(term in message for term in group):
                    matches.append(ProductTypeMatch(product_type_id=product_type.id, alias="+".join(group)))
                    break
    return matches


def canonicalize_product_type(value: str) -> str:
    value = value.strip()
    product_types = load_product_taxonomy()
    if value in product_types:
        return value
    for product_type in product_types.values():
        if value == product_type.display_name or value in product_type.aliases:
            return product_type.id
        if any(value == "+".join(group) for group in product_type.compound_aliases):
            return product_type.id
    return value


def product_type_matches(value: str, metadata: dict) -> bool:
    canonical = canonicalize_product_type(value)
    return canonical in infer_product_type_ids(metadata)


def infer_product_type_ids(metadata: dict) -> list[str]:
    explicit = explicit_product_type_ids(metadata)
    if explicit:
        return explicit

    matched: list[str] = []
    for product_type in load_product_taxonomy().values():
        haystack = build_match_haystack(metadata, product_type.match_fields)
        if any(alias.lower() in haystack for alias in product_type.aliases) or any(
            all(term.lower() in haystack for term in group)
            for group in product_type.compound_aliases
            if group
        ):
            matched.append(product_type.id)
    return matched


def explicit_product_type_ids(metadata: dict) -> list[str]:
    raw = metadata.get("product_types") or metadata.get("product_type") or []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [str(item) for item in raw]
    else:
        values = []

    product_types = load_product_taxonomy()
    canonical_ids: list[str] = []
    for value in values:
        canonical = canonicalize_product_type(value)
        if canonical in product_types and canonical not in canonical_ids:
            canonical_ids.append(canonical)
    return canonical_ids


def product_type_display_names(product_type_ids: list[str]) -> list[str]:
    product_types = load_product_taxonomy()
    names: list[str] = []
    for value in product_type_ids:
        canonical = canonicalize_product_type(value)
        product_type = product_types.get(canonical)
        if product_type and product_type.display_name not in names:
            names.append(product_type.display_name)
    return names


def enrich_product_type_metadata(metadata: dict) -> dict:
    enriched = dict(metadata)
    product_types = infer_product_type_ids(enriched)
    if product_types:
        enriched["product_types"] = product_types
    return enriched


def build_match_haystack(metadata: dict, fields: tuple[str, ...]) -> str:
    parts: list[str] = []
    for field in fields:
        value = metadata.get(field, "")
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
    return " ".join(parts).lower()
