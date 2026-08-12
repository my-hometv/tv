import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


PLAYLIST_FILE = Path("Playlist.m3u")
REPORT_FILE = Path("playlist_report.txt")

TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def get_entries():
    if not PLAYLIST_FILE.exists():
        raise SystemExit("Playlist.m3u not found")

    lines = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace"
    ).splitlines()

    entries = []

    current_name = "Unknown channel"
    current_extinf = ""

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF:"):
            current_extinf = line

            if "," in line:
                current_name = line.split(",", 1)[1].strip()
            else:
                current_name = "Unknown channel"

        elif line and not line.startswith("#"):
            if line.startswith(("http://", "https://")):
                entries.append({
                    "name": current_name,
                    "url": line,
                    "extinf": current_extinf,
                })

                current_name = "Unknown channel"
                current_extinf = ""

    return entries


def check_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return {
            "status": "INVALID",
            "detail": "Unsupported URL scheme",
        }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        status_code = response.status_code
        content_type = response.headers.get("Content-Type", "")

        if status_code >= 400:
            return {
                "status": "HTTP_ERROR",
                "detail": f"HTTP {status_code}",
            }

        # Direct HLS URLs are expected to end in .m3u8.
        is_m3u8_url = ".m3u8" in url.lower()

        # Read only a small amount of the response.
        sample = b""

        try:
            for chunk in response.iter_content(chunk_size=4096):
                sample += chunk
                if len(sample) >= 16384:
                    break
        finally:
            response.close()

        sample_text = sample.decode(
            "utf-8",
            errors="ignore"
        )

        looks_like_hls = (
            "#EXTM3U" in sample_text
            or "#EXT-X-" in sample_text
            or "application/vnd.apple.mpegurl" in content_type.lower()
            or "application/x-mpegurl" in content_type.lower()
        )

        if is_m3u8_url and looks_like_hls:
            return {
                "status": "OK",
                "detail": f"HTTP {status_code}, HLS playlist",
            }

        if is_m3u8_url and not looks_like_hls:
            return {
                "status": "SUSPECT",
                "detail": (
                    f"HTTP {status_code}, "
                    "URL says m3u8 but response does not look like HLS"
                ),
            }

        # URLs without .m3u8 may still be valid, but they are not
        # direct HLS playlist URLs.
        if looks_like_hls:
            return {
                "status": "OK",
                "detail": (
                    f"HTTP {status_code}, "
                    "HLS content detected"
                ),
            }

        return {
            "status": "WEBPAGE_OR_UNKNOWN",
            "detail": (
                f"HTTP {status_code}, "
                "response does not look like HLS"
            ),
        }

    except requests.exceptions.Timeout:
        return {
            "status": "TIMEOUT",
            "detail": f"Timed out after {TIMEOUT}s",
        }

    except requests.exceptions.RequestException as exc:
        return {
            "status": "ERROR",
            "detail": str(exc),
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "detail": str(exc),
        }


def main():
    entries = get_entries()

    print(f"Found {len(entries)} playlist URLs.")
    print()

    report = []
    report.append("Playlist URL Check Report")
    report.append("=" * 80)
    report.append(
        f"Checked {len(entries)} URLs"
    )
    report.append(
        time.strftime(
            "Time: %Y-%m-%d %H:%M:%S UTC",
            time.gmtime()
        )
    )
    report.append("")

    counts = {}

    for index, entry in enumerate(entries, start=1):
        name = entry["name"]
        url = entry["url"]

        print(f"[{index}/{len(entries)}] {name}")

        result = check_url(url)

        status = result["status"]
        detail = result["detail"]

        counts[status] = counts.get(status, 0) + 1

        print(f"    {status}: {detail}")

        report.append(f"CHANNEL: {name}")
        report.append(f"STATUS:  {status}")
        report.append(f"DETAIL:  {detail}")
        report.append(f"URL:     {url}")
        report.append("-" * 80)

        # Small delay to avoid hammering servers.
        time.sleep(0.2)

    report.append("")
    report.append("SUMMARY")
    report.append("=" * 80)

    for status in sorted(counts):
        report.append(
            f"{status}: {counts[status]}"
        )

    REPORT_FILE.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8"
    )

    print()
    print("Report written to playlist_report.txt")

    # The checker itself should not fail the GitHub Action just because
    # individual streams are unavailable.
    sys.exit(0)


if __name__ == "__main__":
    main()
