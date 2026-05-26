import json

from scripts.seed import seed, SEEDS


class _MockResponse:
    def __init__(self, content=b"", json_data=None):
        self.content = content
        self._json = json_data or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _MockClient:
    def __init__(self, upload_status="ok"):
        self.get_calls = []
        self.post_calls = []
        self._upload_status = upload_status

    def get(self, url, **kwargs):
        self.get_calls.append(str(url))
        return _MockResponse(content=b"FAKEIMAGE")

    def post(self, url, **kwargs):
        self.post_calls.append({"url": str(url), **kwargs})
        return _MockResponse(json_data={"status": self._upload_status})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_seed_downloads_each_picsum_url():
    client = _MockClient()
    seed(client=client)
    for entry in SEEDS:
        assert any(entry["picsum_url"] in url for url in client.get_calls)


def test_seed_uploads_three_photos():
    client = _MockClient()
    seed(client=client)
    assert len(client.post_calls) == 3


def test_seed_posts_to_photos_endpoint():
    client = _MockClient()
    seed(backend_url="http://backend:8000", client=client)
    for call in client.post_calls:
        assert call["url"] == "http://backend:8000/photos"


def test_seed_uploads_correct_filenames():
    client = _MockClient()
    seed(client=client)
    uploaded_filenames = set()
    for call in client.post_calls:
        files = call["files"]
        uploaded_filenames.add(files["image"][0])
    for entry in SEEDS:
        assert entry["filename"] in uploaded_filenames


def test_seed_metadata_has_required_fields():
    client = _MockClient()
    seed(client=client)
    for call in client.post_calls:
        meta_bytes = call["files"]["metadata"][1]
        meta = json.loads(meta_bytes)
        assert "filename" in meta
        assert "captured_at" in meta


def test_seed_metadata_filename_matches_image():
    client = _MockClient()
    seed(client=client)
    for call in client.post_calls:
        files = call["files"]
        image_filename = files["image"][0]
        meta = json.loads(files["metadata"][1])
        assert meta["filename"] == image_filename


def test_seed_does_not_error_on_duplicate_status():
    client = _MockClient(upload_status="duplicate")
    seed(client=client)  # should not raise
