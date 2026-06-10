from pathlib import Path

from server.inputs.base import ProcessedInput, TextProcessor
from server.inputs.image_similarity import ProductImageSimilarityIndex
from server.inputs.visual_embedding import ProductVisualEmbeddingIndex


class MultimodalInputProcessor:
    def __init__(
        self,
        product_data_path: Path,
        product_image_dir: Path,
        visual_embedding_index: ProductVisualEmbeddingIndex | None = None,
    ) -> None:
        self.text_processor = TextProcessor()
        self.visual_index = ProductImageSimilarityIndex(product_data_path, product_image_dir)
        self.visual_embedding_index = visual_embedding_index

    def process(
        self,
        raw: str,
        image_base64: str = "",
        image_bytes: bytes = b"",
        image_mime_type: str = "",
        image_filename: str = "",
    ) -> ProcessedInput:
        text = raw.strip()
        if not image_base64.strip() and not image_bytes:
            return self.text_processor.process(text)

        matches = self._match_image(
            image_base64,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )
        if not matches:
            fallback = text or "find visually similar products"
            summary = "我看到了你上传的图片，但当前商品库里还没有足够可靠的视觉近邻。我会先结合你补充的文字需求继续找，避免硬说同款。"
            return ProcessedInput(
                text=f"{fallback}\nImage signal: {summary}",
                modality="image",
                image_summary=summary,
                visual_matches=[],
            )

        best = matches[0]
        product_types = ", ".join(best.get("product_type_names", []))
        match_source = best.get("visual_match_source", "signature")
        summary = (
            f"我先按图片做了视觉匹配，当前商品库里最接近的是「{best['name']}」，"
            f"品牌是 {best['brand']}，类目是 {best['category']}"
        )
        if product_types:
            summary += f"，更像是 {product_types}"
        summary += (
            f"。相似度约 {best['similarity']:.2f}，来源是 {format_visual_match_source(match_source)}。"
            "我会优先按这个风格和品类给你推荐，同时不会把它说成百分百同款。"
        )

        user_text = text or "find the same or visually similar product from the image"
        visual_query = (
            f"{user_text}\n"
            f"Image signal: {summary}\n"
            f"Prioritize same or visually similar products: {best['name']} {best['brand']} "
            f"{best['category']} {' '.join(best.get('product_type_names', []))}"
        )
        return ProcessedInput(
            text=visual_query,
            modality="image",
            image_summary=summary,
            visual_matches=matches,
        )

    def _match_image(self, image_base64: str, *, image_bytes: bytes, image_mime_type: str) -> list[dict]:
        if self.visual_embedding_index and self.visual_embedding_index.available:
            if image_bytes:
                matches = self.visual_embedding_index.match_image_bytes(
                    image_bytes,
                    image_mime_type=image_mime_type or "image/jpeg",
                    top_k=3,
                )
            else:
                matches = self.visual_embedding_index.match_base64_image(
                    image_base64,
                    image_mime_type=image_mime_type or "image/jpeg",
                    top_k=3,
                )
            if matches:
                return matches
        if image_bytes:
            return self.visual_index.match_image_bytes(image_bytes, top_k=3)
        return self.visual_index.match_base64_image(image_base64, top_k=3)


def format_visual_match_source(source: str) -> str:
    if source == "multimodal_embedding":
        return "多模态向量"
    return "图片视觉特征"
