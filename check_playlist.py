import json
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
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 "
        "Safari/537.36"
    ),
    "Accept": "*/*",
}


def load_status():
    if not STATUS_FILE.exists():
        return {}

    try:
        return json.loads(
            STATUS_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_status(data):
    STATUS_FILE.write_text(
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def get_entries():
    if not PLAYLIST_FILE.exists():
        raise SystemExit(
            "Playlist.m3u not found"
        )

    lines = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    entries = []
    current_name = "Unknown channel"

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF:"):
            if "," in line:
                current_name = (
                    line.split(",", 1)[1]
                    .strip()
                )

        elif (
            line
            and not line.startswith("#")
            and line.startswith(
                ("http://", "https://")
            )
        ):
            entries.append(
                {
                    "name": current_name,
                    "url": line,
                }
            )

            current_name = (
                "Unknown channel"
            )

    return entries


def check_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in (
        "http",
        "https",
    ):
        return (
            "INVALID",
            "Unsupported URL scheme",
        )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        status_code = (
            response.status_code
        )

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
        )

        if status_code >= 400:
            response.close()

            return (
                "HTTP_ERROR",
                f"HTTP {status_code}",
            )

        sample = b""

        try:
            for chunk in (
                response.iter_content(
                    chunk_size=4096
                )
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
            or
            "application/vnd.apple.mpegurl"
            in content_type.lower()
            or
            "application/x-mpegurl"
            in content_type.lower()
        )

        if looks_like_hls:
            return (
                "OK",
                f"HTTP {status_code}, "
                "HLS playlist",
            )

        if ".m3u8" in url.lower():
            return (
                "SUSPECT",
                f"HTTP {status_code}, "
                "not recognized as HLS",
            )

        return (
            "WEBPAGE_OR_UNKNOWN",
            f"HTTP {status_code}",
        )

    except requests.Timeout:
        return (
            "TIMEOUT",
            f"Timed out after "
            f"{TIMEOUT}s",
        )

    except (
        requests.RequestException
    ) as exc:
        return (
            "ERROR",
            str(exc),
        )


def classify(
    status,
    failures,
):
    if status == "OK":
        return "WORKING"

    if failures == 1:
        return "TEMPORARY_FAILURE"

    if failures == 2:
        return "REPEATED_FAILURE"

    return "CONSISTENTLY_BROKEN"


def main():
    entries = get_entries()

    previous = load_status()
    current = {}

    raw_counts = {}
    class_counts = {}

    report = [
        "# Playlist URL Check Report",
        "",
        f"Checked {len(entries)} URLs",
        time.strftime(
            "Time: %Y-%m-%d "
            "%H:%M:%S UTC",
            time.gmtime(),
        ),
        "",
    ]

    for number, entry in enumerate(
        entries,
        1,
    ):
        name = entry["name"]
        url = entry["url"]

        print(
            f"[{number}/"
            f"{len(entries)}] {name}"
        )

        status, detail = check_url(
            url
        )

        old = previous.get(
            url,
            {},
        )

        previous_failures = old.get(
            "consecutive_failures",
            0,
        )

        if status == "OK":
            failures = 0
        else:
            failures = (
                previous_failures + 1
            )

        classification = classify(
            status,
            failures,
        )

        current[url] = {
            "name": name,
            "last_status": status,
            "last_detail": detail,
            "consecutive_failures":
                failures,
            "classification":
                classification,
            "last_checked_utc":
                time.strftime(
                    "%Y-%m-%d "
                    "%H:%M:%S UTC",
                    time.gmtime(),
                ),
        }

        raw_counts[status] = (
            raw_counts.get(
                status,
                0,
            )
            + 1
        )

        class_counts[
            classification
        ] = (
            class_counts.get(
                classification,
                0,
            )
            + 1
        )

        report.extend(
            [
                f"## {name}",
                f"Status: {status}",
                (
                    "Classification: "
                    f"{classification}"
                ),
                (
                    "Consecutive failures: "
                    f"{failures}"
                ),
                f"Detail: {detail}",
                f"URL: {url}",
                "",
            ]
        )

        print(
            f"  {status} | "
            f"{classification} | "
            f"{failures}"
        )

        time.sleep(0.2)

    save_status(current)

    report.extend(
        [
            "# SUMMARY BY STATUS",
            "",
        ]
    )

    for status in sorted(
        raw_counts
    ):
        report.append(
            f"{status}: "
            f"{raw_counts[status]}"
        )

    report.extend(
        [
            "",
            "# SUMMARY BY CLASSIFICATION",
            "",
        ]
    )

    for key in [
        "WORKING",
        "TEMPORARY_FAILURE",
        "REPEATED_FAILURE",
        "CONSISTENTLY_BROKEN",
    ]:
        report.append(
            f"{key}: "
            f"{class_counts.get(key, 0)}"
        )

    REPORT_FILE.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "playlist_report.txt created"
    )
    print(
        "playlist_status.json updated"
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
