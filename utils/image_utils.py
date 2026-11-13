import io

MAX_UPLOAD_MB = 5
MAX_SIDE_PIXELS = 800
ALLOWED_TYPES = ["jpg", "jpeg", "png", "webp"]

def prepare_food_image(uploaded_file):
    """Convert an uploaded photo into a small JPEG (bytes).

    The photo is resized to at most 800x800 pixels so the database stays
    small and the menu loads fast.

    Returns (image_bytes, None) or (None, "error message").
    """
    if uploaded_file is None:
        return None, None
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        return None, f"Photo is too big. Maximum size is {MAX_UPLOAD_MB} MB."
    try:
        from PIL import Image, ImageOps
        image = Image.open(io.BytesIO(raw))
        # fix phone photos that are rotated
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        image.thumbnail((MAX_SIDE_PIXELS, MAX_SIDE_PIXELS))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=True)
        return output.getvalue(), None
    except Exception:
        return None, "This file is not a valid image. Use JPG, PNG or WEBP."

def prepare_payment_screenshot(uploaded_file):
    """Prepare a UPI payment screenshot.

    Returns (jpeg_bytes, sha256_of_original_file, None)
    or (None, None, "error message").
    """
    import hashlib
    if uploaded_file is None:
        return None, None, None
    raw = uploaded_file.getvalue()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        return None, None, (f"Screenshot is too big. Maximum size is {MAX_UPLOAD_MB} MB.")
    try:
        from PIL import Image, ImageOps
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        image.thumbnail((1200, 1200))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=80, optimize=True)
        return (output.getvalue(), hashlib.sha256(raw).hexdigest(), None)
    except Exception:
        return None, None, ("This file is not a valid image. Use a JPG, PNG or WEBP " "screenshot.")
