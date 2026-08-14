import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


PLAYLIST_FILE = Path("Playlist.m3u")
REPORT_FILE = Path("playlist_report.txt")
STATUS_FILE = Path("playlist_status.json")

TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def load_status():
    if not STATUS_FILE.exists():
        return {}

    try:
        return json.loads(
            STATUS_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def save_status(status_data):
    STATUS_FILE.write_text(
        json.dumps(
            status_data,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def get_entries():
    if not PLAYLIST_FILE.exists():
        raise SystemExit("Playlist.m3u not found")

    lines = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
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
        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        if status_code >= 400:
            response.close()

            return {
                "status": "HTTP_ERROR",
                "detail": f"HTTP {status_code}",
            }

        is_m3u8_url = ".m3u8" in url.lower()

        sample = b""

        try:
            for chunk in response.iter_content(
                chunk_size=4096
            ):
                sample += chunk

                if len(sample) >= 16384:
                    break
        finally:
            response.close()

        sample_text = sample.decode(
            "utf-8",
            errors="ignore",
        )

        looks_like_hls = (
            "#EXTM3U" in sample_text
            or "#EXT-X-" in sample_text
            or "application/vnd.apple.mpegurl"
            in content_type.lower()
            or "application/x-mpegurl"
            in content_type.lower()
        )

        if looks_like_hls:
            return {
                "status": "OK",
                "detail": (
                    f"HTTP {status_code}, "
                    "HLS playlist"
                ),
            }

        if is_m3u8_url:
            return {
                "status": "SUSPECT",
                "detail": (
                    f"HTTP {status_code}, "
                    "URL ends in .m3u8 but "
                    "response does not look like HLS"
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


def classify(status, failures):
    if status == "OK":
        return "WORKING"

    if failures <= 1:
        return "TEMPORARY_FAILURE"

    if failures == 2:
        return "REPEATED_FAILURE"

    return "CONSISTENTLY_BROKEN"


def main():
    entries = get_entries()
    previous_status = load_status()
    new_status = {}

    print(f"Found {len(entries)} playlist URLs.")
    print()

    report = []

    report.append("# Playlist URL Check Report")
    report.append("")
    report.append(f"Checked {len(entries)} URLs")
    report.append(
        time.strftime(
            "Time: %Y-%m-%d %H:%M:%S UTC",
            time.gmtime(),
        )
    )
    report.append("")

    raw_counts = {}
    classification_counts = {}

    for index, entry in enumerate(
        entries,
        start=1,
    ):
        name = entry["name"]
        url = entry["url"]

        print(
            f"[{index}/{len(entries)}] {name}"
        )

        result = check_url(url)

        status = result["status"]
        detail = result["detail"]

        old = previous_status.get(url, {})
        previous_failures = old.get(
            "consecutive_failures",
            0,
        )

        if status == "OK":
            failures = 0
        else:
            failures = previous_failures + 1

        classification = classify(
            status,
            failures,
        )

        new_status[url] = {
            "name": name,
            "last_status": status,
            "last_detail": detail,
            "consecutive_failures": failures,
            "classification": classification,
            "last_checked_utc": time.strftime(
                "%Y-%m-%d %H:%M:%S UTC",
                time.gmtime(),
            ),
        }

        raw_counts[status] = (
            raw_counts.get(status, 0) + 1
        )

        classification_counts[classification] = (
            classification_counts.get(
                classification,
                0,
            )
            + 1
        )

        print(
            f"    {status} | "
            f"{classification} | "
            f"failures={failures}"
        )

        report.extend([
            f"## {name}",
            f"Status: {status}",
            f"Classification: {classification}",
            f"Consecutive failures: {failures}",
            f"Detail: {detail}",
            f"URL: {url}",
            "",
        ])

        time.sleep(0.2)

    save_status(new_status)

    report.extend([
        "# SUMMARY BY STATUS",
        "",
    ])

    for status in sorted(raw_counts):
        report.append(
            f"{status}: {raw_counts[status]}"
        )

    report.extend([
        "",
        "# SUMMARY BY CLASSIFICATION",
        "",
    ])

    for classification in [
        "WORKING",
        "TEMPORARY_FAILURE",
        "REPEATED_FAILURE",
        "CONSISTENTLY_BROKEN",
    ]:
        report.append(
            f"{classification}: "
            f"{classification_counts.get(classification, 0)}"
        )

    REPORT_FILE.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "Report written to playlist_report.txt"
    )
    print(
        "Status history written to "
        "playlist_status.json"
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
