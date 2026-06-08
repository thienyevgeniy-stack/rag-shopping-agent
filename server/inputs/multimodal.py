from pathlib import Path

from server.inputs.base import ProcessedInput, TextProcessor
from server.inputs.image_similarity import ProductImageSimilarityIndex


class MultimodalInputProcessor:
    def __init__(self, product_data_path: Path, product_image_dir: Path) -> None:
        self.text_processor = TextProcessor()
        self.visual_index = ProductImageSimilarityIndex(product_data_path, product_image_dir)

    def process(
        self,
        raw: str,
        image_base64: str = "",
        image_mime_type: str = "",
        image_filename: str = "",
    ) -> ProcessedInput:
        text = raw.strip()
        if not image_base64.strip():
            return self.text_processor.process(text)

        matches = self.visual_index.match_base64_image(image_base64, top_k=3)
        if not matches:
            fallback = text or "我想找图片里的同款或相似商品"
            summary = "已收到图片，但当前商品库里没有找到足够相似的主图。"
            return ProcessedInput(
                text=f"{fallback}\n图片线索：{summary}",
                modality="image",
                image_summary=summary,
                visual_matches=[],
            )

        best = matches[0]
        product_types = ", ".join(best.get("product_type_names", []))
        summary = (
            f"上传图片最像商品“{best['name']}”，品牌 {best['brand']}，"
            f"类目 {best['category']}"
        )
        if product_types:
            summary += f"，商品类型 {product_types}"
        summary += f"，视觉相似度 {best['similarity']:.2f}。"

        user_text = text or "我想找图片里的同款或相似商品"
        visual_query = (
            f"{user_text}\n"
            f"图片线索：{summary}\n"
            f"优先检索同款或相似商品：{best['name']} {best['brand']} "
            f"{best['category']} {' '.join(best.get('product_type_names', []))}"
        )
        return ProcessedInput(
            text=visual_query,
            modality="image",
            image_summary=summary,
            visual_matches=matches,
        )
