import json
from pathlib import Path

import requests


PLAYLIST_FILE = Path("Playlist.m3u")
STATUS_FILE = Path("playlist_status.json")
SOURCES_FILE = Path("sources.json")

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
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        print(f"Could not read {path}: {exc}")
        return default


def download_source(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


def parse_m3u(text):
    entries = {}

    current_name = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line.startswith("#EXTINF:"):
            if "," in line:
                current_name = (
                    line.split(",", 1)[1].strip()
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


def check_hls(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        if response.status_code >= 400:
            response.close()
            return False, f"HTTP {response.status_code}"

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

        return False, "Response does not look like HLS"

    except Exception as exc:
        return False, str(exc)


def build_channel_status(status_data):
    result = {}

    for url, info in status_data.items():
        name = info.get("name")

        if not name:
            continue

        result[name] = {
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

    return result


def replace_stream_url(
    playlist_text,
    channel_name,
    expected_old_url,
    new_url,
):
    lines = playlist_text.splitlines()

    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue

        if "," not in line:
            continue

        name = line.split(",", 1)[1].strip()

        if name != channel_name:
            continue

        j = i + 1

        while j < len(lines):
            value = lines[j].strip()

            if value.startswith("#EXTINF:"):
                break

            if value.startswith(
                ("http://", "https://")
            ):
                if value != expected_old_url:
                    print(
                        f"SKIP {channel_name}: "
                        "playlist URL no longer matches "
                        "status history"
                    )
                    return playlist_text, False

                lines[j] = new_url

                return (
                    "\n".join(lines).rstrip()
                    + "\n",
                    True,
                )

            j += 1

    return playlist_text, False


def main():
    if not PLAYLIST_FILE.exists():
        raise SystemExit(
            "Playlist.m3u not found"
        )

    status_data = load_json(
        STATUS_FILE,
        {},
    )

    source_config = load_json(
        SOURCES_FILE,
        [],
    )

    if not source_config:
        print(
            "No replacement sources configured."
        )
        return

    channel_status = build_channel_status(
        status_data
    )

    playlist_text = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    updated = 0

    for source in source_config:
        feed_url = source.get("feed_url")
        allowed_channels = source.get(
            "channels",
            [],
        )

        if not feed_url:
            continue

        print()
        print(
            f"Reading source feed: {feed_url}"
        )

        try:
            source_text = download_source(
                feed_url
            )
        except Exception as exc:
            print(
                f"Could not download source: {exc}"
            )
            continue

        source_entries = parse_m3u(
            source_text
        )

        for channel_name in allowed_channels:
            info = channel_status.get(
                channel_name
            )

            if not info:
                print(
                    f"SKIP {channel_name}: "
                    "not found in status file"
                )
                continue

            classification = info[
                "classification"
            ]

            failures = info["failures"]
            old_url = info["url"]

            if classification != (
                "CONSISTENTLY_BROKEN"
            ):
                print(
                    f"KEEP {channel_name}: "
                    f"{classification}, "
                    f"failures={failures}"
                )
                continue

            new_url = source_entries.get(
                channel_name
            )

            if not new_url:
                print(
                    f"NO UPDATE {channel_name}: "
                    "not found in source feed"
                )
                continue

            if new_url == old_url:
                print(
                    f"NO UPDATE {channel_name}: "
                    "source still has same URL"
                )
                continue

            print(
                f"Candidate update: {channel_name}"
            )
            print(f"OLD: {old_url}")
            print(f"NEW: {new_url}")

            valid, detail = check_hls(
                new_url
            )

            if not valid:
                print(
                    f"REJECTED {channel_name}: "
                    f"{detail}"
                )
                continue

            (
                playlist_text,
                changed,
            ) = replace_stream_url(
                playlist_text,
                channel_name,
                old_url,
                new_url,
            )

            if changed:
                updated += 1

                print(
                    f"UPDATED {channel_name}"
                )

    if updated:
        PLAYLIST_FILE.write_text(
            playlist_text,
            encoding="utf-8",
        )

    print()
    print(
        f"Stream URLs updated: {updated}"
    )


if __name__ == "__main__":
    main()
