from pathlib import Path

from PIL import Image, ImageDraw

dest = Path(__file__).with_name("spriteforge.ico")
sizes = [16, 32, 48, 64, 128, 256]
imgs = []
for s in sizes:
    im = Image.new("RGBA", (s, s), (12, 15, 20, 255))
    d = ImageDraw.Draw(im)
    m = max(1, s // 16)
    d.rounded_rectangle((m, m, s - m - 1, s - m - 1), radius=s // 5, fill=(27, 33, 48, 255))
    d.rounded_rectangle((s // 5, s // 4, s - s // 5, s - s // 5), radius=s // 10, fill=(62, 224, 194, 255))
    d.rectangle((s // 3, s // 6, s - s // 3, s // 3), fill=(255, 107, 87, 255))
    imgs.append(im)
imgs[0].save(dest, sizes=[(s, s) for s in sizes], format="ICO")
print(dest)
