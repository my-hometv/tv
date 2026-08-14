import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SOURCE_FILE = Path("youtube_sources.json")
REPORT_FILE = Path("youtube_report.txt")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


def check_youtube(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            final_url = response.geturl()

            data = response.read(500000).decode(
                "utf-8",
                errors="ignore"
            )

            if status != 200:
                return "HTTP_ERROR", status, final_url

            markers = [
                "youtube",
                "ytInitialPlayerResponse",
                "playabilityStatus",
            ]

            if any(marker in data for marker in markers):
                return "OK", status, final_url

            return "WEBPAGE_OR_UNKNOWN", status, final_url

    except HTTPError as e:
        return "HTTP_ERROR", e.code, url

    except URLError as e:
        return "ERROR", str(e.reason), url

    except Exception as e:
        return "ERROR", str(e), url


def main():
    with SOURCE_FILE.open("r", encoding="utf-8") as f:
        sources = json.load(f)

    results = []

    for source in sources:
        name = source["name"]
        youtube_url = source["youtube_url"]

        print(f"Checking: {name}")
        print(f"Source:   {youtube_url}")

        status, detail, final_url = check_youtube(youtube_url)

        results.append({
            "name": name,
            "url": youtube_url,
            "status": status,
            "detail": detail,
            "final_url": final_url,
        })

        print(f"Result:   {status}")
        print()

    counts = {}

    for result in results:
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1

    now = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    lines = [
        "# YouTube Source Check Report",
        "",
        f"Checked {len(results)} URLs",
        f"Time: {now}",
        "",
        "# SUMMARY",
        "",
    ]

    for status in [
        "OK",
        "HTTP_ERROR",
        "ERROR",
        "WEBPAGE_OR_UNKNOWN",
    ]:
        lines.append(
            f"{status}: {counts.get(status, 0)}"
        )

    lines.extend([
        "",
        "# DETAILS",
        "",
    ])

    for result in results:
        lines.extend([
            f"## {result['name']}",
            f"Status: {result['status']}",
            f"URL: {result['url']}",
            f"Detail: {result['detail']}",
            f"Final URL: {result['final_url']}",
            "",
        ])

    REPORT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("Report written to youtube_report.txt")


if __name__ == "__main__":
    main()
