"""Token metadata upload helper.

Posts a token's name/symbol/description/social links plus an image to an
IPFS-facing metadata endpoint (config.IPFS_API by default) and prints the
resulting metadata URI. Standard library only: multipart/form-data is
built by hand with urllib.

Usage:
    python upload_metadata.py --image ./logo.png --name "Name" \
        --symbol "SYM" [--description ...] [--twitter ...] \
        [--telegram ...] [--website ...] [--api ...]
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import config

_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _field_part(boundary: str, name: str, value: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode("utf-8")


def _file_part(boundary: str, name: str, filename: str, content_type: str, data: bytes) -> bytes:
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    return head + data + b"\r\n"


def build_multipart(boundary: str, metadata: dict, image_path: Path) -> bytes:
    content_type = _IMAGE_TYPES.get(image_path.suffix.lower(), "application/octet-stream")
    chunks = [_field_part(boundary, key, value) for key, value in metadata.items()]
    chunks.append(
        _file_part(boundary, "file", image_path.name, content_type, image_path.read_bytes())
    )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


def upload_metadata(image_path, metadata: dict, api_url=None):
    """POST image + metadata; return the resulting metadata URI or None."""
    image = Path(image_path)
    api_url = api_url or config.IPFS_API
    boundary = "----TrackerForm" + uuid.uuid4().hex
    request = urllib.request.Request(
        api_url,
        data=build_multipart(boundary, metadata, image),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as exc:
        print(f"upload failed: {exc}", file=sys.stderr)
        return None

    uri = payload.get("metadataUri") or payload.get("uri")
    if uri:
        print(f"metadata uri: {uri}")
        return uri
    print(f"unexpected response: {payload}", file=sys.stderr)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="upload token metadata to IPFS")
    parser.add_argument("--image", required=True, help="path to the token image")
    parser.add_argument("--name", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--twitter", default="")
    parser.add_argument("--telegram", default="")
    parser.add_argument("--website", default="")
    parser.add_argument("--api", default=None, help="metadata endpoint override")
    args = parser.parse_args()

    metadata = {
        "name": args.name,
        "symbol": args.symbol,
        "description": args.description,
        "showName": "true",
    }
    for key in ("twitter", "telegram", "website"):
        value = getattr(args, key)
        if value:
            metadata[key] = value

    return 0 if upload_metadata(args.image, metadata, args.api) else 1


if __name__ == "__main__":
    raise SystemExit(main())
