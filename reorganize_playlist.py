import json
from pathlib import Path


MASTER_FILE = Path("Master.m3u")
STATUS_FILE = Path(
    "playlist_status.json"
)

ACTIVE_FILE = Path("Playlist.m3u")
OFFLINE_FILE = Path("Offline.m3u")


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


def get_name(extinf):
    if "," not in extinf:
        return "Unknown"

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
                urls.append(value)

            i += 1

        if urls:
            entries.append(
                {
                    "name": name,
                    "extinf": extinf,
                    "urls": urls,
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
        output.append(
            entry["extinf"]
        )

        output.append(
            entry["url"]
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
        name = entry["name"]

        info = status_data.get(
            name,
            {},
        )

        classification = info.get(
            "classification",
            "CHECK_REQUIRED",
        )

        selected_url = info.get(
            "selected_url"
        )

        if (
            classification
            == "CONSISTENTLY_BROKEN"
        ):
            offline_url = (
                entry["urls"][0]
            )

            offline.append(
                {
                    "extinf":
                        entry["extinf"],
                    "url":
                        offline_url,
                }
            )

            print(
                f"OFFLINE: {name}"
            )

            continue

        # Prefer the working URL selected
        # by the checker.
        if selected_url:
            active_url = selected_url
        else:
            # No confirmed working URL yet.
            # Keep first fallback visible.
            active_url = (
                entry["urls"][0]
            )

        active.append(
            {
                "extinf":
                    entry["extinf"],
                "url":
                    active_url,
            }
        )

        print(
            f"ACTIVE: {name}"
        )

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


if __name__ == "__main__":
    main()
