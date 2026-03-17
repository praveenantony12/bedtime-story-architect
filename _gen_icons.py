import math
import os
import random
import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BG_INNER = (88, 34, 134)
BG_OUTER = (3, 1, 10)
HAZE_COLOR = (108, 48, 176)
STAR_COLOR = (245, 241, 255)
MOON_COLOR = (251, 245, 255)
MOON_RIM = (214, 186, 255)
GLOW_COLOR = (156, 84, 255)


def clamp01(value):
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value


def lerp(a, b, t):
    return a + (b - a) * t


def mix_color(base, target, alpha):
    return (
        int(lerp(base[0], target[0], alpha) + 0.5),
        int(lerp(base[1], target[1], alpha) + 0.5),
        int(lerp(base[2], target[2], alpha) + 0.5),
    )


def smoothstep(edge0, edge1, value):
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    t = clamp01((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def blend(base, overlay, alpha):
    if alpha <= 0.0:
        return base
    if alpha >= 1.0:
        return overlay
    return (
        int(base[0] + (overlay[0] - base[0]) * alpha + 0.5),
        int(base[1] + (overlay[1] - base[1]) * alpha + 0.5),
        int(base[2] + (overlay[2] - base[2]) * alpha + 0.5),
    )


def png_chunk(chunk_type, data):
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def write_png(path, width, height, pixels):
    raw = bytearray()
    row_stride = width * 3
    for row in range(height):
        raw.append(0)
        start = row * row_stride
        raw.extend(pixels[start : start + row_stride])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), level=9)
    png = PNG_SIGNATURE + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")

    with open(path, "wb") as handle:
        handle.write(png)


def make_stars(size, maskable):
    rng = random.Random(size * 1009 + (97 if maskable else 31))
    stars = []
    count = max(18, size // 16)
    if maskable:
        min_pos = size * 0.10
        max_pos = size * 0.90
    else:
        min_pos = size * 0.04
        max_pos = size * 0.96

    moon_x = size * (0.58 if maskable else 0.61)
    moon_y = size * (0.43 if maskable else 0.40)
    moon_radius = size * (0.16 if maskable else 0.19)

    for _ in range(count):
        for _attempt in range(18):
            radius = rng.uniform(size * 0.0025, size * 0.0075)
            x = rng.uniform(min_pos + radius * 3.0, max_pos - radius * 3.0)
            y = rng.uniform(min_pos + radius * 3.0, max_pos - radius * 3.0)
            distance = math.hypot(x - moon_x, y - moon_y)
            if distance > moon_radius * 1.55:
                stars.append(
                    {
                        "x": x,
                        "y": y,
                        "radius": radius,
                        "glow": rng.uniform(1.8, 3.4),
                        "alpha": rng.uniform(0.35, 0.95),
                        "spike": rng.uniform(0.0, 0.45),
                    }
                )
                break

    return stars


def render_icon(size, maskable=False):
    pixels = bytearray(size * size * 3)
    stars = make_stars(size, maskable)
    safe_min = size * 0.10
    safe_max = size * 0.90

    moon_x = size * (0.58 if maskable else 0.61)
    moon_y = size * (0.43 if maskable else 0.40)
    moon_radius = size * (0.16 if maskable else 0.19)
    cut_x = moon_x + moon_radius * 0.46
    cut_y = moon_y - moon_radius * 0.08
    cut_radius = moon_radius * 0.93
    glow_radius = moon_radius * (1.68 if maskable else 1.82)
    aa = max(1.1, size * 0.0035)

    haze_x = size * 0.36
    haze_y = size * 0.26
    haze_radius = size * 0.92

    for y in range(size):
        row_offset = y * size * 3
        for x in range(size):
            base_distance = math.hypot(x - haze_x, y - haze_y) / haze_radius
            base_t = clamp01(base_distance)
            color = mix_color(BG_INNER, BG_OUTER, pow(base_t, 0.92))

            moon_haze = math.hypot(x - moon_x, y - moon_y) / (size * 0.78)
            haze_alpha = clamp01(1.0 - moon_haze) * 0.28
            color = blend(color, HAZE_COLOR, haze_alpha)

            in_safe_zone = (not maskable) or (safe_min <= x <= safe_max and safe_min <= y <= safe_max)

            if in_safe_zone:
                for star in stars:
                    dx = x - star["x"]
                    dy = y - star["y"]
                    distance = math.hypot(dx, dy)
                    sigma = star["radius"] * star["glow"]
                    glow = math.exp(-((distance * distance) / (2.0 * sigma * sigma))) * star["alpha"]
                    if star["spike"] > 0.0:
                        line = min(abs(dx), abs(dy))
                        spike = math.exp(-line / max(0.8, star["radius"] * 0.8))
                        spike *= math.exp(-distance / max(1.0, star["radius"] * 5.0)) * star["spike"]
                        glow += spike
                    if glow > 0.002:
                        color = blend(color, STAR_COLOR, clamp01(glow))

                moon_distance = math.hypot(x - moon_x, y - moon_y)
                cut_distance = math.hypot(x - cut_x, y - cut_y)

                glow_alpha = clamp01(1.0 - smoothstep(moon_radius * 0.78, glow_radius, moon_distance)) * 0.42
                color = blend(color, GLOW_COLOR, glow_alpha)

                moon_disk = 1.0 - smoothstep(moon_radius - aa, moon_radius + aa, moon_distance)
                moon_cut = 1.0 - smoothstep(cut_radius - aa, cut_radius + aa, cut_distance)
                crescent_alpha = clamp01(moon_disk - moon_cut)

                if crescent_alpha > 0.0:
                    rim = clamp01((moon_distance - moon_radius * 0.45) / (moon_radius * 0.55))
                    moon_tint = blend(MOON_COLOR, MOON_RIM, rim * 0.55)
                    color = blend(color, moon_tint, crescent_alpha)

            idx = row_offset + x * 3
            pixels[idx] = color[0]
            pixels[idx + 1] = color[1]
            pixels[idx + 2] = color[2]

    return pixels


def generate_icons():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")
    os.makedirs(static_dir, exist_ok=True)

    specs = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("apple-touch-icon.png", 180, False),
        ("icon-512-maskable.png", 512, True),
    ]

    for filename, size, maskable in specs:
        pixels = render_icon(size, maskable=maskable)
        output_path = os.path.join(static_dir, filename)
        write_png(output_path, size, size, pixels)
        print("wrote", output_path)


if __name__ == "__main__":
    generate_icons()