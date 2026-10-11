"""Creates a clean, attractive tray icon using Pillow."""
from PIL import Image, ImageDraw, ImageFont
import os


def create_tray_icon_image(size: int = 64) -> Image.Image:
    """Generates a crisp Riot-themed tray icon (red badge with stylized R/key)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg_color = (209, 54, 57, 255)
    border_color = (255, 255, 255, 230)

    pad = 2
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=14,
        fill=bg_color,
        outline=border_color,
        width=2,
    )

    draw.rectangle([16, 14, 25, 50], fill=(255, 255, 255, 255))

    draw.rounded_rectangle([20, 14, 48, 33], radius=8, fill=(255, 255, 255, 255))

    draw.rounded_rectangle([25, 20, 42, 27], radius=4, fill=bg_color)

    draw.polygon([(26, 31), (46, 50), (37, 50), (22, 34)], fill=(255, 255, 255, 255))

    return img


def save_icon_files(output_dir: str):
    """Saves generated icon to PNG and ICO files if not already existing."""
    ico_path = os.path.join(output_dir, "icon.ico")
    png_path = os.path.join(output_dir, "icon.png")

    if not os.path.exists(ico_path) or not os.path.exists(png_path):
        icon_img = create_tray_icon_image(64)
        if not os.path.exists(png_path):
            icon_img.save(png_path, format="PNG")
        if not os.path.exists(ico_path):
            icon_img.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    return ico_path, png_path


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ico, png = save_icon_files(current_dir)
    print(f"Saved icon to: {ico} and {png}")
