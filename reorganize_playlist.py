import json
import re
from pathlib import Path


PLAYLIST_FILE = Path("Playlist.m3u")
STATUS_FILE = Path("playlist_status.json")

OFFLINE_GROUP = "99.Offline"


def load_status():
    if not STATUS_FILE.exists():
        raise SystemExit("playlist_status.json not found")

    return json.loads(
        STATUS_FILE.read_text(encoding="utf-8")
    )


def get_group(extinf):
    match = re.search(
        r'group-title="([^"]*)"',
        extinf,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None


def get_original_group(extinf):
    match = re.search(
        r'original-group="([^"]*)"',
        extinf,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None


def set_group(extinf, group):
    if re.search(
        r'group-title="[^"]*"',
        extinf,
        flags=re.IGNORECASE,
    ):
        return re.sub(
            r'group-title="[^"]*"',
            f'group-title="{group}"',
            extinf,
            count=1,
            flags=re.IGNORECASE,
        )

    comma = extinf.rfind(",")

    if comma != -1:
        return (
            extinf[:comma]
            + f' group-title="{group}"'
            + extinf[comma:]
        )

    return extinf


def add_original_group(extinf, group):
    if get_original_group(extinf):
        return extinf

    comma = extinf.rfind(",")

    if comma == -1:
        return extinf

    return (
        extinf[:comma]
        + f' original-group="{group}"'
        + extinf[comma:]
    )


def remove_original_group(extinf):
    return re.sub(
        r'\s*original-group="[^"]*"',
        "",
        extinf,
        count=1,
        flags=re.IGNORECASE,
    )


def status_by_url(status_data):
    result = {}

    for url, info in status_data.items():
        result[url] = info.get(
            "classification",
            "",
        )

    return result


def main():
    if not PLAYLIST_FILE.exists():
        raise SystemExit("Playlist.m3u not found")

    status_data = load_status()
    classifications = status_by_url(status_data)

    lines = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    moved_offline = 0
    restored = 0

    i = 0

    while i < len(lines):
        if not lines[i].startswith("#EXTINF:"):
            i += 1
            continue

        extinf_index = i
        extinf = lines[i]

        j = i + 1
        stream_url = None

        while j < len(lines):
            value = lines[j].strip()

            if value.startswith("#EXTINF:"):
                break

            if value.startswith(
                ("http://", "https://")
            ):
                stream_url = value
                break

            j += 1

        if not stream_url:
            i += 1
            continue

        classification = classifications.get(
            stream_url
        )

        current_group = get_group(extinf)
        original_group = get_original_group(extinf)

        # Move consistently broken streams
        # into 99.Offline.
        if (
            classification == "CONSISTENTLY_BROKEN"
            and current_group != OFFLINE_GROUP
        ):
            if current_group:
                extinf = add_original_group(
                    extinf,
                    current_group,
                )

            extinf = set_group(
                extinf,
                OFFLINE_GROUP,
            )

            lines[extinf_index] = extinf

            moved_offline += 1

            print(
                f"OFFLINE: {stream_url}"
            )

        # Restore a recovered stream.
        elif (
            classification == "WORKING"
            and current_group == OFFLINE_GROUP
            and original_group
        ):
            extinf = set_group(
                extinf,
                original_group,
            )

            extinf = remove_original_group(
                extinf
            )

            lines[extinf_index] = extinf

            restored += 1

            print(
                f"RESTORED: {stream_url}"
            )

        i = max(i + 1, j)

    PLAYLIST_FILE.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )

    print()
    print(
        f"Moved to {OFFLINE_GROUP}: "
        f"{moved_offline}"
    )
    print(
        f"Restored to original group: "
        f"{restored}"
    )


if __name__ == "__main__":
    main()
