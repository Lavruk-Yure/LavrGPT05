# dev_tools\pillow.py
import os

from PIL import Image, ImageDraw, ImageFont


def create_icon(text, filename):
    img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))  # Прозорий фон
    draw = ImageDraw.Draw(img)
    try:
        # Спроба жирного Arial (стандартний у Windows)
        font = ImageFont.truetype("arialbd.ttf", 18)  # Жирний Arial
    except:  # noqa
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except:  # noqa
            font = ImageFont.load_default()
    # Обчислення центру
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (24 - text_w) // 2
    y = (24 - text_h) // 2 - 1  # Невеликий зсув для ідеального центру
    draw.text((x, y), text, font=font, fill=(32, 32, 32, 255))  # сірий колір
    img.save(filename, "PNG")


# Створення папки та іконок
os.makedirs("icons", exist_ok=True)
create_icon("I", "../icons/icon_info_24.png")
create_icon("?", "../icons/icon_question_24.png")
create_icon("!", "../icons/icon_warning_24.png")
create_icon("і", "../icons/icon_info_ua_24.png")
print("Іконки створено")
