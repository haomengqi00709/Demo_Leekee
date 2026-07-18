# -*- coding: utf-8 -*-
"""把 images/ 里所有产品图缩成 ~150px 缩略图存到 images_thumb/（不动原图），供前端嵌入。"""
import os
from PIL import Image

D = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(D, "images")
DST = os.path.join(D, "images_thumb")

def main():
    made = skipped = total = 0
    for root, _, files in os.walk(SRC):
        for fn in files:
            src = os.path.join(root, fn)
            rel = os.path.relpath(src, SRC)
            dst = os.path.join(DST, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                im = Image.open(src)
                fmt = (im.format or "").upper()
                im.thumbnail((150, 150))
                if fmt in ("JPEG", "JPG") or fn.lower().endswith((".jpg", ".jpeg")):
                    im.convert("RGB").save(dst, "JPEG", quality=80, optimize=True)
                else:
                    im.save(dst, "PNG", optimize=True)
                made += 1; total += os.path.getsize(dst)
            except Exception as e:
                skipped += 1
    print(f"生成 {made} 张缩略图 · 合计 {total/1048576:.2f} MB · 跳过 {skipped}")

if __name__ == "__main__":
    main()
