import re
from pathlib import Path


PLAYLIST_FILE = Path("Playlist.m3u")
OFFLINE_GROUP = "99.Offline"


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

    return "98.Ungrouped"


def natural_key(text):
    """
    Natural sorting:
    1.Malayalam
    2.Malayalam News
    3.Malayalam Religious
    10.Other

    instead of:
    1...
    10...
    2...
    """

    parts = re.split(r"(\d+)", text.lower())

    result = []

    for part in parts:
        if part.isdigit():
            result.append((0, int(part)))
        else:
            result.append((1, part))

    return result


def group_sort_key(group):
    # Always force Offline to the bottom.
    if group.lower() == OFFLINE_GROUP.lower():
        return (1, [])

    return (0, natural_key(group))


def parse_playlist(text):
    lines = text.splitlines()

    header = "#EXTM3U"
    entries = []

    i = 0

    # Preserve #EXTM3U header.
    if lines and lines[0].strip().startswith("#EXTM3U"):
        header = lines[0].strip()
        i = 1

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Ignore old section comments such as:
        # ===== 1.Malayalam =====
        if (
            line.startswith("#")
            and not line.startswith("#EXTINF:")
        ):
            i += 1
            continue

        if not line.startswith("#EXTINF:"):
            i += 1
            continue

        extinf = lines[i].strip()

        block = [extinf]

        i += 1

        # Preserve everything belonging to this channel
        # until the next #EXTINF.
        while i < len(lines):
            next_line = lines[i].strip()

            if next_line.startswith("#EXTINF:"):
                break

            if next_line:
                block.append(next_line)

            i += 1

        channel_name = get_channel_name(extinf)
        group = get_group(extinf)

        entries.append(
            {
                "group": group,
                "name": channel_name,
                "block": block,
            }
        )

    return header, entries


def main():
    if not PLAYLIST_FILE.exists():
        raise SystemExit("Playlist.m3u not found")

    text = PLAYLIST_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    header, entries = parse_playlist(text)

    print(f"Channels found: {len(entries)}")

    # First sort channels alphabetically.
    # Then sort groups.
    entries.sort(
        key=lambda entry: (
            group_sort_key(entry["group"]),
            natural_key(entry["name"]),
        )
    )

    output = [header, ""]

    previous_group = None
    group_count = 0

    for entry in entries:
        group = entry["group"]

        if group != previous_group:
            if previous_group is not None:
                output.append("")

            # Add a readable section marker.
            output.append(
                f"# ===== {group} ====="
            )
            output.append("")

            previous_group = group
            group_count += 1

        output.extend(entry["block"])
        output.append("")

    PLAYLIST_FILE.write_text(
        "\n".join(output).rstrip() + "\n",
        encoding="utf-8",
    )

    print(f"Groups found: {group_count}")
    print("Playlist sorted successfully.")
    print(
        "Sort order: group -> channel name"
    )


if __name__ == "__main__":
    main()
