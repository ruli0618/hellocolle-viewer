"""Face-aware, upper-body-first thumbnail cropping with a safe center fallback."""
from __future__ import annotations

from pathlib import Path
import threading

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2026may.onnx"
LOCAL = threading.local()


def detector():
    if not hasattr(LOCAL, "face_detector"):
        LOCAL.face_detector = cv2.FaceDetectorYN.create(str(MODEL), "", (320, 320), 0.6, 0.3, 5000)
    return LOCAL.face_detector


def crop_thumbnail(source: Path, target: Path, width=360, height=360) -> bool:
    data = np.fromfile(str(source), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return False
    h, w = image.shape[:2]
    scale = min(1.0, 800 / max(h, w))
    small = cv2.resize(image, (round(w * scale), round(h * scale))) if scale < 1 else image
    face_detector = detector()
    face_detector.setInputSize((small.shape[1], small.shape[0]))
    _, faces = face_detector.detect(small)
    if faces is not None and len(faces):
        # Prefer the largest visible face; the crop keeps some torso beneath it.
        x, y, fw, fh = max(faces, key=lambda face: face[2] * face[3])[:4]
        focal_x = (x + fw / 2) / scale
        focal_y = (y + fh / 2) / scale
    else:
        focal_x, focal_y = w / 2, h * 0.34
    ratio = width / height
    if w / h > ratio:
        crop_h, crop_w = h, round(h * ratio)
    else:
        crop_w, crop_h = w, round(w / ratio)
    left = max(0, min(w - crop_w, round(focal_x - crop_w / 2)))
    top = max(0, min(h - crop_h, round(focal_y - crop_h * 0.34)))
    cropped = image[top:top + crop_h, left:left + crop_w]
    resized = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(str(target))
    return True
