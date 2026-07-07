"""Download the uploads of a FREE itch.io project into asset_library/<name>/.

itch.io flow for free projects: the game page embeds a csrf_token and its upload ids;
POSTing <game_url>/file/<upload_id> with that token returns a signed URL. No login needed
for free/no-minimum projects (paid ones 404 here — buy in a browser instead).

Usage: python tools/fetch_itch_asset.py <game_url> <dest_subdir> [name_filter]
"""
import re
import sys
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}


def fetch(game_url: str, dest: Path, name_filter: str = "") -> None:
    s = requests.Session()
    s.headers.update(UA)
    page = s.get(game_url, timeout=30)
    page.raise_for_status()
    html = page.text
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html) or \
        re.search(r'csrf_token"?\s*[:=]\s*"([^"]+)"', html)
    if not m:
        raise SystemExit(f"no csrf token on {game_url} (paid project? login wall?)")
    csrf = m.group(1)

    def parse_uploads(doc: str):
        found = []
        for um in re.finditer(r'data-upload_id="(\d+)".*?class="name"[^>]*title="([^"]+)"',
                              doc, re.S):
            found.append((um.group(1), um.group(2)))
        if not found:  # fallback: ids only
            found = [(uid, f"upload_{uid}.bin")
                     for uid in dict.fromkeys(re.findall(r'data-upload_id="(\d+)"', doc))]
        return found

    uploads = parse_uploads(html)
    if not uploads:
        # "Name your price" projects hide uploads behind the donation modal: POST download_url
        # (the "No thanks, just take me to the downloads" path) and parse the download page.
        r = s.post(f"{game_url}/download_url", data={"csrf_token": csrf}, timeout=30)
        r.raise_for_status()
        dl_url = r.json().get("url", "")
        if dl_url:
            dl_page = s.get(dl_url, timeout=30)
            dl_page.raise_for_status()
            uploads = parse_uploads(dl_page.text)
    if not uploads:
        raise SystemExit(f"no uploads found on {game_url}")
    dest.mkdir(parents=True, exist_ok=True)
    for uid, fname in uploads:
        if name_filter and name_filter.lower() not in fname.lower():
            print(f"  skip {fname} (filter)")
            continue
        r = s.post(f"{game_url}/file/{uid}?source=view_game",
                   data={"csrf_token": csrf}, timeout=30)
        r.raise_for_status()
        url = r.json().get("url")
        if not url:
            print(f"  !! no url for upload {uid} ({fname})")
            continue
        out = dest / fname
        with s.get(url, stream=True, timeout=120) as dl:
            dl.raise_for_status()
            with open(out, "wb") as f:
                for chunk in dl.iter_content(1 << 20):
                    f.write(chunk)
        print(f"  {out.name}: {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    game_url = sys.argv[1].rstrip("/")
    sub = sys.argv[2]
    filt = sys.argv[3] if len(sys.argv) > 3 else ""
    root = Path(__file__).resolve().parent.parent / "asset_library" / sub
    print(f"{game_url} -> {root}")
    fetch(game_url, root, filt)
