import os
from PIL import Image


SOURCE_LOGO = os.path.join("static", "dream-bot.png")


def _resize_logo_rgba(source: Image.Image, size: int) -> Image.Image:
    return source.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")


def _create_maskable_logo(source: Image.Image, size: int) -> Image.Image:
    safe_size = int(size * 0.8)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    logo = source.resize((safe_size, safe_size), Image.Resampling.LANCZOS).convert("RGBA")
    offset = ((size - safe_size) // 2, (size - safe_size) // 2)
    canvas.alpha_composite(logo, dest=offset)
    return canvas


def generate_icons():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")
    os.makedirs(static_dir, exist_ok=True)
    source_logo_path = os.path.join(base_dir, SOURCE_LOGO)

    if not os.path.exists(source_logo_path):
        raise FileNotFoundError(f"Source logo not found: {source_logo_path}")

    source_logo = Image.open(source_logo_path).convert("RGBA")

    specs = [
        ("favicon-32.png", 32),
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),
    ]

    for filename, size in specs:
        output = _resize_logo_rgba(source_logo, size)
        output_path = os.path.join(static_dir, filename)
        output.save(output_path, format="PNG")
        print("wrote", output_path)

    maskable_path = os.path.join(static_dir, "icon-512-maskable.png")
    maskable = _create_maskable_logo(source_logo, 512)
    maskable.save(maskable_path, format="PNG")
    print("wrote", maskable_path)


if __name__ == "__main__":
    generate_icons()