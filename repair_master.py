import re
from pathlib import Path


MASTER_FILE = Path("Master.m3u")


def repair_extinf(line):
    """
    Convert:

    group-title="99.Offline" ... original-group="1.Malayalam"

    into:

    group-title="1.Malayalam" ...

    Then remove original-group.
    """

    offline_match = re.search(
        r'group-title="99\.Offline"',
        line,
        flags=re.IGNORECASE,
    )

    if not offline_match:
        return line, False

    original_match = re.search(
        r'original-group="([^"]+)"',
        line,
        flags=re.IGNORECASE,
    )

    if not original_match:
        print(
            "WARNING: Offline entry has no "
            "original-group:"
        )
        print(line)
        return line, False

    original_group = original_match.group(1)

    # Restore original group.
    line = re.sub(
        r'group-title="99\.Offline"',
        f'group-title="{original_group}"',
        line,
        count=1,
        flags=re.IGNORECASE,
    )

    # Remove original-group attribute.
    line = re.sub(
        r'\s+original-group="[^"]*"',
        "",
        line,
        flags=re.IGNORECASE,
    )

    return line, True


def main():
    if not MASTER_FILE.exists():
        raise SystemExit(
            "ERROR: Master.m3u not found"
        )

    text = MASTER_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    lines = text.splitlines()

    output = []

    repaired = 0
    removed_headers = 0

    for line in lines:
        stripped = line.strip()

        # Remove generated section headers.
        # They will be regenerated later.
        if re.match(
            r'^#\s*=+\s*.*?\s*=+\s*$',
            stripped,
        ):
            removed_headers += 1
            continue

        if stripped.startswith("#EXTINF:"):
            line, changed = repair_extinf(line)

            if changed:
                repaired += 1

        output.append(line)

    # Remove excessive blank lines.
    cleaned = []
    previous_blank = False

    for line in output:
        blank = not line.strip()

        if blank and previous_blank:
            continue

        cleaned.append(line)

        previous_blank = blank

    MASTER_FILE.write_text(
        "\n".join(cleaned).rstrip()
        + "\n",
        encoding="utf-8",
    )

    print()
    print("==============================")
    print("MASTER PLAYLIST REPAIR")
    print("==============================")
    print(
        f"Offline entries restored: "
        f"{repaired}"
    )
    print(
        f"Old section headers removed: "
        f"{removed_headers}"
    )
    print()
    print("Master.m3u repaired.")
    print()
    print(
        "IMPORTANT: Master.m3u now contains "
        "channels in their original groups."
    )


if __name__ == "__main__":
    main()
