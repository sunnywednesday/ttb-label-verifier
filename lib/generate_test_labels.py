"""
Generates synthetic label images for testing, since real bottle photography
wasn't available for this prototype. The take-home brief explicitly suggests
this approach ("AI image generation tools work well for this") -- this does
the same job deterministically and for free using Pillow, and additionally
produces deliberately imperfect labels (mismatch, title-case warning, glare
simulation) to exercise the matching logic described in the interviews.

Run:  python lib/generate_test_labels.py
Output goes to ./test_labels/ and a matching ./sample_data/applications.csv
"""

import csv
import os
import random
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "test_labels")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "sample_data", "applications.csv")

WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)

LABELS = [
    # name, class_type, abv, net_contents, producer, country, warning_text, warning_caps, brand_on_label
    dict(id="label_01_clean_pass", brand="OLD TOM DISTILLERY",
         class_type="Kentucky Straight Bourbon Whiskey", abv="45% Alc./Vol. (90 Proof)",
         net="750 mL", producer="Old Tom Distillery Co., Bardstown, KY",
         country="", warning=WARNING, warning_caps=True,
         app_brand="OLD TOM DISTILLERY"),
    dict(id="label_02_casing_review", brand="Stone's Throw",
         class_type="American Single Malt Whiskey", abv="43% Alc./Vol. (86 Proof)",
         net="750 mL", producer="Stone's Throw Distilling, Asheville, NC",
         country="", warning=WARNING, warning_caps=True,
         app_brand="STONE'S THROW"),  # Dave's exact example
    dict(id="label_03_warning_titlecase_fail", brand="Harbor Light Spirits",
         class_type="London Dry Gin", abv="40% Alc./Vol. (80 Proof)",
         net="750 mL", producer="Harbor Light Spirits, Seattle, WA",
         country="", warning=WARNING, warning_caps=False,  # Jenny's example
         app_brand="Harbor Light Spirits"),
    dict(id="label_04_abv_mismatch_fail", brand="Redwood Ridge Vineyards",
         class_type="Cabernet Sauvignon", abv="14.5% Alc./Vol.", net="750 mL",
         producer="Redwood Ridge Vineyards, Napa, CA", country="",
         warning=WARNING, warning_caps=True,
         app_brand="Redwood Ridge Vineyards", app_abv_override="13.5% Alc./Vol."),
    dict(id="label_05_import_country", brand="Isla Brava Tequila",
         class_type="Blanco Tequila", abv="40% Alc./Vol. (80 Proof)", net="750 mL",
         producer="Destileria Isla Brava", country="Product of Mexico",
         warning=WARNING, warning_caps=True,
         app_brand="Isla Brava Tequila"),
]


def _font(size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_label_image(spec, glare=False, angle=0):
    W, H = 600, 800
    img = Image.new("RGB", (W, H), (245, 240, 228))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, W - 10, H - 10], outline=(80, 60, 30), width=4)

    y = 60
    f_brand = _font(34)
    f_body = _font(20)
    f_small = _font(13)

    for line in _wrap(draw, spec["brand"], f_brand, W - 80):
        draw.text((W / 2, y), line, font=f_brand, fill=(40, 25, 10), anchor="ma")
        y += 42

    y += 10
    for line in _wrap(draw, spec["class_type"], f_body, W - 80):
        draw.text((W / 2, y), line, font=f_body, fill=(20, 20, 20), anchor="ma")
        y += 26

    y += 20
    draw.text((W / 2, y), spec["abv"], font=f_body, fill=(20, 20, 20), anchor="ma")
    y += 30
    draw.text((W / 2, y), spec["net"], font=f_body, fill=(20, 20, 20), anchor="ma")
    y += 40

    for line in _wrap(draw, spec["producer"], f_small, W - 80):
        draw.text((W / 2, y), line, font=f_small, fill=(20, 20, 20), anchor="ma")
        y += 18

    if spec.get("country"):
        y += 6
        draw.text((W / 2, y), spec["country"], font=f_small, fill=(20, 20, 20), anchor="ma")
        y += 22

    y += 20
    warning_font = f_small
    warning_text = spec["warning"]
    if not spec["warning_caps"]:
        # Jenny's exact failure case: title case lead-in
        warning_text = warning_text.replace("GOVERNMENT WARNING:", "Government Warning:", 1)
    for line in _wrap(draw, warning_text, warning_font, W - 70):
        draw.text((35, y), line, font=warning_font, fill=(10, 10, 10))
        y += 16

    if glare:
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([150, 300, 420, 480], fill=(255, 255, 255, 110))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    if angle:
        img = img.rotate(angle, expand=True, fillcolor=(245, 240, 228))

    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    rows = []
    for spec in LABELS:
        glare = spec["id"].endswith("review") and random.random() < 0.0  # off by default
        img = make_label_image(spec)
        path = os.path.join(OUT_DIR, spec["id"] + ".png")
        img.save(path)

        abv_for_app = spec.get("app_abv_override", spec["abv"])
        rows.append({
            "image_filename": os.path.basename(path),
            "brand_name": spec["app_brand"],
            "class_type": spec["class_type"],
            "abv": abv_for_app,
            "net_contents": spec["net"],
            "producer_name_address": spec["producer"],
            "country_of_origin": spec.get("country", ""),
        })
        print(f"Generated {path}")

    # one more: a rotated/glare-affected "bad photo" case using label_01's spec
    bad_photo = make_label_image(LABELS[0], glare=True, angle=8)
    bad_path = os.path.join(OUT_DIR, "label_06_bad_photo_quality.png")
    bad_photo.save(bad_path)
    rows.append({
        "image_filename": "label_06_bad_photo_quality.png",
        "brand_name": LABELS[0]["app_brand"],
        "class_type": LABELS[0]["class_type"],
        "abv": LABELS[0]["abv"],
        "net_contents": LABELS[0]["net"],
        "producer_name_address": LABELS[0]["producer"],
        "country_of_origin": "",
    })
    print(f"Generated {bad_path}")

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote application data CSV -> {CSV_PATH}")


if __name__ == "__main__":
    main()
