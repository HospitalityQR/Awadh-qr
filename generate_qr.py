import os
import re
import json
import math
import shutil
import hashlib
import qrcode
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

UPLOAD_DIR = r"C:\Users\Hp\.gemini\antigravity\brain\5eb7a8f4-fc16-43f0-823e-5a22048850c8\.user_uploaded"
LOGO_UPLOAD = os.path.join(UPLOAD_DIR, "media_1790789457490.png")
NIGHT_UPLOAD = os.path.join(UPLOAD_DIR, "media_1790789469429.png")
FACADE_UPLOAD = os.path.join(UPLOAD_DIR, "media_1790789481816.png")
INTERIOR_UPLOAD = os.path.join(UPLOAD_DIR, "media_1790789489781.png")
EXTERIOR_UPLOAD = os.path.join(UPLOAD_DIR, "media_1790789497505.png")


def load_config(config_path="config.js"):
    """Parse config.js and extract JSON settings safely without stripping https:// URLs."""
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"window\.RESTAURANT_CONFIG\s*=\s*(\{.*?\});", content, re.DOTALL)
    if not match:
        return {}
    json_str = match.group(1)
    # Remove full-line comments and inline comments that follow whitespace (not https://)
    json_str = re.sub(r"^\s*//.*$", "", json_str, flags=re.MULTILINE)
    json_str = re.sub(r"(?<=\s)//.*$", "", json_str, flags=re.MULTILINE)
    # Quote unquoted JS keys
    json_str = re.sub(r"([\{\,\s])([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', json_str)
    json_str = re.sub(r",\s*([\]}])", r"\1", json_str)
    try:
        return json.loads(json_str)
    except Exception as e:
        print("Config parse warning:", e)
        return {}


def get_font(size, bold=False, italic=False, serif=False):
    """Load Windows system fonts cleanly with fallbacks."""
    candidates = []
    if serif and italic:
        candidates = ["georgiai.ttf", "timesbi.ttf", "timesi.ttf", "ariali.ttf"]
    elif serif and bold:
        candidates = ["georgiab.ttf", "timesbd.ttf", "arialbd.ttf"]
    elif serif:
        candidates = ["georgia.ttf", "times.ttf", "arial.ttf"]
    elif bold and italic:
        candidates = ["arialbi.ttf", "georgiabi.ttf", "timesbi.ttf"]
    elif bold:
        candidates = ["arialbd.ttf", "segoeuib.ttf", "georgiab.ttf", "timesbd.ttf"]
    elif italic:
        candidates = ["ariali.ttf", "georgiai.ttf", "timesi.ttf"]
    else:
        candidates = ["arial.ttf", "segoeui.ttf", "georgia.ttf"]

    for font_name in candidates:
        font_path = os.path.join("C:\\Windows\\Fonts", font_name)
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass

    # Linux / Ubuntu fallback fonts (for GitHub Actions runner)
    linux_candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if (serif and bold) else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for lf in linux_candidates:
        if os.path.exists(lf):
            try:
                return ImageFont.truetype(lf, size)
            except Exception:
                pass
    return ImageFont.load_default()


def extract_awadh_logo_transparent(src_img):
    """
    Extract the official 'अवध' Saffron Calligraphy + Divine Blue Arm + Golden Bow & Arrow
    from media_1790789457490.png onto a 100% clean transparent RGBA canvas.
    Returns (fg_clean_for_light_bg, canvas_with_contour_and_shadow_for_dark_bg).
    """
    rgb = src_img.convert("RGB")
    arr = np.array(rgb, dtype=np.float32)
    H, W, _ = arr.shape

    # Detect exact vertical split column x_split between dark-grey left half and white right half
    lum_full = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    lower_profile = lum_full[int(H * 0.68):int(H * 0.86), :].mean(axis=0)
    white_cols = np.where(lower_profile > 210)[0]
    x_split_full = int(white_cols[0]) if len(white_cols) > 0 else int(W * 0.469)

    # Crop to the 'अवध' + Bow & Arrow region (above the dark 'Fine Dine Restaurant' rectangle)
    y1, y2 = int(H * 0.305), int(H * 0.495)
    x1, x2 = int(W * 0.285), int(W * 0.935)

    sub = arr[y1:y2, x1:x2].copy()
    sh, sw, _ = sub.shape
    x_split = x_split_full - x1

    r, g, b = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # 1. Right side (x >= x_split + 1): Background is pure white (255, 255, 255)
    # Use a clean threshold (28.0) so faint JPEG noise around the bow is 100% ignored
    max_drop_white = np.maximum(np.maximum(255.0 - r, 255.0 - g), 255.0 - b)
    alpha_right = np.clip((max_drop_white - 26.0) / 42.0, 0.0, 1.0)

    # Un-premultiply white background on right side for rich, halo-free edge colors
    r_unwhite = np.clip((r - 255.0 * (1.0 - alpha_right)) / np.maximum(alpha_right, 0.22), 0, 255)
    g_unwhite = np.clip((g - 255.0 * (1.0 - alpha_right)) / np.maximum(alpha_right, 0.22), 0, 255)
    b_unwhite = np.clip((b - 255.0 * (1.0 - alpha_right)) / np.maximum(alpha_right, 0.22), 0, 255)

    # 2. Left side (x < x_split + 1): Background is dark grey (R,G,B ~ 68..96)
    # Extract the vibrant orange strokes of 'अ' AND its crisp white outline
    orange_score = np.clip(((r - b) - 46.0) / 40.0, 0.0, 1.0) * np.clip((r - 125.0) / 42.0, 0.0, 1.0)
    white_outline_score = np.clip((lum - 148.0) / 45.0, 0.0, 1.0)

    # Restrict white_outline_score on the left side to pixels within 9px of orange 'अ' strokes
    orange_pil = Image.fromarray((orange_score * 255).astype(np.uint8), "L")
    orange_dilated = np.array(orange_pil.filter(ImageFilter.MaxFilter(13)), dtype=np.float32) / 255.0
    white_outline_score = white_outline_score * np.clip(orange_dilated * 1.4, 0.0, 1.0)

    # For clean foreground (used inside the white medallion), use only colored strokes on left side
    alpha_left_clean = orange_score
    # For dark background wordmark, include the crisp white outline of 'अ'
    alpha_left_dark = np.maximum(orange_score, white_outline_score)

    x_grid = np.arange(sw)[None, :]
    is_right = (x_grid >= x_split + 1)

    alpha_clean = np.where(is_right, alpha_right, alpha_left_clean)
    alpha_dark = np.where(is_right, alpha_right, alpha_left_dark)

    out_r = np.where(is_right, r_unwhite, np.where(orange_score >= white_outline_score, r, 255.0))
    out_g = np.where(is_right, g_unwhite, np.where(orange_score >= white_outline_score, g, 255.0))
    out_b = np.where(is_right, b_unwhite, np.where(orange_score >= white_outline_score, b, 255.0))

    # Boost saturation/vibrance of the saffron-orange 'अवध', blue arm & golden bow
    is_saffron = (out_r - out_b > 65) & (out_r > 160) & (out_g < 165)
    out_r = np.where(is_saffron, np.clip(out_r * 1.06 + 8, 235, 255), out_r)
    out_g = np.where(is_saffron, np.clip(out_g * 1.02 + 2, 88, 138), out_g)
    out_b = np.where(is_saffron, np.clip(out_b * 0.72, 8, 42), out_b)

    # Tight crop to non-empty pixels
    ys, xs = np.where(alpha_dark > 0.15)
    if len(xs) > 0 and len(ys) > 0:
        pad = 20
        cx1 = max(0, int(xs.min()) - pad)
        cy1 = max(0, int(ys.min()) - pad)
        cx2 = min(sw, int(xs.max()) + pad)
        cy2 = min(sh, int(ys.max()) + pad)
        out_r = out_r[cy1:cy2, cx1:cx2]
        out_g = out_g[cy1:cy2, cx1:cx2]
        out_b = out_b[cy1:cy2, cx1:cx2]
        alpha_clean = alpha_clean[cy1:cy2, cx1:cx2]
        alpha_dark = alpha_dark[cy1:cy2, cx1:cx2]

    # Clean RGBA for light backgrounds (inside the 24k Gold Medallion)
    rgba_clean = np.stack([
        np.clip(out_r, 0, 255).astype(np.uint8),
        np.clip(out_g, 0, 255).astype(np.uint8),
        np.clip(out_b, 0, 255).astype(np.uint8),
        np.clip(alpha_clean * 255.0, 0, 255).astype(np.uint8)
    ], axis=2)
    fg_clean_img = Image.fromarray(rgba_clean, "RGBA")

    # Dark-background RGBA with a crisp 2px white/ivory contour and subtle drop shadow
    rgba_dark = np.stack([
        np.clip(out_r, 0, 255).astype(np.uint8),
        np.clip(out_g, 0, 255).astype(np.uint8),
        np.clip(out_b, 0, 255).astype(np.uint8),
        np.clip(alpha_dark * 255.0, 0, 255).astype(np.uint8)
    ], axis=2)
    fg_dark_img = Image.fromarray(rgba_dark, "RGBA")

    # Use clean stroke mask (thresholded at > 110) so the white contour is tight and razor-sharp
    hard_mask = Image.fromarray(((alpha_clean > 0.42) * 255).astype(np.uint8), "L")
    contour_mask = hard_mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.8))
    c_arr = np.clip(np.array(contour_mask, dtype=np.float32) * 1.4, 0, 255).astype(np.uint8)

    contour_rgba = np.zeros_like(rgba_dark)
    contour_rgba[:, :, 0] = 255
    contour_rgba[:, :, 1] = 252
    contour_rgba[:, :, 2] = 244
    contour_rgba[:, :, 3] = c_arr
    contour_img = Image.fromarray(contour_rgba, "RGBA")

    shadow_mask = hard_mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(6.5))
    sh_arr = (np.array(shadow_mask, dtype=np.float32) * 0.85).astype(np.uint8)
    shadow_rgba = np.zeros_like(rgba_dark)
    shadow_rgba[:, :, 3] = sh_arr
    shadow_img = Image.fromarray(shadow_rgba, "RGBA")

    canvas = Image.new("RGBA", (fg_dark_img.width + 24, fg_dark_img.height + 24), (0, 0, 0, 0))
    canvas.paste(shadow_img, (12, 16), mask=shadow_img)
    canvas.paste(contour_img, (12, 12), mask=contour_img)
    canvas.paste(fg_dark_img, (12, 12), mask=fg_dark_img)
    return fg_clean_img, canvas


def prepare_brand_assets():
    """
    Process the 5 user-uploaded Awadh Restaurant files into ultra-luxury brand assets.
    """
    if os.path.exists(LOGO_UPLOAD):
        shutil.copyfile(LOGO_UPLOAD, "source_logo.png")
    if os.path.exists(NIGHT_UPLOAD):
        shutil.copyfile(NIGHT_UPLOAD, "source_night.png")
    if os.path.exists(FACADE_UPLOAD):
        shutil.copyfile(FACADE_UPLOAD, "source_facade.png")
    if os.path.exists(INTERIOR_UPLOAD):
        shutil.copyfile(INTERIOR_UPLOAD, "source_interior.png")
    if os.path.exists(EXTERIOR_UPLOAD):
        shutil.copyfile(EXTERIOR_UPLOAD, "source_exterior.png")

    # 1. Extract Transparent 'अवध' + Divine Bow & Arrow Wordmark (awadh_title.png)
    fg_clean, awadh_wordmark = None, None
    if os.path.exists("source_logo.png"):
        src_logo = Image.open("source_logo.png")
        fg_clean, awadh_wordmark = extract_awadh_logo_transparent(src_logo)
        awadh_wordmark.save("awadh_title.png")
        print("[OK] Generated awadh_title.png (Transparent Saffron-Orange & Golden Bow Wordmark)")

    # 2. Create 24k Gold-Rimmed Circular Royal Medallion (logo_with_gold_rim.png & logo.png)
    size = 600
    medallion = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(medallion)

    # Outer 24k Gold Triple Ring
    mdraw.ellipse([4, 4, size - 5, size - 5], fill=(212, 175, 55, 255), outline=(249, 226, 156, 255), width=6)
    mdraw.ellipse([16, 16, size - 17, size - 17], fill=(148, 112, 24, 255))
    mdraw.ellipse([22, 22, size - 23, size - 23], fill=(255, 252, 245, 255))

    inner_size = size - 56
    inner_circle = Image.new("RGBA", (inner_size, inner_size), (255, 252, 244, 255))
    idraw = ImageDraw.Draw(inner_circle)

    # Decorative saffron & emerald pure-veg heritage waves at bottom of medallion
    idraw.pieslice([-40, int(inner_size * 0.73), inner_size + 40, inner_size + 110], 180, 360, fill=(240, 101, 19, 255))
    idraw.pieslice([20, int(inner_size * 0.79), inner_size - 20, inner_size + 120], 180, 360, fill=(24, 138, 55, 255))
    idraw.pieslice([75, int(inner_size * 0.85), inner_size - 75, inner_size + 130], 180, 360, fill=(212, 175, 55, 255))

    # 100% Pure Veg green badge at top center of medallion
    veg_bx, veg_by = inner_size // 2, 70
    veg_r = 21
    idraw.rounded_rectangle(
        [veg_bx - veg_r, veg_by - veg_r, veg_bx + veg_r, veg_by + veg_r],
        radius=5,
        fill=(255, 255, 255, 255),
        outline=(22, 138, 54, 255),
        width=3
    )
    idraw.ellipse([veg_bx - 10, veg_by - 10, veg_bx + 10, veg_by + 10], fill=(22, 138, 54, 255))

    font_veg = get_font(19, bold=True)
    veg_txt = "100% PURE VEG"
    vb = idraw.textbbox((0, 0), veg_txt, font=font_veg)
    idraw.text(((inner_size - (vb[2] - vb[0])) / 2, 100), veg_txt, fill=(22, 118, 46, 255), font=font_veg)

    # Paste the clean extracted 'अवध' + Bow & Arrow emblem into the center of the medallion
    if fg_clean is not None:
        wm_copy = fg_clean.copy()
        target_w = int(inner_size * 0.84)
        target_h = int(wm_copy.height * (target_w / wm_copy.width))
        wm_copy = wm_copy.resize((target_w, target_h), Image.Resampling.LANCZOS)
        wx = (inner_size - target_w) // 2 + 8
        wy = (inner_size - target_h) // 2 - 8
        inner_circle.paste(wm_copy, (wx, wy), mask=wm_copy)

    # Dark gold-rimmed 'FINE DINE RESTAURANT' plaque inside medallion below 'अवध'
    pill_w, pill_h = 316, 40
    px1 = (inner_size - pill_w) // 2
    py1 = 340
    idraw.rounded_rectangle(
        [px1, py1, px1 + pill_w, py1 + pill_h],
        radius=9,
        fill=(26, 22, 20, 255),
        outline=(212, 175, 55, 255),
        width=2
    )
    font_fd = get_font(19, bold=True, serif=True)
    fd_txt = "Fine Dine Restaurant"
    fb = idraw.textbbox((0, 0), fd_txt, font=font_fd)
    idraw.text(((inner_size - (fb[2] - fb[0])) / 2, py1 + 9), fd_txt, fill=(247, 215, 116, 255), font=font_fd)

    # Apply circular mask
    circle_mask = Image.new("L", (inner_size, inner_size), 0)
    cdraw = ImageDraw.Draw(circle_mask)
    cdraw.ellipse([0, 0, inner_size - 1, inner_size - 1], fill=255)
    medallion.paste(inner_circle, (28, 28), mask=circle_mask)

    # Inner hairline gold ring
    mdraw.ellipse([25, 25, size - 26, size - 26], outline=(212, 175, 55, 235), width=5)

    medallion.save("logo_with_gold_rim.png")
    medallion.save("logo.png")
    print("[OK] Generated logo_with_gold_rim.png & logo.png (24k Gold Rim Medallion)")

    # 3. Generate Curated High-Contrast Ambience Photos from the 4 Uploaded Restaurant Photos
    # ambience_1.jpg: Iconic Warm Wood Facade & 3D 'अवध' Bow-and-Arrow Sign (from source_facade.png)
    if os.path.exists("source_facade.png"):
        im1 = Image.open("source_facade.png").convert("RGB")
        w1, h1 = im1.size
        c1 = im1.crop((int(w1 * 0.08), int(h1 * 0.18), w1, int(h1 * 0.94)))
        c1 = ImageEnhance.Color(ImageEnhance.Contrast(c1).enhance(1.14)).enhance(1.18)
        c1.save("ambience_1.jpg", quality=95)

    # ambience_2.jpg: Grand Double-Height Chandelier Dining Hall & Plush Booths (from source_interior.png)
    if os.path.exists("source_interior.png"):
        im2 = Image.open("source_interior.png").convert("RGB")
        w2, h2 = im2.size
        c2 = im2.crop((0, int(h2 * 0.04), w2, int(h2 * 0.92)))
        c2 = ImageEnhance.Color(ImageEnhance.Contrast(c2).enhance(1.15)).enhance(1.20)
        c2.save("ambience_2.jpg", quality=95)

    # ambience_3.jpg: Illuminated Night Facade & Glowing 'अवध' Sign + Chandelier Atrium (from source_night.png)
    if os.path.exists("source_night.png"):
        im3 = Image.open("source_night.png").convert("RGB")
        w3, h3 = im3.size
        c3 = im3.crop((int(w3 * 0.02), int(h3 * 0.36), int(w3 * 0.72), int(h3 * 0.72)))
        c3 = ImageEnhance.Brightness(ImageEnhance.Color(ImageEnhance.Contrast(c3).enhance(1.22)).enhance(1.25)).enhance(1.12)
        c3.save("ambience_3.jpg", quality=95)

    # ambience_4.jpg: Full Grand Daytime Exterior & Red Carpet Entrance Canopy (from source_exterior.png)
    if os.path.exists("source_exterior.png"):
        im4 = Image.open("source_exterior.png").convert("RGB")
        w4, h4 = im4.size
        c4 = im4.crop((0, int(h4 * 0.36), w4, int(h4 * 0.72)))
        c4 = ImageEnhance.Color(ImageEnhance.Contrast(c4).enhance(1.16)).enhance(1.20)
        c4.save("ambience_4.jpg", quality=95)

    print("[OK] Generated ambience_1.jpg, ambience_2.jpg, ambience_3.jpg, ambience_4.jpg")


def create_ambience_luxury_background(width=1200, height=1800):
    """
    Create an Ultra-Luxury Awadh Fine Dine Ambience Background blending the grand
    double-height chandelier dining hall (source_interior.png) and warm golden/saffron
    royal Awadhi architectural lighting.
    """
    y_idx = np.linspace(0, 1, height)[:, None]
    x_idx = np.linspace(0, 1, width)[None, :]

    r_base = (12 * (1 - y_idx) + 6 * y_idx)
    g_base = (10 * (1 - y_idx) + 8 * y_idx)
    b_base = (20 * (1 - y_idx) + 15 * y_idx)

    dist_top = np.sqrt(((x_idx - 0.5) / 0.54) ** 2 + ((y_idx - 0.16) / 0.23) ** 2)
    glow_top = np.clip(1.0 - dist_top, 0, 1) ** 1.8

    dist_mid = np.sqrt(((x_idx - 0.5) / 0.60) ** 2 + ((y_idx - 0.48) / 0.32) ** 2)
    glow_mid = np.clip(1.0 - dist_mid, 0, 1) ** 2.0

    r_grad = r_base + glow_top * 58 + glow_mid * 42
    g_grad = g_base + glow_top * 36 + glow_mid * 28
    b_grad = b_base + glow_top * 14 + glow_mid * 10

    grad_arr = np.stack([
        np.clip(r_grad, 0, 255),
        np.clip(g_grad, 0, 255),
        np.clip(b_grad, 0, 255)
    ], axis=2).astype(np.uint8)
    base_img = Image.fromarray(grad_arr, "RGB")

    amb_path = "source_interior.png" if os.path.exists("source_interior.png") else (
        "ambience_2.jpg" if os.path.exists("ambience_2.jpg") else None
    )
    if amb_path:
        try:
            amb = Image.open(amb_path).convert("RGB")
            aw, ah = amb.size
            target_ratio = width / height
            src_ratio = aw / ah
            if src_ratio > target_ratio:
                new_w = int(ah * target_ratio)
                left = (aw - new_w) // 2
                amb = amb.crop((left, 0, left + new_w, ah))
            else:
                new_h = int(aw / target_ratio)
                top = (ah - new_h) // 2
                amb = amb.crop((0, top, aw, top + new_h))
            amb = amb.resize((width, height), Image.Resampling.LANCZOS)

            amb_sharp = ImageEnhance.Contrast(amb).enhance(1.20)
            amb_sharp = ImageEnhance.Color(amb_sharp).enhance(1.25)
            amb_soft = amb_sharp.filter(ImageFilter.GaussianBlur(radius=3.2))

            amb_arr = np.array(amb_soft, dtype=np.float32)
            base_arr = np.array(base_img, dtype=np.float32)

            edge_dist = np.sqrt(((x_idx - 0.5) / 0.66) ** 2 + ((y_idx - 0.46) / 0.52) ** 2)
            photo_weight = np.clip(0.52 - 0.30 * (edge_dist ** 1.5), 0.18, 0.52)[:, :, None]

            blended = base_arr * (1.0 - photo_weight) + amb_arr * photo_weight
            base_img = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), "RGB")
        except Exception as e:
            print("Ambience blend warning:", e)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    cx, cy = width // 2, 185
    for r_arch, alpha_val in [(230, 28), (305, 22), (390, 15), (480, 10)]:
        odraw.ellipse(
            [cx - r_arch, cy - int(r_arch * 0.75), cx + r_arch, cy + int(r_arch * 0.75)],
            outline=(247, 223, 148, alpha_val),
            width=2
        )

    for angle_deg in range(0, 360, 15):
        rad = math.radians(angle_deg)
        x1 = cx + int(110 * math.cos(rad))
        y1 = 135 + int(110 * math.sin(rad))
        x2 = cx + int(195 * math.cos(rad))
        y2 = 135 + int(195 * math.sin(rad))
        odraw.line([x1, y1, x2, y2], fill=(212, 175, 55, 20), width=1)

    base_rgba = base_img.convert("RGBA")
    base_rgba = Image.alpha_composite(base_rgba, overlay)
    return base_rgba.convert("RGB")


def draw_indri_luxury_borders(draw, width=1200, height=1800):
    """
    Draw the signature luxury 24k Gold double border with ornamental corner accents.
    """
    gold_outer = (212, 175, 55)
    gold_inner = (165, 132, 42)
    gold_bright = (247, 223, 148)

    m1 = 36
    draw.rectangle([m1, m1, width - m1, height - m1], outline=gold_outer, width=4)

    m2 = 52
    draw.rectangle([m2, m2, width - m2, height - m2], outline=gold_inner, width=1)

    c_len = 42
    for cx, cy, dx, dy in [
        (m2 + 10, m2 + 10, 1, 1),
        (width - m2 - 10, m2 + 10, -1, 1),
        (m2 + 10, height - m2 - 10, 1, -1),
        (width - m2 - 10, height - m2 - 10, -1, -1),
    ]:
        draw.line([cx, cy, cx + dx * c_len, cy], fill=gold_bright, width=2)
        draw.line([cx, cy, cx, cy + dy * c_len], fill=gold_bright, width=2)
        draw.polygon([(cx, cy - 5), (cx + 5, cy), (cx, cy + 5), (cx - 5, cy)], fill=gold_bright)


def draw_sparkle(draw, cx, cy, radius=12, color=(212, 175, 55)):
    """Draw a 4-point luxury star sparkle."""
    r_outer = radius
    r_inner = max(2, int(radius * 0.28))
    pts = []
    for i in range(8):
        angle = i * (math.pi / 4.0) - (math.pi / 2.0)
        r = r_outer if i % 2 == 0 else r_inner
        px = cx + math.cos(angle) * r
        py = cy + math.sin(angle) * r
        pts.append((px, py))
    draw.polygon(pts, fill=color)


def draw_star_5pt(draw, cx, cy, radius=9, color=(212, 175, 55)):
    """Draw a crisp 5-pointed gold rating star."""
    r_outer = radius
    r_inner = radius * 0.42
    pts = []
    for i in range(10):
        angle = i * (math.pi / 5.0) - (math.pi / 2.0)
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    draw.polygon(pts, fill=color)


def draw_5_stars_row(draw, start_x, cy, star_radius=8, spacing=20, color=(212, 165, 32)):
    """Draw a row of 5 gold stars."""
    for i in range(5):
        draw_star_5pt(draw, start_x + i * spacing, cy, radius=star_radius, color=color)


def draw_google_g_icon(draw, cx, cy, radius=14):
    """Draw a clean Google 'G' multi-color icon inside a white circle."""
    draw.ellipse([cx - radius - 3, cy - radius - 3, cx + radius + 3, cy + radius + 3], fill=(255, 255, 255))
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.pieslice(bbox, 220, 325, fill=(234, 67, 53))
    draw.pieslice(bbox, 135, 220, fill=(251, 188, 5))
    draw.pieslice(bbox, 45, 135, fill=(52, 168, 83))
    draw.pieslice(bbox, 345, 45, fill=(66, 133, 244))
    inner_r = int(radius * 0.56)
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=(255, 255, 255))
    draw.rectangle([cx, cy - int(radius * 0.22), cx + radius, cy + int(radius * 0.24)], fill=(66, 133, 244))


def draw_instagram_icon(draw, cx, cy, size=26):
    """Draw a clean Instagram camera glyph."""
    half = size // 2
    draw.rounded_rectangle(
        [cx - half, cy - half, cx + half, cy + half],
        radius=7,
        fill=(214, 41, 118),
        outline=(255, 255, 255),
        width=2
    )
    r_lens = int(size * 0.24)
    draw.ellipse([cx - r_lens, cy - r_lens, cx + r_lens, cy + r_lens], outline=(255, 255, 255), width=2)
    draw.ellipse([cx + half - 7, cy - half + 4, cx + half - 4, cy - half + 7], fill=(255, 255, 255))


_QR_CACHE = {}


def generate_styled_qr(url, target_size=680):
    """
    Generate an Ultra-Luxury Mudoven-style QR Code with:
    - Circular dot modules in Royal Obsidian & Awadh Saffron-Orange radial gradient
    - Custom rounded finder eyes with Saffron-Orange centers
    - Embedded 24k Gold-Rimmed Circular Awadh Medallion in the center
    """
    if url in _QR_CACHE:
        return _QR_CACHE[url].resize((target_size, target_size), Image.Resampling.LANCZOS)

    is_long_url = len(url) > 140
    err_corr = qrcode.constants.ERROR_CORRECT_M if is_long_url else qrcode.constants.ERROR_CORRECT_H

    qr = qrcode.QRCode(
        version=None,
        error_correction=err_corr,
        box_size=20,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n_mods = len(matrix)
    border = 2

    cell = 24
    canvas_px = n_mods * cell
    img = Image.new("RGBA", (canvas_px, canvas_px), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    center_mod = n_mods / 2.0
    logo_mod_radius = (n_mods * 0.13) if is_long_url else (n_mods * 0.165)

    def is_finder(r, c):
        if border <= r < border + 7 and border <= c < border + 7:
            return True
        if border <= r < border + 7 and (n_mods - border - 7) <= c < (n_mods - border):
            return True
        if (n_mods - border - 7) <= r < (n_mods - border) and border <= c < border + 7:
            return True
        return False

    dot_pad = max(1, int(cell * 0.08))
    for r in range(n_mods):
        for c in range(n_mods):
            if not matrix[r][c]:
                continue
            if is_finder(r, c):
                continue
            dist_c = math.sqrt((r + 0.5 - center_mod) ** 2 + (c + 0.5 - center_mod) ** 2)
            if dist_c < logo_mod_radius:
                continue

            norm_d = dist_c / (n_mods * 0.5)
            if norm_d < 0.44 or ((r * 7 + c * 13) % 5 == 0 and norm_d < 0.68):
                fill_col = (196, 62, 20, 255)
            else:
                fill_col = (12, 16, 28, 255)

            x1 = c * cell + dot_pad
            y1 = r * cell + dot_pad
            x2 = (c + 1) * cell - dot_pad
            y2 = (r + 1) * cell - dot_pad
            draw.ellipse([x1, y1, x2, y2], fill=fill_col)

    finder_origins = [
        (border, border),
        (border, n_mods - border - 7),
        (n_mods - border - 7, border),
    ]
    for fr, fc in finder_origins:
        fx1, fy1 = fc * cell, fr * cell
        fx2, fy2 = (fc + 7) * cell, (fr + 7) * cell
        draw.rounded_rectangle(
            [fx1, fy1, fx2, fy2],
            radius=int(cell * 1.8),
            fill=(12, 16, 28, 255),
            outline=(232, 92, 28, 255),
            width=max(2, cell // 7)
        )
        draw.rounded_rectangle(
            [fx1 + cell, fy1 + cell, fx2 - cell, fy2 - cell],
            radius=int(cell * 1.2),
            fill=(255, 255, 255, 255)
        )
        draw.rounded_rectangle(
            [fx1 + 2 * cell, fy1 + 2 * cell, fx2 - 2 * cell, fy2 - 2 * cell],
            radius=int(cell * 0.75),
            fill=(232, 92, 28, 255),
            outline=(12, 16, 28, 255),
            width=max(2, cell // 6)
        )

    logo_path = "logo_with_gold_rim.png" if os.path.exists("logo_with_gold_rim.png") else "logo.png"
    if os.path.exists(logo_path):
        logo_px = int(logo_mod_radius * 2.0 * cell)
        cx_px = canvas_px // 2
        cy_px = canvas_px // 2
        pad_ring = max(6, cell // 3)
        draw.ellipse(
            [cx_px - logo_px // 2 - pad_ring, cy_px - logo_px // 2 - pad_ring,
             cx_px + logo_px // 2 + pad_ring, cy_px + logo_px // 2 + pad_ring],
            fill=(255, 255, 255, 255),
            outline=(212, 175, 55, 255),
            width=max(3, cell // 6)
        )
        logo_im = Image.open(logo_path).convert("RGBA").resize((logo_px, logo_px), Image.Resampling.LANCZOS)
        img.paste(logo_im, (cx_px - logo_px // 2, cy_px - logo_px // 2), mask=logo_im)

    _QR_CACHE[url] = img
    return img.resize((target_size, target_size), Image.Resampling.LANCZOS)


def draw_brand_header(canvas, draw, w=1200, config=None):
    """
    Draw the Compact & Balanced Awadh Fine Dine Restaurant Luxury Header.
    """
    if config is None:
        config = {}
    logo_path = "logo_with_gold_rim.png" if os.path.exists("logo_with_gold_rim.png") else "logo.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo_size = 152
        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        canvas.paste(logo, (int((w - logo_size) / 2), 44), mask=logo)

    title_path = "awadh_title.png"
    if os.path.exists(title_path):
        title_img = Image.open(title_path).convert("RGBA")
        target_w = 395
        target_h = int(title_img.size[1] * (target_w / title_img.size[0]))
        if target_h > 148:
            target_h = 148
            target_w = int(title_img.size[0] * (target_h / title_img.size[1]))
        title_img = title_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        hx = int((w - target_w) / 2) + 8
        hy = 198
        canvas.paste(title_img, (hx, hy), mask=title_img)

    raw_sub = config.get("subname", "AWADH FINE DINE RESTAURANT").strip().upper()
    midway_text = "   ".join([" ".join(list(word)) for word in raw_sub.split()])
    font_size_sub = 27
    font_midway = get_font(font_size_sub, bold=True)
    bbox = draw.textbbox((0, 0), midway_text, font=font_midway)
    if (bbox[2] - bbox[0]) > (w - 140):
        midway_text = "  ".join([" ".join(list(word)) for word in raw_sub.split()])
        bbox = draw.textbbox((0, 0), midway_text, font=font_midway)
    while (bbox[2] - bbox[0]) > (w - 140) and font_size_sub > 18:
        font_size_sub -= 1
        font_midway = get_font(font_size_sub, bold=True)
        bbox = draw.textbbox((0, 0), midway_text, font=font_midway)
    if (bbox[2] - bbox[0]) > (w - 140):
        midway_text = raw_sub
        bbox = draw.textbbox((0, 0), midway_text, font=font_midway)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 354), midway_text, fill=(247, 223, 148), font=font_midway)

    sub_text = config.get("tagline", "100% PURE VEG  •  ROYAL FAMILY DINING  •  RAU, INDORE")
    font_size_tag = 18
    font_sub = get_font(font_size_tag, bold=True)
    bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
    while (bbox[2] - bbox[0]) > (w - 140) and font_size_tag > 13:
        font_size_tag -= 1
        font_sub = get_font(font_size_tag, bold=True)
        bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 396), sub_text, fill=(255, 255, 255), font=font_sub)

    div_y = 438
    draw.line([200, div_y, w - 200, div_y], fill=(212, 175, 55), width=2)
    draw.polygon([(w // 2, div_y - 7), (w // 2 + 7, div_y), (w // 2, div_y + 7), (w // 2 - 7, div_y)], fill=(247, 223, 148))


def draw_footer(canvas, draw, config, w=1200):
    """
    Draw the Ultra-Luxury Address & Phone Box + Gold Sparkle Thank-You Footer.
    """
    font_phone = get_font(33, bold=True)
    font_thanks = get_font(28, bold=False, italic=True, serif=True)

    info_x1, info_y1 = 82, 1450
    info_x2, info_y2 = w - 82, 1662

    glass = Image.new("RGBA", (w, 1800), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glass)
    gdraw.rounded_rectangle(
        [info_x1, info_y1, info_x2, info_y2],
        radius=18,
        fill=(8, 12, 22, 242),
        outline=(212, 175, 55, 255),
        width=3
    )
    gdraw.rounded_rectangle(
        [info_x1 + 6, info_y1 + 6, info_x2 - 6, info_y2 - 6],
        radius=14,
        outline=(247, 223, 148, 90),
        width=1
    )
    div_y = info_y1 + 60
    gdraw.line([info_x1 + 90, div_y, info_x2 - 90, div_y], fill=(212, 175, 55, 115), width=1)

    gdraw.rounded_rectangle(
        [info_x1 + 135, info_y1 + 124, info_x2 - 135, info_y2 - 16],
        radius=14,
        fill=(212, 175, 55, 42),
        outline=(249, 226, 156, 175),
        width=2
    )
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba = Image.alpha_composite(canvas_rgba, glass)
    canvas.paste(canvas_rgba.convert("RGB"))

    lbl1 = "100% PURE VEG :  "
    txt1 = config.get("highlight", "Royal Awadhi, North Indian & Global Fine Dining")
    f_size1 = 21
    font_label1 = get_font(f_size1, bold=True)
    font_addr1 = get_font(f_size1, bold=True)
    b_lbl1 = draw.textbbox((0, 0), lbl1, font=font_label1)
    b_txt1 = draw.textbbox((0, 0), txt1, font=font_addr1)
    while ((b_lbl1[2] - b_lbl1[0]) + (b_txt1[2] - b_txt1[0])) > (w - 230) and f_size1 > 14:
        f_size1 -= 1
        font_label1 = get_font(f_size1, bold=True)
        font_addr1 = get_font(f_size1, bold=True)
        b_lbl1 = draw.textbbox((0, 0), lbl1, font=font_label1)
        b_txt1 = draw.textbbox((0, 0), txt1, font=font_addr1)
    w1_lbl = b_lbl1[2] - b_lbl1[0]
    w1_txt = b_txt1[2] - b_txt1[0]
    total_w1 = w1_lbl + w1_txt
    x1_start = (w - total_w1) / 2
    y1_row = info_y1 + 19 + (21 - f_size1) // 2
    draw_sparkle(draw, x1_start - 20, y1_row + 10, radius=7, color=(249, 226, 156))
    draw.text((x1_start, y1_row), lbl1, fill=(249, 226, 156), font=font_label1)
    draw.text((x1_start + w1_lbl, y1_row), txt1, fill=(255, 255, 255), font=font_addr1)

    lbl2 = f"{config.get('addressPrimaryLabel', 'LOCATION')} :  "
    txt2 = config.get("addressPrimary", "NH 3, Near Maharana Pratap Bridge, Pigdamber, Rau, Indore")
    f_size2 = 21
    font_label2 = get_font(f_size2, bold=True)
    font_addr2 = get_font(f_size2, bold=True)
    b_lbl2 = draw.textbbox((0, 0), lbl2, font=font_label2)
    b_txt2 = draw.textbbox((0, 0), txt2, font=font_addr2)
    while ((b_lbl2[2] - b_lbl2[0]) + (b_txt2[2] - b_txt2[0])) > (w - 230) and f_size2 > 14:
        f_size2 -= 1
        font_label2 = get_font(f_size2, bold=True)
        font_addr2 = get_font(f_size2, bold=True)
        b_lbl2 = draw.textbbox((0, 0), lbl2, font=font_label2)
        b_txt2 = draw.textbbox((0, 0), txt2, font=font_addr2)
    w2_lbl = b_lbl2[2] - b_lbl2[0]
    w2_txt = b_txt2[2] - b_txt2[0]
    total_w2 = w2_lbl + w2_txt
    x2_start = (w - total_w2) / 2
    y2_row = info_y1 + 75 + (21 - f_size2) // 2
    draw_sparkle(draw, x2_start - 20, y2_row + 10, radius=7, color=(249, 226, 156))
    draw.text((x2_start, y2_row), lbl2, fill=(249, 226, 156), font=font_label2)
    draw.text((x2_start + w2_lbl, y2_row), txt2, fill=(250, 247, 240), font=font_addr2)

    phone_disp = config.get("phoneDisplay") or config.get("phone", "90351 70841")
    phone_text = f"Call / Reservation: {phone_disp}"
    bbox = draw.textbbox((0, 0), phone_text, font=font_phone)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, info_y1 + 139), phone_text, fill=(250, 228, 152), font=font_phone)

    thanks_text = "Thank you for dining with us!"
    bbox = draw.textbbox((0, 0), thanks_text, font=font_thanks)
    tw = bbox[2] - bbox[0]
    tx = (w - tw) / 2
    ty = 1692
    draw.text((tx, ty), thanks_text, fill=(247, 223, 148), font=font_thanks)

    draw_sparkle(draw, tx - 32, ty + 16, radius=11, color=(247, 223, 148))
    draw_sparkle(draw, tx + tw + 32, ty + 16, radius=11, color=(247, 223, 148))


def build_hub_standee(config, bg_img, output_filenames=["table_standee_printable.png", "standee_front_printable.png"]):
    """
    Generate the 300 DPI Primary Table Standee with luxury circular-dot QR code and Awadh branding.
    """
    w, h = 1200, 1800
    canvas = bg_img.copy()
    draw = ImageDraw.Draw(canvas)
    draw_indri_luxury_borders(draw, w, h)
    draw_brand_header(canvas, draw, w, config)

    font_cta = get_font(46, bold=True)
    font_pill = get_font(22, bold=True)

    cta_text = "SCAN TO CONNECT"
    bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 492), cta_text, fill=(255, 255, 255), font=font_cta)

    label_g = "Rate Us on Google"
    label_i = "Follow Us on Instagram"
    bbox_g = draw.textbbox((0, 0), label_g, font=font_pill)
    bbox_i = draw.textbbox((0, 0), label_i, font=font_pill)

    pill_y = 564
    pill_h = 54
    pill_w_g = (bbox_g[2] - bbox_g[0]) + 84
    pill_w_i = (bbox_i[2] - bbox_i[0]) + 84
    gap = 24
    total_pills_w = pill_w_g + gap + pill_w_i
    start_x = int((w - total_pills_w) / 2)

    gx1, gy1 = start_x, pill_y
    gx2, gy2 = gx1 + pill_w_g, pill_y + pill_h
    draw.rounded_rectangle([gx1, gy1, gx2, gy2], radius=27, fill=(12, 18, 32), outline=(212, 175, 55), width=2)
    draw_google_g_icon(draw, gx1 + 34, gy1 + pill_h // 2, radius=13)
    draw.text((gx1 + 60, gy1 + 14), label_g, fill=(255, 255, 255), font=font_pill)

    ix1, iy1 = gx2 + gap, pill_y
    ix2, iy2 = ix1 + pill_w_i, pill_y + pill_h
    draw.rounded_rectangle([ix1, iy1, ix2, iy2], radius=27, fill=(12, 18, 32), outline=(212, 175, 55), width=2)
    draw_instagram_icon(draw, ix1 + 34, iy1 + pill_h // 2, size=24)
    draw.text((ix1 + 60, iy1 + 14), label_i, fill=(255, 255, 255), font=font_pill)

    qr_url = config.get("landingPageUrl", "https://hospitalityqr.github.io/Awadh-qr/?v=1")
    card_size = 752
    qr_size = 674
    qr_img = generate_styled_qr(qr_url, target_size=qr_size)

    card_x = int((w - card_size) / 2)
    card_y = 656

    shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    sdraw.rounded_rectangle(
        [card_x - 4, card_y + 8, card_x + card_size + 4, card_y + card_size + 16],
        radius=28,
        fill=(0, 0, 0, 140)
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=16))
    canvas_rgba = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer)
    canvas = canvas_rgba.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_size, card_y + card_size],
        radius=26,
        fill=(255, 255, 255),
        outline=(212, 175, 55),
        width=4
    )
    canvas.paste(qr_img, (card_x + (card_size - qr_size) // 2, card_y + (card_size - qr_size) // 2))

    draw_footer(canvas, draw, config, w)

    for fn in output_filenames:
        canvas.save(fn, quality=95, dpi=(300, 300))
        print(f"[OK] Generated {fn} (300 DPI)")


def build_dual_direct_standee(config, bg_img, output_filename="standee_dual_direct_static.png"):
    """
    Generate 300 DPI Dual Direct Static Standee with both direct Google & Instagram QR codes.
    """
    w, h = 1200, 1800
    canvas = bg_img.copy()
    draw = ImageDraw.Draw(canvas)
    draw_indri_luxury_borders(draw, w, h)
    draw_brand_header(canvas, draw, w, config)

    font_cta = get_font(42, bold=True)
    font_sub_cta = get_font(23, bold=True)
    font_card_head_g = get_font(23, bold=True)
    font_card_head_i = get_font(21, bold=True)
    font_card_sub = get_font(19, bold=True)
    font_feature_title = get_font(23, bold=True)
    font_feature_item = get_font(21, bold=False)

    cta_text = "SCAN TO CONNECT DIRECTLY"
    bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 486), cta_text, fill=(255, 255, 255), font=font_cta)

    sub_cta = "Point Your Camera Directly At Either QR Below  •  Instant Open"
    bbox = draw.textbbox((0, 0), sub_cta, font=font_sub_cta)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 542), sub_cta, fill=(247, 223, 148), font=font_sub_cta)

    google_url = config.get("googleReviewUrl", "https://www.google.com/gasearch?q=awadh%20restaurant")
    insta_url = config.get("instagramUrl", "https://www.instagram.com/awadh_restaurant__?stkn=ODdiYTBwdDdna3Q1")
    insta_handle = config.get("instagramHandle", "@awadh_restaurant__").upper()

    qr_g = generate_styled_qr(google_url, target_size=404)
    qr_i = generate_styled_qr(insta_url, target_size=404)

    card_w, card_h = 475, 572
    left_x = 100
    right_x = w - 100 - card_w
    cards_y = 604

    # Left Card: Rate Us on Google
    draw.rounded_rectangle([left_x, cards_y, left_x + card_w, cards_y + card_h], radius=24, fill=(255, 255, 255), outline=(212, 175, 55), width=4)
    draw.rounded_rectangle([left_x + 22, cards_y + 18, left_x + card_w - 22, cards_y + 72], radius=27, fill=(12, 18, 32), outline=(212, 175, 55), width=2)
    draw_google_g_icon(draw, left_x + 56, cards_y + 45, radius=13)
    draw.text((left_x + 84, cards_y + 32), "Rate Us on Google", fill=(255, 255, 255), font=font_card_head_g)
    canvas.paste(qr_g, (left_x + (card_w - 404) // 2, cards_y + 88))
    draw_5_stars_row(draw, left_x + 76, cards_y + 522, star_radius=8, spacing=20, color=(218, 165, 32))
    draw.text((left_x + 182, cards_y + 511), "RATE US ON GOOGLE", fill=(12, 18, 32), font=font_card_sub)

    # Right Card: Follow Us on Instagram
    draw.rounded_rectangle([right_x, cards_y, right_x + card_w, cards_y + card_h], radius=24, fill=(255, 255, 255), outline=(212, 175, 55), width=4)
    draw.rounded_rectangle([right_x + 22, cards_y + 18, right_x + card_w - 22, cards_y + 72], radius=27, fill=(12, 18, 32), outline=(212, 175, 55), width=2)
    draw_instagram_icon(draw, right_x + 54, cards_y + 45, size=24)
    draw.text((right_x + 80, cards_y + 33), "Follow Us on Instagram", fill=(255, 255, 255), font=font_card_head_i)
    canvas.paste(qr_i, (right_x + (card_w - 404) // 2, cards_y + 88))
    i_foot = f"FOLLOW {insta_handle}"
    bbox = draw.textbbox((0, 0), i_foot, font=font_card_sub)
    draw.text((right_x + (card_w - (bbox[2] - bbox[0])) / 2, cards_y + 511), i_foot, fill=(12, 18, 32), font=font_card_sub)

    # Luxury Hospitality Highlights Strip
    feat_x1, feat_y1 = 82, 1218
    feat_x2, feat_y2 = w - 82, 1412
    glass = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glass)
    gdraw.rounded_rectangle([feat_x1, feat_y1, feat_x2, feat_y2], radius=16, fill=(9, 13, 24, 225), outline=(212, 175, 55, 255), width=2)
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), glass).convert("RGB"))
    draw = ImageDraw.Draw(canvas)

    ft_head = "100% PURE VEG  •  AWADH FINE DINE  •  ROYAL AMBIENCE"
    bbox = draw.textbbox((0, 0), ft_head, font=font_feature_title)
    ft_w = bbox[2] - bbox[0]
    ft_x = (w - ft_w) / 2
    draw.text((ft_x, feat_y1 + 22), ft_head, fill=(247, 223, 148), font=font_feature_title)
    draw_sparkle(draw, ft_x - 28, feat_y1 + 35, radius=10, color=(247, 223, 148))
    draw_sparkle(draw, ft_x + ft_w + 28, feat_y1 + 35, radius=10, color=(247, 223, 148))

    ft_line1 = "Authentic Awadhi & North Indian Cuisine  •  Poolside & Chandelier Hall"
    bbox = draw.textbbox((0, 0), ft_line1, font=font_feature_item)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, feat_y1 + 74), ft_line1, fill=(255, 255, 255), font=font_feature_item)

    ft_line2 = "\"Experience Royal Taste & Hospitality\"  —  Share Your Review & Tag Us!"
    bbox = draw.textbbox((0, 0), ft_line2, font=font_feature_item)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, feat_y1 + 120), ft_line2, fill=(226, 232, 240), font=font_feature_item)

    draw_footer(canvas, draw, config, w)
    canvas.save(output_filename, quality=95, dpi=(300, 300))
    print(f"[OK] Generated {output_filename} (300 DPI)")


def build_single_direct_standee(config, bg_img, url, mode="google", output_filename="standee_google_direct.png"):
    """
    Generate 300 DPI Single Direct Standee (Google Direct or Instagram Direct).
    """
    w, h = 1200, 1800
    canvas = bg_img.copy()
    draw = ImageDraw.Draw(canvas)
    draw_indri_luxury_borders(draw, w, h)
    draw_brand_header(canvas, draw, w, config)

    font_cta = get_font(44, bold=True)
    font_pill = get_font(24, bold=True)
    insta_handle = config.get("instagramHandle", "@awadh_restaurant__")

    if mode == "google":
        cta_text = "RATE US ON GOOGLE"
        pill_label = "Rate Us on Google  •  5-Star Rating"
    else:
        cta_text = "FOLLOW US ON INSTAGRAM"
        pill_label = f"Follow Us on Instagram  •  {insta_handle}"

    bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 492), cta_text, fill=(255, 255, 255), font=font_cta)

    bbox_p = draw.textbbox((0, 0), pill_label, font=font_pill)
    pill_w = (bbox_p[2] - bbox_p[0]) + 96
    pill_h = 54
    px1 = int((w - pill_w) / 2)
    py1 = 564
    draw.rounded_rectangle([px1, py1, px1 + pill_w, py1 + pill_h], radius=27, fill=(12, 18, 32), outline=(212, 175, 55), width=2)
    if mode == "google":
        draw_google_g_icon(draw, px1 + 38, py1 + pill_h // 2, radius=14)
    else:
        draw_instagram_icon(draw, px1 + 38, py1 + pill_h // 2, size=26)
    draw.text((px1 + 70, py1 + 13), pill_label, fill=(255, 255, 255), font=font_pill)

    card_size = 752
    qr_size = 674
    qr_img = generate_styled_qr(url, target_size=qr_size)
    card_x = int((w - card_size) / 2)
    card_y = 656

    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_size, card_y + card_size],
        radius=26,
        fill=(255, 255, 255),
        outline=(212, 175, 55),
        width=4
    )
    canvas.paste(qr_img, (card_x + (card_size - qr_size) // 2, card_y + (card_size - qr_size) // 2))

    draw_footer(canvas, draw, config, w)
    canvas.save(output_filename, quality=95, dpi=(300, 300))
    print(f"[OK] Generated {output_filename} (300 DPI)")


def build_mobile_landing_preview(config, bg_img, output_filename="mobile_landing_preview.png"):
    """
    Generate a visual preview of the Mobile QR Landing Page (index.html).
    """
    w, h = 1200, 1800
    canvas = bg_img.copy()
    draw = ImageDraw.Draw(canvas)
    draw_indri_luxury_borders(draw, w, h)
    draw_brand_header(canvas, draw, w, config)

    font_card_title = get_font(32, bold=True)
    font_card_desc = get_font(23, bold=False)
    font_card_tag = get_font(22, bold=True)
    font_sec = get_font(22, bold=True)
    insta_handle = config.get("instagramHandle", "@awadh_restaurant__")

    glass = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glass)
    c1_y1, c1_y2 = 496, 702
    c2_y1, c2_y2 = 738, 944
    gdraw.rounded_rectangle([115, c1_y1, w - 115, c1_y2], radius=24, fill=(18, 22, 34, 236), outline=(247, 223, 148, 255), width=3)
    gdraw.rounded_rectangle([115, c2_y1, w - 115, c2_y2], radius=24, fill=(10, 15, 26, 232), outline=(212, 175, 55, 230), width=2)
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), glass).convert("RGB"))
    draw = ImageDraw.Draw(canvas)

    # Google Card Content
    draw.rounded_rectangle([150, c1_y1 + 44, 265, c1_y1 + 159], radius=24, fill=(255, 255, 255), outline=(212, 175, 55), width=2)
    draw_google_g_icon(draw, 207, c1_y1 + 101, radius=34)
    draw.text((300, c1_y1 + 38), "Rate Us on Google", fill=(255, 255, 255), font=font_card_title)
    draw.text((300, c1_y1 + 86), "Share your dining experience with us", fill=(203, 213, 225), font=font_card_desc)
    draw_5_stars_row(draw, 310, c1_y1 + 143, star_radius=10, spacing=26, color=(251, 191, 36))
    draw.text((445, c1_y1 + 131), "Tap to Review", fill=(247, 223, 148), font=font_card_tag)
    ax1, ay1 = w - 183, c1_y1 + 103
    draw.ellipse([ax1 - 32, ay1 - 32, ax1 + 32, ay1 + 32], fill=(212, 175, 55), outline=(247, 223, 148), width=2)
    draw.line([ax1 - 12, ay1, ax1 + 10, ay1], fill=(9, 13, 24), width=3)
    draw.line([ax1 + 2, ay1 - 9, ax1 + 11, ay1], fill=(9, 13, 24), width=3)
    draw.line([ax1 + 2, ay1 + 9, ax1 + 11, ay1], fill=(9, 13, 24), width=3)

    # Instagram Card Content
    draw.rounded_rectangle([150, c2_y1 + 44, 265, c2_y1 + 159], radius=24, fill=(214, 41, 118), outline=(247, 223, 148), width=2)
    draw_instagram_icon(draw, 207, c2_y1 + 101, size=64)
    draw.text((300, c2_y1 + 38), "Follow Us on Instagram", fill=(255, 255, 255), font=font_card_title)
    draw.text((300, c2_y1 + 86), "Explore royal delicacies, reels & fine dining vibes", fill=(203, 213, 225), font=font_card_desc)
    draw.text((300, c2_y1 + 131), insta_handle, fill=(247, 223, 148), font=font_card_tag)
    ax2, ay2 = w - 183, c2_y1 + 103
    draw.ellipse([ax2 - 32, ay2 - 32, ax2 + 32, ay2 + 32], fill=(16, 24, 42), outline=(212, 175, 55), width=2)
    draw.line([ax2 - 12, ay2, ax2 + 10, ay2], fill=(247, 223, 148), width=3)
    draw.line([ax2 + 2, ay2 - 9, ax2 + 11, ay2], fill=(247, 223, 148), width=3)
    draw.line([ax2 + 2, ay2 + 9, ax2 + 11, ay2], fill=(247, 223, 148), width=3)

    # Ambience Showcase Strip
    sec_label = "OUR ROYAL FINE DINE AMBIENCE  •  AWADH"
    bbox = draw.textbbox((0, 0), sec_label, font=font_sec)
    sw = bbox[2] - bbox[0]
    sx = (w - sw) / 2
    draw.text((sx, 1004), sec_label, fill=(247, 223, 148), font=font_sec)
    draw_sparkle(draw, sx - 24, 1017, radius=9, color=(247, 223, 148))
    draw_sparkle(draw, sx + sw + 24, 1017, radius=9, color=(247, 223, 148))

    thumb_w, thumb_h = 302, 354
    thumb_gap = 32
    t_start_x = int((w - (thumb_w * 3 + thumb_gap * 2)) / 2)
    t_y = 1054
    for idx, fn in enumerate(["ambience_1.jpg", "ambience_2.jpg", "ambience_3.jpg"]):
        tx = t_start_x + idx * (thumb_w + thumb_gap)
        if os.path.exists(fn):
            im = Image.open(fn).convert("RGB")
            iw, ih = im.size
            s_r = iw / ih
            t_r = thumb_w / thumb_h
            if s_r > t_r:
                nw = int(ih * t_r)
                left = (iw - nw) // 2
                im = im.crop((left, 0, left + nw, ih))
            else:
                nh = int(iw / t_r)
                top = (ih - nh) // 2
                im = im.crop((0, top, iw, top + nh))
            im = im.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            canvas.paste(im, (tx, t_y))
            draw.rounded_rectangle([tx, t_y, tx + thumb_w, t_y + thumb_h], radius=16, outline=(212, 175, 55), width=3)

    draw_footer(canvas, draw, config, w)
    canvas.save(output_filename, quality=95)
    print(f"[OK] Generated {output_filename}")


def sync_html_files(config, config_path="config.js"):
    """
    Bake config.js values and deterministic cache-buster version (?v=<hash>)
    into index.html and standee.html so browser & CDN caches never serve stale content.
    """
    ver = "1"
    if os.path.exists(config_path):
        with open(config_path, "rb") as f:
            ver = hashlib.md5(f.read()).hexdigest()[:8]

    name = config.get("name", "Awadh Fine Dine Restaurant")
    subname = config.get("subname", "AWADH FINE DINE RESTAURANT")
    tagline = config.get("tagline", "100% PURE VEG • ROYAL FAMILY DINING • RAU, INDORE")
    highlight = config.get("highlight", "Royal Awadhi, North Indian & Global Family Dining")
    addr = config.get("addressPrimary", "NH 3, Agra-Mumbai Highway, Near Maharana Pratap Bridge, Pigdamber, Rau, Indore")
    phone = config.get("phone", "9035170841")
    clean_phone = re.sub(r"\s+", "", phone)
    phone_disp = config.get("phoneDisplay") or phone
    g_url = config.get("googleReviewUrl", "")
    i_url = config.get("instagramUrl", "")
    i_handle = config.get("instagramHandle", "@awadh_restaurant__")

    # 1. Sync index.html
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()
        html = re.sub(r'(<title id="pageTitle">).*?(</title>)', lambda m: f"{m.group(1)}{name} | Rate Us on Google & Follow Us on Instagram{m.group(2)}", html)
        html = re.sub(r'(<div class="brand-subname" id="uiSubname">).*?(</div>)', lambda m: f"{m.group(1)}{subname}{m.group(2)}", html)
        html = re.sub(r'(<span id="uiTagline">).*?(</span>)', lambda m: f"{m.group(1)}{tagline}{m.group(2)}", html)
        html = re.sub(r'(<div class="address-line" id="uiHighlight">).*?(</div>)', lambda m: f"{m.group(1)}{highlight}{m.group(2)}", html)
        html = re.sub(r'(<div class="address-line" id="uiAddressPrimary">).*?(</div>)', lambda m: f"{m.group(1)}{addr}{m.group(2)}", html)
        html = re.sub(r'(<a href="tel:)[^"]*(" class="phone-link" id="uiPhoneLink">)', lambda m: f"{m.group(1)}{clean_phone}{m.group(2)}", html)
        html = re.sub(r'(<span id="uiPhoneText">).*?(</span>)', lambda m: f"{m.group(1)}Call / Reservation: {phone_disp}{m.group(2)}", html)
        html = re.sub(r'(<div class="insta-handle" id="uiInstaHandle">).*?(</div>)', lambda m: f"{m.group(1)}{i_handle}{m.group(2)}", html)
        if g_url:
            html = re.sub(r'(<a href=")[^"]*(" target="_blank" rel="noopener noreferrer" class="action-card primary-card" id="googleCard">)', lambda m: f"{m.group(1)}{g_url}{m.group(2)}", html)
        if i_url:
            html = re.sub(r'(<a href=")[^"]*(" target="_blank" rel="noopener noreferrer" class="action-card" id="instaCard">)', lambda m: f"{m.group(1)}{i_url}{m.group(2)}", html)
        html = re.sub(r'config\.js\?v=[a-zA-Z0-9_]+', f'config.js?v={ver}', html)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[OK] Synced index.html with config.js (v={ver})")

    # 2. Sync standee.html
    if os.path.exists("standee.html"):
        with open("standee.html", "r", encoding="utf-8") as f:
            shtml = f.read()
        shtml = re.sub(r'(<div class="standee-subname" id="stSubname">).*?(</div>)', lambda m: f"{m.group(1)}{subname}{m.group(2)}", shtml)
        shtml = re.sub(r'(<div class="standee-location" id="stTagline">).*?(</div>)', lambda m: f"{m.group(1)}{tagline}{m.group(2)}", shtml)
        shtml = re.sub(r'(<span id="stHighlight">).*?(</span>)', lambda m: f"{m.group(1)}{highlight}{m.group(2)}", shtml)
        shtml = re.sub(r'(<span id="stAddress">).*?(</span>)', lambda m: f"{m.group(1)}{addr}{m.group(2)}", shtml)
        shtml = re.sub(r'(<div class="standee-phone" id="stPhone">).*?(</div>)', lambda m: f"{m.group(1)}Call / Reservation: {phone_disp}{m.group(2)}", shtml)
        shtml = re.sub(r'(<div class="dual-qr-foot" id="stInstaFoot">).*?(</div>)', lambda m: f"{m.group(1)}{i_handle.upper()}{m.group(2)}", shtml)
        shtml = re.sub(r'config\.js\?v=[a-zA-Z0-9_]+', f'config.js?v={ver}', shtml)
        with open("standee.html", "w", encoding="utf-8") as f:
            f.write(shtml)
        print(f"[OK] Synced standee.html with config.js (v={ver})")


def main():
    assets_ready = all(os.path.exists(f) for f in [
        "awadh_title.png", "logo_with_gold_rim.png", "logo.png",
        "ambience_1.jpg", "ambience_2.jpg", "ambience_3.jpg", "ambience_4.jpg"
    ])
    if not assets_ready:
        print("Preparing Awadh Fine Dine Restaurant brand logos and architectural photos...")
        prepare_brand_assets()

    config = load_config("config.js")
    sync_html_files(config, "config.js")

    landing_url = config.get("landingPageUrl", "https://hospitalityqr.github.io/Awadh-qr/?v=1")
    google_url = config.get("googleReviewUrl", "https://www.google.com/gasearch?q=awadh%20restaurant")
    insta_url = config.get("instagramUrl", "https://www.instagram.com/awadh_restaurant__?stkn=ODdiYTBwdDdna3Q1")

    print("Loaded URLs:")
    print(" - Landing:", landing_url)
    print(" - Google :", google_url[:80] + "...")
    print(" - Insta  :", insta_url)

    if os.path.exists("bg_ambience_luxury.jpg"):
        bg_img = Image.open("bg_ambience_luxury.jpg").convert("RGB")
    else:
        print("Generating shared Awadh Luxury Ambience Background...")
        bg_img = create_ambience_luxury_background(1200, 1800)
        bg_img.save("bg_ambience_luxury.jpg", quality=93)
        print("[OK] Saved bg_ambience_luxury.jpg")

    print("Generating standalone high-res luxury QR codes...")
    qr_hub = generate_styled_qr(landing_url, target_size=800)
    qr_hub.save("qr_code.png")
    qr_hub.save("qr_landing_page.png")

    qr_google = generate_styled_qr(google_url, target_size=800)
    qr_google.save("qr_google_direct.png")

    qr_insta = generate_styled_qr(insta_url, target_size=800)
    qr_insta.save("qr_instagram_direct.png")
    print("[OK] Generated qr_code.png, qr_landing_page.png, qr_google_direct.png, qr_instagram_direct.png")

    build_hub_standee(config, bg_img, ["table_standee_printable.png", "standee_front_printable.png"])
    build_dual_direct_standee(config, bg_img, "standee_dual_direct_static.png")
    build_single_direct_standee(config, bg_img, google_url, mode="google", output_filename="standee_google_direct.png")
    build_single_direct_standee(config, bg_img, insta_url, mode="instagram", output_filename="standee_instagram_direct.png")
    build_mobile_landing_preview(config, bg_img, "mobile_landing_preview.png")


if __name__ == "__main__":
    main()
