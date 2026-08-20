import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright


CATEGORY_URL = "https://bhoomtv.me/channel/malayalam/"

MASTER_FILE = Path("Master.m3u")
REPORT_FILE = Path("bhoomtv_dynamic_report.txt")

PAGE_TIMEOUT = 45000
WAIT_AFTER_LOAD = 8000


ALIASES = {
    "kaumudy tv": "kaumudi",
    "darshana tv": "darshana",
    "newstar": "new star",
    "kasaragod vision": "kasargod vision",
    "raj music malayalam": "rajmusix malayalam",
}


def normalize_name(name):
    name = name.casefold().strip()

    name = name.replace("&", "and")

    name = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return ALIASES.get(
        name,
        name,
    )


def get_master_channels():
    if not MASTER_FILE.exists():
        return {}

    channels = {}

    text = MASTER_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    for line in text.splitlines():
        line = line.strip()

        if not line.startswith("#EXTINF:"):
            continue

        if "," not in line:
            continue

        name = (
            line.split(",", 1)[1]
            .strip()
        )

        channels[
            normalize_name(name)
        ] = name

    return channels


def classify_url(url):
    lower = url.lower()

    if ".m3u8" in lower:
        return "HLS"

    if ".mpd" in lower:
        return "DASH"

    if (
        "youtube.com/watch" in lower
        or "youtu.be/" in lower
        or "youtube.com/embed/" in lower
    ):
        return "YOUTUBE"

    return None


async def collect_category_links(page):
    await page.goto(
        CATEGORY_URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    await page.wait_for_timeout(
        3000
    )

    links = await page.eval_on_selector_all(
        "a[href]",
        """
        els => els
            .map(a => a.href)
            .filter(h => h.includes('/live/'))
        """
    )

    cleaned = []

    for url in links:
        if "bhoomtv.me/live/" not in url:
            continue

        url = url.split("#", 1)[0]

        if url not in cleaned:
            cleaned.append(url)

    return cleaned


async def page_channel_name(page, page_url):
    title = await page.title()

    title = re.sub(
        r"\s*[-|]\s*Bhoom\s*TV.*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"^Watch\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\s+Live.*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = title.strip()

    if title:
        return title

    return (
        page_url.rstrip("/")
        .split("/")[-1]
        .replace("-", " ")
        .title()
    )


async def scan_channel(
    context,
    page_url,
    master_channels,
):
    page = await context.new_page()

    discovered = []

    def add_url(url, source):
        classification = (
            classify_url(url)
        )

        if not classification:
            return

        key = (
            classification,
            url,
        )

        if any(
            (
                item["type"],
                item["url"],
            )
            == key
            for item in discovered
        ):
            return

        discovered.append(
            {
                "type": classification,
                "url": url,
                "source": source,
            }
        )

    def request_handler(request):
        add_url(
            request.url,
            "REQUEST",
        )

    def response_handler(response):
        add_url(
            response.url,
            "RESPONSE",
        )

    page.on(
        "request",
        request_handler,
    )

    page.on(
        "response",
        response_handler,
    )

    status = "OK"
    error = ""

    try:
        response = await page.goto(
            page_url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT,
        )

        if (
            response
            and response.status >= 400
        ):
            status = (
                f"PAGE_HTTP_"
                f"{response.status}"
            )

        # Allow JavaScript/player to start.
        await page.wait_for_timeout(
            WAIT_AFTER_LOAD
        )

        # ----------------------------------
        # Inspect iframe URLs
        # ----------------------------------

        iframe_urls = await page.eval_on_selector_all(
            "iframe[src]",
            """
            els => els.map(x => x.src)
            """
        )

        for iframe_url in iframe_urls:
            add_url(
                iframe_url,
                "IFRAME",
            )

        # ----------------------------------
        # Inspect rendered HTML
        # ----------------------------------

        html = await page.content()

        html = (
            html.replace("\\/", "/")
            .replace("&amp;", "&")
        )

        patterns = [
            r'https?://[^"\'<>\s]+\.m3u8(?:\?[^"\'<>\s]*)?',
            r'https?://[^"\'<>\s]+\.mpd(?:\?[^"\'<>\s]*)?',
            r'https?://(?:www\.)?youtube\.com/watch\?v=[A-Za-z0-9_-]+',
            r'https?://youtu\.be/[A-Za-z0-9_-]+',
        ]

        for pattern in patterns:
            for match in re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            ):
                add_url(
                    match,
                    "RENDERED_HTML",
                )

        # ----------------------------------
        # Inspect JS performance resources
        # ----------------------------------

        resources = await page.evaluate(
            """
            () => performance
                .getEntriesByType('resource')
                .map(x => x.name)
            """
        )

        for resource_url in resources:
            add_url(
                resource_url,
                "PERFORMANCE",
            )

        # ----------------------------------
        # Inspect frames after rendering
        # ----------------------------------

        for frame in page.frames:
            if frame.url:
                add_url(
                    frame.url,
                    "FRAME",
                )

    except Exception as exc:
        status = "PAGE_ERROR"
        error = str(exc)

    name = await page_channel_name(
        page,
        page_url,
    )

    normalized = normalize_name(
        name
    )

    master_match = (
        normalized
        in master_channels
    )

    await page.close()

    return {
        "name": name,
        "page": page_url,
        "status": status,
        "error": error,
        "master_match":
            master_match,
        "streams":
            discovered,
    }


async def main():
    master_channels = (
        get_master_channels()
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Safari/537.36"
            ),
            viewport={
                "width": 1280,
                "height": 720,
            },
        )

        category_page = (
            await context.new_page()
        )

        links = await collect_category_links(
            category_page
        )

        await category_page.close()

        print(
            f"Channel pages found: "
            f"{len(links)}"
        )

        results = []

        for index, page_url in enumerate(
            links,
            start=1,
        ):
            print(
                f"[{index}/{len(links)}] "
                f"{page_url}"
            )

            result = await scan_channel(
                context,
                page_url,
                master_channels,
            )

            results.append(
                result
            )

        await browser.close()

    hls_count = 0
    dash_count = 0
    youtube_count = 0
    no_stream_count = 0

    for item in results:
        types = {
            stream["type"]
            for stream in item[
                "streams"
            ]
        }

        hls_count += sum(
            1
            for stream in item[
                "streams"
            ]
            if stream[
                "type"
            ] == "HLS"
        )

        dash_count += sum(
            1
            for stream in item[
                "streams"
            ]
            if stream[
                "type"
            ] == "DASH"
        )

        youtube_count += sum(
            1
            for stream in item[
                "streams"
            ]
            if stream[
                "type"
            ] == "YOUTUBE"
        )

        if not types:
            no_stream_count += 1

    report = [
        "# BhoomTV Dynamic Malayalam Report",
        "",
        f"Category: {CATEGORY_URL}",
        "",
        "# SUMMARY",
        "",
        (
            f"Channel pages: "
            f"{len(results)}"
        ),
        (
            f"HLS URLs discovered: "
            f"{hls_count}"
        ),
        (
            f"DASH URLs discovered: "
            f"{dash_count}"
        ),
        (
            f"YouTube URLs discovered: "
            f"{youtube_count}"
        ),
        (
            f"No stream discovered: "
            f"{no_stream_count}"
        ),
        "",
        "# DETAILS",
        "",
    ]

    missing_master = []

    for item in results:
        report.append(
            f"## {item['name']}"
        )

        report.append(
            f"PAGE STATUS: "
            f"{item['status']}"
        )

        report.append(
            (
                "IN MASTER: "
                + (
                    "YES"
                    if item[
                        "master_match"
                    ]
                    else "NO"
                )
            )
        )

        report.append(
            f"PAGE: {item['page']}"
        )

        if item["error"]:
            report.append(
                f"ERROR: "
                f"{item['error']}"
            )

        if not item["streams"]:
            report.append(
                "STREAM: NOT FOUND"
            )

        else:
            for stream in (
                item["streams"]
            ):
                report.append(
                    (
                        f"{stream['type']}: "
                        f"{stream['url']}"
                    )
                )

                report.append(
                    (
                        "DISCOVERED VIA: "
                        f"{stream['source']}"
                    )
                )

        report.append("")

        if not item[
            "master_match"
        ]:
            missing_master.append(
                item
            )

    report.extend(
        [
            "# NOT FOUND IN MASTER",
            "",
            (
                f"Count: "
                f"{len(missing_master)}"
            ),
            "",
        ]
    )

    for item in missing_master:
        report.append(
            item["name"]
        )

    REPORT_FILE.write_text(
        "\n".join(report)
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "=============================="
    )
    print(
        "BHOOMTV DYNAMIC SCAN"
    )
    print(
        "=============================="
    )
    print(
        f"Channels: {len(results)}"
    )
    print(
        f"HLS discovered: "
        f"{hls_count}"
    )
    print(
        f"DASH discovered: "
        f"{dash_count}"
    )
    print(
        f"YouTube discovered: "
        f"{youtube_count}"
    )
    print(
        f"No stream: "
        f"{no_stream_count}"
    )
    print()
    print(
        "bhoomtv_dynamic_report.txt "
        "created."
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
