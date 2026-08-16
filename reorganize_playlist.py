import json
from pathlib import Path


MASTER_FILE = Path("Master.m3u")
STATUS_FILE = Path(
    "playlist_status.json"
)

ACTIVE_FILE = Path(
    "Playlist.m3u"
)

OFFLINE_FILE = Path(
    "Offline.m3u"
)


def load_status():
    if not STATUS_FILE.exists():
        return {}

    try:
        return json.loads(
            STATUS_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


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

        if "," in extinf:
            name = (
                extinf
                .split(",", 1)[1]
                .strip()
            )
        else:
            name = "Unknown"

        block = [extinf]
        stream_url = None

        i += 1

        while i < len(lines):
            value = lines[i].strip()

            if value.startswith(
                "#EXTINF:"
            ):
                break

            # Completely ignore all
            # generated section comments:
            #
            # # ===== GROUP =====
            #
            # This prevents duplicates.
            if (
                value
                and not value.startswith(
                    "# ====="
                )
            ):
                block.append(value)

                if (
                    stream_url is None
                    and value.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    )
                ):
                    stream_url = value

            i += 1

        if stream_url:
            entries.append(
                {
                    "name": name,
                    "url": stream_url,
                    "block": block,
                }
            )

    return header, entries


def write_playlist(
    path,
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

    path.write_text(
        "\n".join(output)
        .rstrip()
        + "\n",
        encoding="utf-8",
    )


def main():
    status_data = load_status()

    header, entries = parse_master()

    active = []
    offline = []

    for entry in entries:
        info = status_data.get(
            entry["url"],
            {},
        )

        classification = info.get(
            "classification",
            "CHECK_REQUIRED",
        )

        # Only confirmed persistent
        # HARD failures are hidden.
        if (
            classification
            == "CONSISTENTLY_BROKEN"
        ):
            offline.append(entry)

            print(
                f"OFFLINE: "
                f"{entry['name']}"
            )

        else:
            active.append(entry)

    write_playlist(
        ACTIVE_FILE,
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
        "=============================="
    )
    print(
        "PLAYLIST GENERATION"
    )
    print(
        "=============================="
    )
    print(
        f"Master channels: "
        f"{len(entries)}"
    )
    print(
        f"Active channels: "
        f"{len(active)}"
    )
    print(
        f"Offline channels: "
        f"{len(offline)}"
    )
    print()
    print(
        "Playlist.m3u = active only"
    )
    print(
        "Offline.m3u = hidden channels"
    )


if __name__ == "__main__":
    main()
