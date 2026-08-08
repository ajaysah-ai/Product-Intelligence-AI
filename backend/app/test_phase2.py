"""
Run after the backend is up:
    docker compose exec backend python -m app.test_phase2

Exits non-zero if any check fails.
"""
import io
import sys

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
results = []


def check(description, passed):
    results.append((description, passed))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {description}")


# Minimal valid magic-byte headers so filetype.guess() detects them correctly.
MINIMAL_PDF = b"%PDF-1.4\n%%EOF"
MINIMAL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def main():
    # 1) Text-only request -> 200, row created
    r = client.post("/submit", data={"text": "A wireless mechanical keyboard with hot-swappable switches"})
    check("text-only request -> 200", r.status_code == 200)
    check("text-only response has request_id", r.status_code == 200 and "request_id" in r.json())

    # 2) Text + 1 file -> 200, file saved
    r = client.post(
        "/submit",
        data={"text": "Product with one spec sheet"},
        files={"files": ("spec.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")},
    )
    check("text+1 file -> 200", r.status_code == 200)
    check(
        "text+1 file -> file accepted in response",
        r.status_code == 200 and r.json().get("accepted_files") == ["spec.pdf"],
    )

    # 3) Text + multi files -> 200, all saved
    r = client.post(
        "/submit",
        data={"text": "Product with multiple docs"},
        files=[
            ("files", ("spec.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")),
            ("files", ("photo.png", io.BytesIO(MINIMAL_PNG), "image/png")),
            ("files", ("notes.txt", io.BytesIO(b"plain text notes about the product"), "text/plain")),
        ],
    )
    check("text+multi files -> 200", r.status_code == 200)
    check(
        "text+multi files -> all 3 accepted",
        r.status_code == 200 and len(r.json().get("accepted_files", [])) == 3,
    )

    # 4) Oversized file -> 413
    oversized = b"0" * (26 * 1024 * 1024)  # 26MB, over the 25MB default limit
    r = client.post(
        "/submit",
        data={"text": "oversized test"},
        files={"files": ("big.txt", io.BytesIO(oversized), "text/plain")},
    )
    check("oversized file -> 413", r.status_code == 413)

    # 5) Disallowed file type -> 400
    r = client.post(
        "/submit",
        data={"text": "malicious upload test"},
        files={"files": ("virus.exe", io.BytesIO(b"MZ\x90\x00fake exe content"), "application/octet-stream")},
    )
    check("disallowed .exe file -> 400", r.status_code == 400)

    # 6) Empty text + no file -> 400
    r = client.post("/submit", data={})
    check("empty text + no file -> 400", r.status_code == 400)

    # Bonus: MIME mismatch (PNG bytes renamed as .pdf) -> 400
    r = client.post(
        "/submit",
        data={"text": "spoofed extension test"},
        files={"files": ("fake.pdf", io.BytesIO(MINIMAL_PNG), "application/pdf")},
    )
    check("bonus: PNG content renamed to .pdf -> 400 (signature mismatch)", r.status_code == 400)

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
