import re
from pathlib import Path
from collections import defaultdict


MASTER_FILE = Path("Master.m3u")
REPORT_FILE = Path("duplicate_report.txt")


def normalize_name(name):
    name = name.casefold().strip()

    # Remove repeated whitespace.
    name = re.sub(r"\s+", " ", name)

    # Remove harmless punctuation differences.
    name = re.sub(
        r"[\-_.,:;]+",
        " ",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name


def get_name(extinf):
    if "," not in extinf:
        return ""

    return (
        extinf.split(",", 1)[1]
        .strip()
    )


def get_group(extinf):
    match = re.search(
        r'group-title="([^"]*)"',
        extinf,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return ""


def parse_master():
    if not MASTER_FILE.exists():
        raise SystemExit(
            "ERROR: Master.m3u not found"
        )

    lines = MASTER_FILE.read_text(
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

        if not line.startswith("#EXTINF:"):
            i += 1
            continue

        extinf = line
        block = [extinf]

        name = get_name(extinf)
        group = get_group(extinf)

        url = None

        i += 1

        while i < len(lines):
            value = lines[i].strip()

            if value.startswith("#EXTINF:"):
                break

            # Ignore generated group comments.
            if (
                value
                and not value.startswith(
                    "# ====="
                )
            ):
                block.append(value)

                if (
                    url is None
                    and value.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    )
                ):
                    url = value

            i += 1

        if url:
            entries.append(
                {
                    "name": name,
                    "normalized_name":
                        normalize_name(name),
                    "group": group,
                    "url": url,
                    "block": block,
                }
            )

    return header, entries


def write_master(
    header,
    entries,
):
    output = [
        header,
        "",
    ]

    for entry in entries:
        output.extend(
            entry["block"]
        )
        output.append("")

    MASTER_FILE.write_text(
        "\n".join(output).rstrip()
        + "\n",
        encoding="utf-8",
    )


def main():
    header, entries = parse_master()

    original_count = len(entries)

    kept = []

    # Track exact duplicates.
    seen_name_url = set()

    # Track identical URLs.
    seen_urls = {}

    # Used later for possible duplicate report.
    names = defaultdict(list)

    deleted = []

    for entry in entries:
        name_key = (
            entry["normalized_name"],
            entry["url"],
        )

        # --------------------------------
        # DUPLICATE TYPE 1
        #
        # Same channel name + same URL
        # --------------------------------
        if name_key in seen_name_url:
            deleted.append(
                {
                    "name": entry["name"],
                    "group": entry["group"],
                    "url": entry["url"],
                    "reason":
                        "Same name and same URL",
                }
            )

            continue

        # --------------------------------
        # DUPLICATE TYPE 2
        #
        # Exact same stream URL already
        # exists.
        # --------------------------------
        if entry["url"] in seen_urls:
            previous = seen_urls[
                entry["url"]
            ]

            # Only auto-delete if names
            # are identical after
            # normalization.
            if (
                previous[
                    "normalized_name"
                ]
                == entry[
                    "normalized_name"
                ]
            ):
                deleted.append(
                    {
                        "name":
                            entry["name"],
                        "group":
                            entry["group"],
                        "url":
                            entry["url"],
                        "reason":
                            "Repeated stream URL",
                    }
                )

                continue

        seen_name_url.add(
            name_key
        )

        seen_urls[
            entry["url"]
        ] = entry

        kept.append(entry)

        names[
            (
                entry[
                    "normalized_name"
                ],
                entry["group"],
            )
        ].append(entry)

    # ------------------------------------
    # Detect possible duplicates.
    #
    # Same name + same group
    # but DIFFERENT URLs.
    #
    # We DO NOT delete these automatically.
    # ------------------------------------

    possible_duplicates = []

    for (
        normalized_name,
        group,
    ), group_entries in names.items():

        if len(group_entries) <= 1:
            continue

        unique_urls = {
            item["url"]
            for item in group_entries
        }

        if len(unique_urls) <= 1:
            continue

        possible_duplicates.append(
            {
                "name":
                    group_entries[0][
                        "name"
                    ],
                "group":
                    group,
                "entries":
                    group_entries,
            }
        )

    write_master(
        header,
        kept,
    )

    report = [
        "# Duplicate Channel Report",
        "",
        (
            f"Original channels: "
            f"{original_count}"
        ),
        (
            f"Channels after cleanup: "
            f"{len(kept)}"
        ),
        (
            f"Duplicates automatically "
            f"deleted: {len(deleted)}"
        ),
        (
            f"Possible duplicates kept "
            f"for review: "
            f"{len(possible_duplicates)}"
        ),
        "",
        "# AUTOMATICALLY DELETED",
        "",
    ]

    if deleted:
        for item in deleted:
            report.extend(
                [
                    (
                        f"CHANNEL: "
                        f"{item['name']}"
                    ),
                    (
                        f"GROUP: "
                        f"{item['group']}"
                    ),
                    (
                        f"REASON: "
                        f"{item['reason']}"
                    ),
                    (
                        f"URL: "
                        f"{item['url']}"
                    ),
                    "",
                ]
            )
    else:
        report.append(
            "No exact duplicates found."
        )
        report.append("")

    report.extend(
        [
            "# POSSIBLE DUPLICATES",
            "",
            (
                "These were NOT deleted "
                "because they use different "
                "stream URLs."
            ),
            "",
        ]
    )

    if possible_duplicates:
        for duplicate in (
            possible_duplicates
        ):
            report.append(
                (
                    f"CHANNEL: "
                    f"{duplicate['name']}"
                )
            )

            report.append(
                (
                    f"GROUP: "
                    f"{duplicate['group']}"
                )
            )

            for item in (
                duplicate["entries"]
            ):
                report.append(
                    f"URL: {item['url']}"
                )

            report.append("")
    else:
        report.append(
            "No possible duplicates found."
        )
        report.append("")

    REPORT_FILE.write_text(
        "\n".join(report)
        + "\n",
        encoding="utf-8",
    )

    print(
        "=============================="
    )
    print(
        "DUPLICATE CHECK"
    )
    print(
        "=============================="
    )
    print(
        f"Original channels: "
        f"{original_count}"
    )
    print(
        f"Exact duplicates deleted: "
        f"{len(deleted)}"
    )
    print(
        f"Possible duplicates: "
        f"{len(possible_duplicates)}"
    )
    print(
        f"Remaining channels: "
        f"{len(kept)}"
    )
    print()
    print(
        "duplicate_report.txt created."
    )


if __name__ == "__main__":
    main()
