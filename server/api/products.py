import html
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from server.config import get_settings
from server.tools.product_search import build_product_image_url


router = APIRouter(tags=["products"])


@router.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(product_id: str) -> HTMLResponse:
    product = get_product_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    settings = get_settings()
    image_url = build_product_image_url(product.get("image_url", ""), settings.public_base_url)
    body = render_product_detail(product, image_url)
    return HTMLResponse(content=body)


def get_product_by_id(product_id: str) -> dict | None:
    return load_product_index().get(product_id)


@lru_cache
def load_product_index() -> dict[str, dict]:
    settings = get_settings()
    path: Path = settings.product_data_file
    products = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in products}


def render_product_detail(product: dict, image_url: str) -> str:
    name = escape(product.get("name", ""))
    brand = escape(product.get("brand", ""))
    category = escape(product.get("category", ""))
    sub_category = escape(product.get("sub_category", ""))
    price = escape(str(product.get("price", "")))
    stock = escape(str(product.get("stock", "")))
    description = escape(product.get("description", ""))
    tags = product.get("tags", [])
    attributes = product.get("attributes", {})
    sku_options = attributes.get("sku_options", {}) if isinstance(attributes, dict) else {}

    tag_items = "".join(f"<span>{escape(str(tag))}</span>" for tag in tags[:10])
    sku_items = "".join(
        f"<li><b>{escape(str(key))}</b>: {escape(' / '.join(str(value) for value in values))}</li>"
        for key, values in sku_options.items()
    )
    sku_section = f"<ul>{sku_items}</ul>" if sku_items else "<p>暂无规格信息</p>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name}</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f8;
      color: #182026;
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
      padding: 18px;
    }}
    .hero {{
      background: white;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #e3e6ea;
    }}
    img {{
      width: 100%;
      aspect-ratio: 1.2 / 1;
      object-fit: cover;
      background: #edf0f2;
      display: block;
    }}
    .content {{
      padding: 16px;
    }}
    h1 {{
      font-size: 20px;
      line-height: 1.35;
      margin: 0 0 12px;
    }}
    .price {{
      color: #d23f31;
      font-size: 24px;
      font-weight: 700;
      margin: 8px 0 12px;
    }}
    .meta {{
      color: #65717b;
      font-size: 14px;
      display: grid;
      gap: 6px;
    }}
    section {{
      background: white;
      border: 1px solid #e3e6ea;
      border-radius: 8px;
      margin-top: 12px;
      padding: 16px;
    }}
    h2 {{
      font-size: 16px;
      margin: 0 0 10px;
    }}
    p, li {{
      font-size: 14px;
      line-height: 1.65;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .tags span {{
      background: #eef3ff;
      color: #254a8f;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <main>
    <article class="hero">
      <img src="{escape(image_url)}" alt="{name}" />
      <div class="content">
        <h1>{name}</h1>
        <div class="price">¥{price}</div>
        <div class="meta">
          <div>品牌：{brand}</div>
          <div>类目：{category} / {sub_category}</div>
          <div>库存：{stock}</div>
        </div>
      </div>
    </article>
    <section>
      <h2>商品标签</h2>
      <div class="tags">{tag_items}</div>
    </section>
    <section>
      <h2>规格信息</h2>
      {sku_section}
    </section>
    <section>
      <h2>商品说明</h2>
      <p>{description}</p>
    </section>
  </main>
</body>
</html>"""


def escape(value: str) -> str:
    return html.escape(value, quote=True)
