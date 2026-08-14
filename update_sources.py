import json
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_CONFIG = Path("sources.json")
PLAYLIST = Path("Playlist.m3u")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


def download_text(url):
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    with urlopen(req, timeout=20) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        )


def parse_m3u(text):
    entries = {}

    lines = text.splitlines()
    current_name = None

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF:"):
            if "," in line:
                current_name = (
                    line.split(",", 1)[1].strip()
                )

        elif (
            current_name
            and line.startswith(
                ("http://", "https://")
            )
        ):
            entries[current_name] = line
            current_name = None

    return entries


def replace_channel_url(
    playlist_text,
    channel_name,
    new_url,
):
    lines = playlist_text.splitlines()

    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue

        if "," not in line:
            continue

        name = line.split(",", 1)[1].strip()

        if name != channel_name:
            continue

        j = index + 1

        while j < len(lines):
            value = lines[j].strip()

            if value.startswith("#EXTINF:"):
                break

            if value.startswith(
                ("http://", "https://")
            ):
                old_url = value

                if old_url == new_url:
                    return (
                        playlist_text,
                        False,
                        old_url,
                    )

                lines[j] = new_url

                return (
                    "\n".join(lines) + "\n",
                    True,
                    old_url,
                )

            j += 1

    return playlist_text, False, None


def main():
    if not SOURCE_CONFIG.exists():
        print(
            "sources.json not found. "
            "No replacement sources configured."
        )
        return

    if not PLAYLIST.exists():
        raise SystemExit(
            "Playlist.m3u not found"
        )

    config = json.loads(
        SOURCE_CONFIG.read_text(
            encoding="utf-8"
        )
    )

    playlist_text = PLAYLIST.read_text(
        encoding="utf-8",
        errors="replace",
    )

    changes = 0

    for source in config:
        feed_url = source["feed_url"]
        channels = source.get(
            "channels",
            [],
        )

        print(
            f"Reading authorized source: "
            f"{feed_url}"
        )

        try:
            source_text = download_text(
                feed_url
            )
        except Exception as exc:
            print(
                f"Could not read source: {exc}"
            )
            continue

        source_entries = parse_m3u(
            source_text
        )

        for channel_name in channels:
            new_url = source_entries.get(
                channel_name
            )

            if not new_url:
                print(
                    f"No source entry for "
                    f"{channel_name}"
                )
                continue

            (
                playlist_text,
                changed,
                old_url,
            ) = replace_channel_url(
                playlist_text,
                channel_name,
                new_url,
            )

            if changed:
                changes += 1

                print(
                    f"UPDATED: {channel_name}"
                )
                print(
                    f"  OLD: {old_url}"
                )
                print(
                    f"  NEW: {new_url}"
                )

            else:
                print(
                    f"UNCHANGED: "
                    f"{channel_name}"
                )

    PLAYLIST.write_text(
        playlist_text.rstrip() + "\n",
        encoding="utf-8",
    )

    print()
    print(
        f"Replacement changes: {changes}"
    )


if __name__ == "__main__":
    main()
