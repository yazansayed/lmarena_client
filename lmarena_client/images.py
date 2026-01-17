from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Optional, Tuple, Any

import aiohttp


def _is_http_url(s: str) -> bool:
    return isinstance(s, str) and s.startswith(("http://", "https://"))


def _is_data_uri(s: str) -> bool:
    return isinstance(s, str) and s.startswith("data:")


def extract_data_uri(data_uri: str) -> Tuple[Optional[str], bytes]:
    """
    Parse a data URI and return (mime_type, bytes).
    Accepts any base64 data URI; validation is deferred to detect_file_type().
    """
    # Example: data:image/png;base64,AAAA
    header, _, b64 = data_uri.partition(",")
    mime = None
    if ";" in header:
        mime = header[5:].split(";", 1)[0] or None
    return mime, base64.b64decode(b64)


def detect_file_type(binary_data: bytes) -> tuple[str, str]:
    """
    Detect file type from magic number / header signature.
    Returns (extension, MIME type).
    """
    # ---- Images ----
    if binary_data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    elif binary_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    elif binary_data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    elif binary_data.startswith(b"RIFF") and binary_data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    elif binary_data.startswith(b"BM"):
        return ".bmp", "image/bmp"
    elif binary_data.startswith(b"II*\x00") or binary_data.startswith(b"MM\x00*"):
        return ".tiff", "image/tiff"
    elif binary_data.lstrip().startswith((b"<?xml", b"<svg")):
        return ".svg", "image/svg+xml"

    # ---- Documents (not expected for LMArena uploads, but kept permissive) ----
    elif binary_data.startswith(b"%PDF"):
        return ".pdf", "application/pdf"
    elif binary_data.startswith(b"PK\x03\x04"):
        return ".zip", "application/zip"

    # ---- Audio ----
    elif binary_data.startswith(b"ID3") or binary_data[0:2] == b"\xff\xfb":
        return ".mp3", "audio/mpeg"
    elif binary_data.startswith(b"OggS"):
        return ".ogg", "audio/ogg"
    elif binary_data.startswith(b"fLaC"):
        return ".flac", "audio/flac"
    elif binary_data.startswith(b"RIFF") and binary_data[8:12] == b"WAVE":
        return ".wav", "audio/wav"

    # ---- Text-ish fallback ----
    elif binary_data.lstrip().startswith((b"{", b"[")):
        return ".json", "application/json"
    elif binary_data.lstrip().startswith((b"<", b"<!DOCTYPE")):
        return ".html", "text/html"
    elif all(32 <= b <= 127 or b in (9, 10, 13) for b in binary_data[:100]):
        return ".txt", "text/plain"

    raise ValueError("Unknown or unsupported file type")


def to_bytes_sync(obj: Any) -> bytes:
    """
    Synchronous conversion to bytes:
    - bytes -> bytes
    - data: URI -> decoded bytes
    - Path / os.PathLike -> file bytes
    - file-like -> read()
    Does NOT fetch http(s) URLs (use to_bytes_async).
    """
    if obj is None:
        raise ValueError("media is None")

    if isinstance(obj, bytes):
        return obj

    if isinstance(obj, str):
        if _is_data_uri(obj):
            _, data = extract_data_uri(obj)
            return data
        if _is_http_url(obj):
            raise ValueError("HTTP URL provided; use to_bytes_async() to fetch it.")
        # treat as local path
        p = Path(obj)
        return p.read_bytes()

    if isinstance(obj, (os.PathLike, Path)):
        return Path(obj).read_bytes()

    # file-like
    try:
        if hasattr(obj, "read"):
            try:
                obj.seek(0)
            except Exception:
                pass
            data = obj.read()
            if isinstance(data, str):
                data = data.encode()
            return data
    except Exception:
        pass

    raise ValueError(f"Unsupported media type: {type(obj).__name__}")


async def to_bytes_async(obj: Any, *, session: aiohttp.ClientSession | None = None) -> bytes:
    """
    Async conversion to bytes. Adds support for http(s) URLs via aiohttp.
    """
    if isinstance(obj, str) and _is_http_url(obj):
        close_session = False
        if session is None:
            timeout = aiohttp.ClientTimeout(total=60)
            session = aiohttp.ClientSession(timeout=timeout)
            close_session = True
        try:
            async with session.get(
                obj,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    )
                },
            ) as resp:
                resp.raise_for_status()
                return await resp.read()
        finally:
            if close_session:
                await session.close()

    return to_bytes_sync(obj)


def ensure_filename(filename: Optional[str], *, default_stem: str = "file") -> str:
    if filename and isinstance(filename, str) and filename.strip():
        return filename.strip()
    return default_stem
