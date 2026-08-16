import json
import re
from pathlib import Path


PLAYLIST_FILE = Path("Playlist.m3u")
STATUS_FILE = Path("playlist_status.json")
OFFLINE_FILE = Path("Offline.m3u")

# How many consecutive hard failures before hiding.
HIDE_AFTER_FAILURES = 3


def load_status():
    if not STATUS_FILE.exists():
        raise SystemExit("playlist_status.json not found")

    return json.loads(
        STATUS_FILE.read_text(encoding="utf-8")
    )


def get_channel_name(extinf):
    if "," not in extinf:
        return "Unknown"

    return extinf.split(",", 1)[1].strip()


def get_group(extinf):
    match = re.search(
        r'group-title="([^"]*)"',
        extinf,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return "98.Ungrouped"


def parse_playlist(text):
    lines = text.splitlines()

    header = "#EXTM3U"
    entries = []

    i = 0

    if lines and lines[0].strip().startswith("#EXTM3U"):
        header = lines[0].strip()
        i = 1

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if not line.startswith("#EXTINF:"):
            i += 1
            continue

        extinf = lines[i].strip()
        block = [extinf]

        i += 1
        stream_url = None

        while i < len(lines):
            next_line = lines[i].strip()

            if next_line.startswith("#EXTINF:"):
                break

            if next_line:
                block.append(next_line)

                if (
                    stream_url is None
                    and next_line.startswith(
                        ("http://", "https://")
                    )
                ):
                    stream_url = next_line

            i += 1

        if stream_url:
            entries.append(
                {
                    "name": get_channel_name(extinf),
                    "group": get_group(extinf),
                    "url": stream_url,
                    "block": block,
                }
            )

    return header, entries


def should_hide(info):
    if not info:
        return False

    status = info.get("last_status", "")
    detail = info.get("last_detail", "")
    failures = info.get(
        "consecutive_failures",
        0,
    )

    # Working stream: always visible.
    if status == "OK":
        return False

    # Do NOT hide access-restricted streams automatically.
    #
    # 401 / 403 may still work in an IPTV app,
    # browser session, geographic region, or with
    # legitimate source-specific headers.
    if (
        "HTTP 401" in detail
        or "HTTP 403" in detail
    ):
        return False

    # Don't hide webpage/unknown entries solely
    # because they are not direct HLS.
    if status == "WEBPAGE_OR_UNKNOWN":
        return False

    # Require several consecutive failures.
    if failures < HIDE_AFTER_FAILURES:
        return False

    # Strong evidence that the stream is gone.
    if "HTTP 404" in detail:
        return True

    if "HTTP 410" in detail:
        return True

    # DNS / hostname failure.
    dns_terms = [
        "Failed to resolve",
        "NameResolutionError",
        "Name or service not known",
        "No address associated with hostname",
    ]

    if any(term in detail for term in dns_terms):
        return True

    # Connection refusal.
    refusal_terms = [
        "Connection refused",
        "Failed to establish a new connection",
    ]

    if any(term in detail for term in refusal_terms):
        return True

    # Persistent timeouts can also be hidden,
    # but only after the threshold.
    if status == "TIMEOUT":
        return True

    return False


def write_playlist(path, header, entries):
    output = [
        header,
        "",
    ]

    previous_group = None

    for entry in entries:
        group = entry["group"]

        if group != previous_group:
            if previous_group is not None:
                output.append("")

            output.append(
                f"# ===== {group} ====="
            )
            output.append("")

            previous_group = group

        output.extend(entry["block"])
        output.append("")

    path.write_text(
        "\n".join(output).rstrip() + "\n",
        encoding="utf-8",
    )


def natural_key(text):
    parts = re.split(
        r"(\d+)",
        text.lower(),
    )

    key = []

    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))

    return key


def main():
    if not PLAYLIST_FILE.exists():
        raise SystemExit("Playlist.m3u not found")

    status_data = load_status()

    playlist_text = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    header, entries = parse_playlist(
        playlist_text
    )

    active = []
    offline = []

    for entry in entries:
        info = status_data.get(
            entry["url"]
        )

        if should_hide(info):
            offline.append(entry)

            print(
                f"HIDE: {entry['name']}"
            )
        else:
            active.append(entry)

            if (
                info
                and info.get("last_status")
                == "OK"
            ):
                print(
                    f"ACTIVE: {entry['name']}"
                )

    # Sort by group, then channel name.
    active.sort(
        key=lambda entry: (
            natural_key(entry["group"]),
            natural_key(entry["name"]),
        )
    )

    offline.sort(
        key=lambda entry: (
            natural_key(entry["group"]),
            natural_key(entry["name"]),
        )
    )

    write_playlist(
        PLAYLIST_FILE,
        header,
        active,
    )

    write_playlist(
        OFFLINE_FILE,
        header,
        offline,
    )

    print()
    print(
        f"Active channels: {len(active)}"
    )
    print(
        f"Hidden/offline channels: {len(offline)}"
    )
    print(
        "Playlist.m3u updated with active channels only."
    )
    print(
        "Offline.m3u created/updated."
    )


if __name__ == "__main__":
    main()
