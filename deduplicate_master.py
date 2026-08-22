import re
from pathlib import Path


MASTER_FILE = Path("Master.m3u")
REPORT_FILE = Path(
    "duplicate_report.txt"
)


def normalize_name(name):
    name = name.casefold().strip()

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

        if not line.startswith(
            "#EXTINF:"
        ):
            i += 1
            continue

        extinf = line
        name = get_name(extinf)

        urls = []

        i += 1

        while i < len(lines):
            value = lines[i].strip()

            if value.startswith(
                "#EXTINF:"
            ):
                break

            if value.startswith(
                ("http://", "https://")
            ):
                if value not in urls:
                    urls.append(value)

            i += 1

        if urls:
            entries.append(
                {
                    "name": name,
                    "normalized_name":
                        normalize_name(name),
                    "extinf": extinf,
                    "urls": urls,
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
        output.append(
            entry["extinf"]
        )

        for url in entry["urls"]:
            output.append(url)

        output.append("")

    MASTER_FILE.write_text(
        "\n".join(output)
        .rstrip()
        + "\n",
        encoding="utf-8",
    )


def main():
    header, entries = parse_master()

    original_count = len(entries)

    seen = {}
    kept = []
    deleted = []

    for entry in entries:
        key = entry[
            "normalized_name"
        ]

        if key not in seen:
            seen[key] = entry
            kept.append(entry)
            continue

        previous = seen[key]

        # Same channel name:
        # merge fallback URLs into the
        # first occurrence instead of
        # creating a second channel.
        added = 0

        for url in entry["urls"]:
            if url not in previous["urls"]:
                previous["urls"].append(
                    url
                )
                added += 1

        deleted.append(
            {
                "name":
                    entry["name"],
                "fallbacks_added":
                    added,
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
            f"Original channel entries: "
            f"{original_count}"
        ),
        (
            f"Channels after merge: "
            f"{len(kept)}"
        ),
        (
            f"Duplicate channel entries "
            f"merged: {len(deleted)}"
        ),
        "",
    ]

    for item in deleted:
        report.append(
            (
                f"CHANNEL: "
                f"{item['name']}"
            )
        )
        report.append(
            (
                "Fallback URLs added: "
                f"{item['fallbacks_added']}"
            )
        )
        report.append("")

    REPORT_FILE.write_text(
        "\n".join(report)
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Original entries: "
        f"{original_count}"
    )
    print(
        f"Channels after merge: "
        f"{len(kept)}"
    )
    print(
        f"Duplicate channel entries "
        f"merged: {len(deleted)}"
    )


if __name__ == "__main__":
    main()
