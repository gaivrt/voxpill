"""Generate the multi-resolution Windows icon from the VoxPill SVG design."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "voxpill.ico"
CANVAS = 1024


def build_icon() -> None:
    scale = CANVAS / 64
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        tuple(round(value * scale) for value in (1, 1, 63, 63)),
        fill="#f0ede4",
    )
    for x, y, width, height in (
        (16, 25, 4, 14),
        (23, 20, 4, 24),
        (30, 15, 4, 34),
        (37, 20, 4, 24),
        (44, 25, 4, 14),
    ):
        draw.rounded_rectangle(
            tuple(round(value * scale) for value in (x, y, x + width, y + height)),
            radius=round(2 * scale),
            fill="#272624",
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        OUTPUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_icon()
    print(OUTPUT)
