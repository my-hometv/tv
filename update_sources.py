import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests


PLAYLIST_FILE = Path("Playlist.m3u")
STATUS_FILE = Path("playlist_status.json")
SOURCES_FILE = Path("sources.json")
REPORT_FILE = Path("source_update_report.txt")

TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        print(
            f"Could not read {path}: {exc}"
        )
        return default


def check_hls(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        status = response.status_code

        if status >= 400:
            response.close()
            return False, f"HTTP {status}"

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

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

        text = sample.decode(
            "utf-8",
            errors="ignore",
        )

        valid = (
            "#EXTM3U" in text
            or "#EXT-X-" in text
            or "application/vnd.apple.mpegurl"
            in content_type
            or "application/x-mpegurl"
            in content_type
        )

        if valid:
            return True, "Valid HLS"

        return (
            False,
            "Response does not look like HLS",
        )

    except Exception as exc:
        return False, str(exc)


def parse_m3u(text):
    entries = {}

    current_name = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line.startswith("#EXTINF:"):
            if "," in line:
                current_name = (
                    line.split(",", 1)[1]
                    .strip()
                )
            else:
                current_name = None

        elif (
            current_name
            and line.startswith(
                ("http://", "https://")
            )
        ):
            entries[current_name] = line
            current_name = None

    return entries


def get_from_feed(feed_url, channel_name):
    try:
        response = requests.get(
            feed_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        entries = parse_m3u(
            response.text
        )

        url = entries.get(
            channel_name
        )

        if not url:
            return (
                None,
                "Channel not found in source feed",
            )

        return (
            url,
            "Found in source feed",
        )

    except Exception as exc:
        return None, str(exc)


def get_from_source_page(source_page):
    try:
        response = requests.get(
            source_page,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        html = response.text

        patterns = [
            r'https?://[^"\'<>\s]+\.m3u8(?:\?[^"\'<>\s]*)?',
            r'["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']',
        ]

        candidates = []

        for pattern in patterns:
            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]

                candidate = match.strip()

                if not candidate.startswith(
                    ("http://", "https://")
                ):
                    candidate = urljoin(
                        source_page,
                        candidate,
                    )

                if candidate not in candidates:
                    candidates.append(
                        candidate
                    )

        if not candidates:
            return (
                None,
                "No direct .m3u8 exposed in page HTML",
            )

        for candidate in candidates:
            valid, detail = check_hls(
                candidate
            )

            if valid:
                return (
                    candidate,
                    "Direct public HLS found in page HTML",
                )

        return (
            None,
            (
                f"Found {len(candidates)} "
                "candidate(s), none passed HLS check"
            ),
        )

    except Exception as exc:
        return None, str(exc)


def build_status_by_name(status_data):
    channels = {}

    for url, info in status_data.items():
        name = info.get("name")

        if not name:
            continue

        channels[name] = {
            "url": url,
            "classification": info.get(
                "classification",
                "",
            ),
            "failures": info.get(
                "consecutive_failures",
                0,
            ),
        }

    return channels


def replace_stream_url(
    playlist_text,
    channel_name,
    old_url,
    new_url,
):
    lines = playlist_text.splitlines()

    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue

        if "," not in line:
            continue

        name = (
            line.split(",", 1)[1]
            .strip()
        )

        if name != channel_name:
            continue

        j = i + 1

        while j < len(lines):
            current = lines[j].strip()

            if current.startswith(
                "#EXTINF:"
            ):
                break

            if current.startswith(
                ("http://", "https://")
            ):
                if current != old_url:
                    return (
                        playlist_text,
                        False,
                        (
                            "Playlist URL differs from "
                            "status history"
                        ),
                    )

                lines[j] = new_url

                return (
                    "\n".join(lines).rstrip()
                    + "\n",
                    True,
                    "URL replaced",
                )

            j += 1

    return (
        playlist_text,
        False,
        "Channel not found in playlist",
    )


def main():
    if not PLAYLIST_FILE.exists():
        raise SystemExit(
            "Playlist.m3u not found"
        )

    status_data = load_json(
        STATUS_FILE,
        {},
    )

    sources = load_json(
        SOURCES_FILE,
        [],
    )

    if not sources:
        print(
            "No replacement sources configured."
        )
        return

    status_by_name = build_status_by_name(
        status_data
    )

    playlist_text = (
        PLAYLIST_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    report = []
    updated = 0

    for source in sources:
        channel_name = source.get(
            "channel"
        )

        if not channel_name:
            continue

        report.append(
            f"CHANNEL: {channel_name}"
        )

        info = status_by_name.get(
            channel_name
        )

        if not info:
            report.append(
                "RESULT: Channel not found in status file"
            )
            report.append("")
            continue

        old_url = info["url"]
        classification = info[
            "classification"
        ]
        failures = info["failures"]

        report.append(
            f"CURRENT URL: {old_url}"
        )
        report.append(
            f"CLASSIFICATION: {classification}"
        )
        report.append(
            f"FAILURES: {failures}"
        )

        if classification != (
            "CONSISTENTLY_BROKEN"
        ):
            report.append(
                "RESULT: Current URL not eligible for refresh"
            )
            report.append("")
            continue

        candidate_url = None
        source_detail = ""

        feed_url = source.get(
            "feed_url"
        )

        source_page = source.get(
            "source_page"
        )

        if feed_url:
            candidate_url, source_detail = (
                get_from_feed(
                    feed_url,
                    channel_name,
                )
            )

        elif source_page:
            candidate_url, source_detail = (
                get_from_source_page(
                    source_page
                )
            )

        else:
            source_detail = (
                "No feed_url or source_page configured"
            )

        report.append(
            f"SOURCE RESULT: {source_detail}"
        )

        if not candidate_url:
            report.append(
                "RESULT: No replacement found"
            )
            report.append("")
            continue

        report.append(
            f"CANDIDATE URL: {candidate_url}"
        )

        if candidate_url == old_url:
            report.append(
                "RESULT: Source still provides same URL"
            )
            report.append("")
            continue

        valid, detail = check_hls(
            candidate_url
        )

        report.append(
            f"CANDIDATE CHECK: {detail}"
        )

        if not valid:
            report.append(
                "RESULT: Candidate rejected"
            )
            report.append("")
            continue

        (
            playlist_text,
            changed,
            replace_detail,
        ) = replace_stream_url(
            playlist_text,
            channel_name,
            old_url,
            candidate_url,
        )

        report.append(
            f"REPLACE RESULT: {replace_detail}"
        )

        if changed:
            updated += 1
            report.append(
                "RESULT: UPDATED"
            )
        else:
            report.append(
                "RESULT: NO CHANGE"
            )

        report.append("")

    if updated:
        PLAYLIST_FILE.write_text(
            playlist_text,
            encoding="utf-8",
        )

    report.append(
        f"TOTAL URLS UPDATED: {updated}"
    )

    REPORT_FILE.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print(
        "\n".join(report)
    )


if __name__ == "__main__":
    main()
