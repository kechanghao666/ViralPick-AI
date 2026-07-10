from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


ROOT_DIR = Path(__file__).resolve().parents[1]
PRODUCTS_CSV = ROOT_DIR / "data" / "processed" / "products.csv"
COMPETITORS_CSV = ROOT_DIR / "data" / "processed" / "competitors.csv"
OUTPUT_DIR = ROOT_DIR / "frontend" / "assets" / "img" / "products"
SOURCE_MANIFEST = ROOT_DIR / "data" / "processed" / "product_image_sources.json"
CONTACT_SHEET = ROOT_DIR / "data" / "processed" / "product_image_contact_sheet.jpg"

CANVAS_SIZE = (720, 540)
MIN_IMAGE_SIZE = 280
REQUEST_TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}

IMAGE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


@dataclass
class ImageCandidate:
    image_url: str
    source_url: str
    title: str


def main() -> None:
    products = pd.read_csv(PRODUCTS_CSV, encoding="utf-8-sig")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sources: list[dict] = []

    for _, product in products.iterrows():
        product_id = str(product["product_id"])
        product_name = str(product["product_name"])
        print(f"[{product_id}] searching {product_name}", flush=True)
        candidates = search_bing_images(_query_for(product))
        print(f"  candidates: {len(candidates)}", flush=True)
        saved = None
        for candidate in candidates:
            try:
                saved = download_and_convert(product_id, candidate)
            except Exception as exc:
                print(f"  skip {candidate.image_url[:90]} -> {exc}", flush=True)
                continue
            if saved:
                sources.append(
                    {
                        "product_id": product_id,
                        "product_name": product_name,
                        "local_image": f"./assets/img/products/{product_id}.jpg",
                        "source_url": candidate.source_url,
                        "image_url": candidate.image_url,
                        "source_host": urlparse(candidate.source_url).netloc,
                        "title": candidate.title,
                    }
                )
                print(f"  saved {saved.name} from {urlparse(candidate.source_url).netloc}", flush=True)
                break
        if not saved:
            raise RuntimeError(f"No usable image found for {product_id} {product_name}")
        time.sleep(0.6)

    update_csv_image_urls(products)
    write_source_manifest(sources)
    build_contact_sheet(products)
    print(f"Updated {PRODUCTS_CSV}")
    print(f"Wrote {SOURCE_MANIFEST}")
    print(f"Wrote {CONTACT_SHEET}")


def _query_for(product: pd.Series) -> str:
    name = str(product["product_name"]).strip()
    brand = str(product.get("brand") or "").strip()
    category = str(product.get("category") or "").strip()
    # The extra terms prefer packshot/product-listing images over reviews or lifestyle photos.
    return f"{name} {brand} {category} 商品图 白底"


def search_bing_images(query: str, limit: int = 24) -> list[ImageCandidate]:
    response = requests.get(
        "https://www.bing.com/images/search",
        params={"q": query, "form": "HDRSC2", "first": 1},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    text = response.text
    candidates: list[ImageCandidate] = []
    seen: set[str] = set()

    for match in re.finditer(r"class=\"iusc\"[^>]+m=\"([^\"]+)\"", text):
        raw = match.group(1)
        try:
            payload = json.loads(html.unescape(raw))
        except json.JSONDecodeError:
            continue
        image_url = str(payload.get("murl") or "").strip()
        source_url = str(payload.get("purl") or payload.get("purl") or "").strip()
        title = str(payload.get("t") or payload.get("desc") or "").strip()
        if _usable_url(image_url) and image_url not in seen:
            seen.add(image_url)
            candidates.append(ImageCandidate(image_url=image_url, source_url=source_url or image_url, title=title))
        if len(candidates) >= limit:
            break

    if len(candidates) < limit:
        for pattern in [r"murl&quot;:&quot;(.*?)&quot;.*?purl&quot;:&quot;(.*?)&quot;", r'"murl":"(.*?)".*?"purl":"(.*?)"']:
            for image_url, source_url in re.findall(pattern, text):
                image_url = _clean_url(image_url)
                source_url = _clean_url(source_url)
                if _usable_url(image_url) and image_url not in seen:
                    seen.add(image_url)
                    candidates.append(ImageCandidate(image_url=image_url, source_url=source_url or image_url, title=""))
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break

    return candidates


def _clean_url(value: str) -> str:
    return html.unescape(value).replace("\\/", "/").strip()


def _usable_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    lower = url.lower()
    blocked_bits = ("logo", "avatar", "icon", "sprite", "favicon")
    return not any(bit in lower for bit in blocked_bits)


def download_and_convert(product_id: str, candidate: ImageCandidate) -> Path | None:
    headers = {**IMAGE_HEADERS, "Referer": candidate.source_url}
    response = requests.get(candidate.image_url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "image" not in content_type and not re.search(r"\.(jpe?g|png|webp)(\?|$)", candidate.image_url, re.I):
        raise ValueError(f"not image content: {content_type}")
    raw = response.content
    if len(raw) < 8_000:
        raise ValueError("image too small")

    temp_path = OUTPUT_DIR / f"{product_id}.download"
    temp_path.write_bytes(raw)
    try:
        with Image.open(temp_path) as original:
            original.load()
            if original.width < MIN_IMAGE_SIZE or original.height < MIN_IMAGE_SIZE:
                raise ValueError(f"image dimensions too small: {original.width}x{original.height}")
            converted = _fit_on_canvas(original.convert("RGBA"))
            target = OUTPUT_DIR / f"{product_id}.jpg"
            converted.save(target, format="JPEG", quality=88, optimize=True)
            return target
    except UnidentifiedImageError as exc:
        raise ValueError("unrecognized image format") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _fit_on_canvas(image: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", CANVAS_SIZE, "white")
    image.thumbnail((CANVAS_SIZE[0] - 56, CANVAS_SIZE[1] - 56), Image.Resampling.LANCZOS)
    x = (CANVAS_SIZE[0] - image.width) // 2
    y = (CANVAS_SIZE[1] - image.height) // 2
    if image.mode == "RGBA":
        canvas.paste(image, (x, y), image)
    else:
        canvas.paste(image, (x, y))
    return canvas


def update_csv_image_urls(products: pd.DataFrame) -> None:
    updated = products.copy()
    updated["image_url"] = updated["product_id"].map(lambda value: f"./assets/img/products/{value}.jpg")
    updated.to_csv(PRODUCTS_CSV, index=False, encoding="utf-8-sig")

    if COMPETITORS_CSV.exists():
        competitors = pd.read_csv(COMPETITORS_CSV, encoding="utf-8-sig")
        if "product_id" in competitors.columns and "competitor_image_url" in competitors.columns:
            competitors["competitor_image_url"] = competitors["product_id"].map(
                lambda value: f"./assets/img/products/{value}.jpg"
            )
            competitors.to_csv(COMPETITORS_CSV, index=False, encoding="utf-8-sig")


def write_source_manifest(sources: list[dict]) -> None:
    SOURCE_MANIFEST.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")


def build_contact_sheet(products: pd.DataFrame) -> None:
    thumb_w, thumb_h = 260, 195
    label_h = 58
    cols = 4
    rows = (len(products) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), "#f6faf9")
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    small_font = _font(13)
    for index, product in products.reset_index(drop=True).iterrows():
        product_id = str(product["product_id"])
        image_path = OUTPUT_DIR / f"{product_id}.jpg"
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            image.thumbnail((thumb_w - 20, thumb_h - 20), Image.Resampling.LANCZOS)
            x = (index % cols) * thumb_w
            y = (index // cols) * (thumb_h + label_h)
            draw.rectangle([x + 5, y + 5, x + thumb_w - 5, y + thumb_h + label_h - 5], fill="white", outline="#d8e4e3")
            sheet.paste(image, (x + (thumb_w - image.width) // 2, y + 10 + (thumb_h - 20 - image.height) // 2))
            draw.text((x + 14, y + thumb_h + 6), f"{product_id} {product['brand']}", fill="#071316", font=font)
            draw.text((x + 14, y + thumb_h + 30), str(product["product_name"])[:18], fill="#65777d", font=small_font)
    sheet.save(CONTACT_SHEET, format="JPEG", quality=90)


def _font(size: int) -> ImageFont.ImageFont:
    for path in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


if __name__ == "__main__":
    main()
