import re
from pathlib import Path


PLAYLIST_FILE = Path("Playlist.m3u")
OFFLINE_GROUP = "99.Offline"
UNGROUPED_GROUP = "98.Ungrouped"


def get_channel_name(extinf):
    if "," not in extinf:
        return ""

    return extinf.split(",", 1)[1].strip()


def get_group(extinf):
    match = re.search(
        r'group-title="([^"]*)"',
        extinf,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return UNGROUPED_GROUP


def natural_key(text):
    parts = re.split(
        r"(\d+)",
        text.lower()
    )

    key = []

    for part in parts:
        if part.isdigit():
            key.append(
                (0, int(part))
            )
        else:
            key.append(
                (1, part)
            )

    return key


def group_sort_key(group):
    group_lower = group.lower()

    # Offline is ALWAYS at the very bottom.
    if group_lower == OFFLINE_GROUP.lower():
        return (
            2,
            [],
        )

    # Ungrouped goes just before Offline.
    if group_lower == UNGROUPED_GROUP.lower():
        return (
            1,
            natural_key(group),
        )

    return (
        0,
        natural_key(group),
    )


def parse_playlist(text):
    lines = text.splitlines()

    header = "#EXTM3U"
    entries = []

    i = 0

    if (
        lines
        and lines[0].strip().startswith(
            "#EXTM3U"
        )
    ):
        header = lines[0].strip()
        i = 1

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Ignore section comments.
        if (
            line.startswith("#")
            and not line.startswith(
                "#EXTINF:"
            )
        ):
            i += 1
            continue

        if not line.startswith(
            "#EXTINF:"
        ):
            i += 1
            continue

        extinf = lines[i].strip()

        block = [extinf]

        i += 1

        while i < len(lines):
            next_line = lines[i].strip()

            if next_line.startswith(
                "#EXTINF:"
            ):
                break

            if next_line:
                block.append(
                    next_line
                )

            i += 1

        group = get_group(extinf)
        name = get_channel_name(
            extinf
        )

        entries.append(
            {
                "group": group,
                "name": name,
                "block": block,
            }
        )

    return header, entries


def main():
    if not PLAYLIST_FILE.exists():
        raise SystemExit(
            "Playlist.m3u not found"
        )

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    header, entries = (
        parse_playlist(text)
    )

    print(
        f"Channels found: "
        f"{len(entries)}"
    )

    entries.sort(
        key=lambda entry: (
            group_sort_key(
                entry["group"]
            ),
            natural_key(
                entry["name"]
            ),
        )
    )

    output = [
        header,
        "",
    ]

    previous_group = None
    group_count = 0

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
            group_count += 1

        output.extend(
            entry["block"]
        )
        output.append("")

    PLAYLIST_FILE.write_text(
        "\n".join(output).rstrip()
        + "\n",
        encoding="utf-8",
    )

    offline_count = sum(
        1
        for entry in entries
        if entry["group"].lower()
        == OFFLINE_GROUP.lower()
    )

    print(
        f"Groups found: "
        f"{group_count}"
    )

    print(
        f"Offline channels moved "
        f"to bottom: {offline_count}"
    )

    print(
        "Playlist sorted successfully."
    )


if __name__ == "__main__":
    main()
