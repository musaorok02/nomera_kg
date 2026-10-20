from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_SIDE = 1600
THUMB_SIZE = (480, 360)

_FONT_PATHS = (
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",  # CentOS / RHEL
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Debian / Ubuntu
)


def _font(size: int):
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # старый Pillow
        return ImageFont.load_default()


def _add_watermark(img: Image.Image, text: str) -> Image.Image:
    if not text:
        return img
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(14, base.width // 38))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left, bottom - top
    margin = max(8, base.width // 80)
    x = base.width - w - margin - left
    y = base.height - h - margin - top
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 140))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 190))
    return Image.alpha_composite(base, overlay).convert("RGB")


def _jpeg(img: Image.Image, quality: int) -> ContentFile:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return ContentFile(buf.getvalue())


def process_upload(fileobj, watermark_text: str = ""):
    """Возвращает (основное фото, миниатюра) в JPEG.

    Перекодирование убирает EXIF (в том числе GPS-координаты), поворот
    исправляется по EXIF, на фото накладывается водяной знак.
    """
    fileobj.seek(0)
    img = Image.open(fileobj)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    img = _add_watermark(img, watermark_text)
    thumb = ImageOps.fit(img, THUMB_SIZE, Image.LANCZOS)
    return _jpeg(img, 85), _jpeg(thumb, 80)
