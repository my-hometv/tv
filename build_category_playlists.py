import re
from pathlib import Path
from collections import defaultdict


SOURCE_FILE = Path(
    "Playlist.m3u"
)


CATEGORY_RULES = {
    "Malayalam.m3u": [
        "malayalam",
    ],

    "Hindi.m3u": [
        "hindi",
    ],

    "English.m3u": [
        "english",
    ],

    "Tamil.m3u": [
        "tamil",
    ],

    "Kids.m3u": [
        "kids",
        "children",
        "cartoon",
    ],

    "Food.m3u": [
        "food",
        "cooking",
        "recipe",
    ],

    "Sports.m3u": [
        "sports",
        "sport",
        "cricket",
        "football",
    ],
}


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

    return ""


def natural_key(text):
    parts = re.split(
        r"(\d+)",
        text.lower(),
    )

    key = []

    for part in parts:
        if part.isdigit():
            key.append(
                (
                    0,
                    int(part),
                )
            )
        else:
            key.append(
                (
                    1,
                    part,
                )
            )

    return key


def parse_active_playlist():
    if not SOURCE_FILE.exists():
        raise SystemExit(
            "ERROR: Playlist.m3u "
            "not found"
        )

    lines = SOURCE_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

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

        name = get_name(extinf)
        group = get_group(extinf)

        stream_found = False

        i += 1

        while i < len(lines):
            value = lines[i].strip()

            if value.startswith(
                "#EXTINF:"
            ):
                break

            # Ignore all generated
            # section headings.
            if (
                value
                and not value.startswith(
                    "# ====="
                )
            ):
                block.append(value)

                if value.startswith(
                    (
                        "http://",
                        "https://",
                    )
                ):
                    stream_found = True

            i += 1

        if stream_found:
            entries.append(
                {
                    "name": name,
                    "group": group,
                    "block": block,
                }
            )

    return header, entries


def find_category(group):
    group_lower = group.lower()

    # Language groups first.
    language_files = [
        "Malayalam.m3u",
        "Hindi.m3u",
        "English.m3u",
        "Tamil.m3u",
    ]

    for filename in language_files:
        for keyword in (
            CATEGORY_RULES[
                filename
            ]
        ):
            if (
                keyword.lower()
                in group_lower
            ):
                return filename

    # General categories second.
    other_files = [
        "Kids.m3u",
        "Food.m3u",
        "Sports.m3u",
    ]

    for filename in other_files:
        for keyword in (
            CATEGORY_RULES[
                filename
            ]
        ):
            if (
                keyword.lower()
                in group_lower
            ):
                return filename

    return None


def write_category(
    filename,
    header,
    entries,
):
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

    for entry in entries:
        group = entry["group"]

        if group != previous_group:
            if previous_group is not None:
                output.append("")

            output.append(
                f"# ===== "
                f"{group} ====="
            )

            output.append("")

            previous_group = group

        output.extend(
            entry["block"]
        )

        output.append("")

    Path(filename).write_text(
        "\n".join(output)
        .rstrip()
        + "\n",
        encoding="utf-8",
    )


def main():
    header, entries = (
        parse_active_playlist()
    )

    categories = defaultdict(list)
    unmatched = []

    for entry in entries:
        category = find_category(
            entry["group"]
        )

        if category:
            categories[
                category
            ].append(entry)
        else:
            unmatched.append(entry)

    print(
        f"Total active channels: "
        f"{len(entries)}"
    )
    print()

    for filename in CATEGORY_RULES:
        category_entries = (
            categories.get(
                filename,
                [],
            )
        )

        write_category(
            filename,
            header,
            category_entries,
        )

        print(
            f"{filename}: "
            f"{len(category_entries)} "
            "channels"
        )

    print()
    print(
        f"Unmatched channels: "
        f"{len(unmatched)}"
    )

    if unmatched:
        groups = sorted(
            {
                entry["group"]
                for entry in unmatched
            },
            key=natural_key,
        )

        print(
            "Unmatched groups:"
        )

        for group in groups:
            print(
                f"  - "
                f"{group or 'NO GROUP'}"
            )

    print()
    print(
        "Category playlists updated."
    )


if __name__ == "__main__":
    main()
