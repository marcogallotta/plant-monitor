#!/usr/bin/env python3
"""Dev seed script: downloads 3 Picsum placeholder images and uploads them to the backend."""

import argparse
import json

import httpx

SEEDS = [
    {
        "picsum_url": "https://picsum.photos/seed/plant-test-001/1920/1080",
        "filename": "2026-05-26T100000Z.jpg",
        "captured_at": "2026-05-26T10:00:00Z",
    },
    {
        "picsum_url": "https://picsum.photos/seed/plant-test-002/1920/1080",
        "filename": "2026-05-26T110000Z.jpg",
        "captured_at": "2026-05-26T11:00:00Z",
    },
    {
        "picsum_url": "https://picsum.photos/seed/plant-test-003/1920/1080",
        "filename": "2026-05-26T120000Z.jpg",
        "captured_at": "2026-05-26T12:00:00Z",
    },
]


def seed(backend_url: str = "http://localhost:8000", client: httpx.Client = None) -> None:
    own_client = client is None
    if own_client:
        client = httpx.Client()
    try:
        for entry in SEEDS:
            print(f"Downloading {entry['picsum_url']} ...")
            resp = client.get(entry["picsum_url"], follow_redirects=True)
            resp.raise_for_status()

            stem = entry["filename"].removesuffix(".jpg")
            metadata = {"filename": entry["filename"], "captured_at": entry["captured_at"]}

            print(f"Uploading {entry['filename']} ...")
            upload = client.post(
                f"{backend_url}/photos",
                files={
                    "image": (entry["filename"], resp.content, "image/jpeg"),
                    "metadata": (f"{stem}.json", json.dumps(metadata).encode(), "application/json"),
                },
            )
            upload.raise_for_status()
            print(f"  → {upload.json()['status']}")
    finally:
        if own_client:
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://localhost:8000")
    args = parser.parse_args()
    seed(backend_url=args.backend_url)
