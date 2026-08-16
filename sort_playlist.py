import re
from pathlib import Path


PLAYLIST_FILES = [
    Path("Playlist.m3u"),
    Path("Offline.m3u"),
]


def get_name(extinf):
    if "," not in extinf:
        return ""

    return (
        extinf
        .split(",", 1)[1]
        .strip()
    )


def get_group(extinf):
    match = re.search(
        r'group-title="([^"]*)"',
        extinf,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            match.group(1)
            .strip()
        )

    return "98.Ungrouped"


def natural_key(text):
    parts = re.split(
        r"(\d+)",
        text.lower(),
    )

    result = []

    for part in parts:
        if part.isdigit():
            result.append(
                (
                    0,
                    int(part),
                )
            )
        else:
            result.append(
                (
                    1,
                    part,
                )
            )

    return result


def parse_file(path):
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    lines = text.splitlines()

    header = "#EXTM3U"

    if (
        lines
        and lines[0]
        .strip()
        .startswith("#EXTM3U")
    ):
        header = lines[0].strip()

    entries = []

    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line.startswith(
            "#EXTINF:"
        ):
            i += 1
            continue

        extinf = line

        block = [extinf]

        i += 1

        while i < len(lines):
            value = lines[i].strip()

            if value.startswith(
                "#EXTINF:"
            ):
                break

            # Never preserve old generated
            # group comments.
            if (
                value
                and not value.startswith(
                    "# ====="
                )
            ):
                block.append(value)

            i += 1

        entries.append(
            {
                "name":
                    get_name(extinf),
                "group":
                    get_group(extinf),
                "block":
                    block,
            }
        )

    return header, entries


def sort_file(path):
    if not path.exists():
        print(
            f"Skipping missing "
            f"{path}"
        )
        return

    header, entries = (
        parse_file(path)
    )

    entries.sort(
        key=lambda entry: (
            natural_key(
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

            # Generate exactly ONE
            # section header.
            output.append(
                f"# ===== "
                f"{group} ====="
            )

            output.append("")

            previous_group = group
            group_count += 1

        output.extend(
            entry["block"]
        )

        output.append("")

    path.write_text(
        "\n".join(output)
        .rstrip()
        + "\n",
        encoding="utf-8",
    )

    print(
        f"{path.name}: "
        f"{len(entries)} channels, "
        f"{group_count} groups"
    )


def main():
    for path in PLAYLIST_FILES:
        sort_file(path)

    print()
    print(
        "Playlist sorting complete."
    )


if __name__ == "__main__":
    main()
