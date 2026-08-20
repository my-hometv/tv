import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


CATEGORY_URL = "https://bhoomtv.me/channel/malayalam/"

MASTER_FILE = Path("Master.m3u")
REPORT_FILE = Path("bhoomtv_malayalam_report.txt")

TIMEOUT = 15
REQUEST_DELAY = 0.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def normalize_name(name):
    name = name.casefold().strip()

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    name = re.sub(
        r"[^a-z0-9 ]+",
        "",
        name,
    )

    return name.strip()


def get_master_channels():
    if not MASTER_FILE.exists():
        return {}

    text = MASTER_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    channels = {}

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


def request_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        return response

    except Exception as exc:
        print(
            f"Request failed: {url}"
        )
        print(
            f"  {exc}"
        )

        return None


def clean_html_text(text):
    text = (
        text.replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("&amp;", "&")
    )

    return text


def get_channel_links(html):
    links = []

    patterns = [
        r'href=["\']([^"\']+/live/[^"\']+)["\']',
        r'href=["\']([^"\']*bhoomtv\.me/live/[^"\']+)["\']',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for match in matches:
            url = urljoin(
                CATEGORY_URL,
                match,
            )

            parsed = urlparse(url)

            if (
                parsed.netloc
                and "bhoomtv.me"
                not in parsed.netloc.lower()
            ):
                continue

            url = url.split("#", 1)[0]

            if url not in links:
                links.append(url)

    return links


def get_page_title(html):
    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        html,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    if not match:
        return ""

    title = re.sub(
        r"<[^>]+>",
        "",
        match.group(1),
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

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

    return title.strip()


def extract_urls(html):
    html = clean_html_text(
        html
    )

    hls = []
    dash = []
    youtube = []

    # ----------------------------
    # Direct HLS
    # ----------------------------
    hls_patterns = [
        (
            r'https?://'
            r'[^"\'<>\s]+'
            r'\.m3u8'
            r'(?:\?[^"\'<>\s]*)?'
        ),
        (
            r'["\']'
            r'([^"\']+\.m3u8'
            r'(?:\?[^"\']*)?)'
            r'["\']'
        ),
    ]

    for pattern in hls_patterns:
        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for match in matches:
            if isinstance(
                match,
                tuple,
            ):
                match = match[0]

            candidate = (
                match.strip()
            )

            candidate = (
                candidate
                .replace("\\/", "/")
            )

            if candidate.startswith(
                "//"
            ):
                candidate = (
                    "https:"
                    + candidate
                )

            elif not candidate.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                candidate = urljoin(
                    CATEGORY_URL,
                    candidate,
                )

            if candidate not in hls:
                hls.append(
                    candidate
                )

    # ----------------------------
    # DASH MPD
    # ----------------------------
    mpd_patterns = [
        (
            r'https?://'
            r'[^"\'<>\s]+'
            r'\.mpd'
            r'(?:\?[^"\'<>\s]*)?'
        ),
        (
            r'["\']'
            r'([^"\']+\.mpd'
            r'(?:\?[^"\']*)?)'
            r'["\']'
        ),
    ]

    for pattern in mpd_patterns:
        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for match in matches:
            if isinstance(
                match,
                tuple,
            ):
                match = match[0]

            candidate = (
                match.strip()
                .replace("\\/", "/")
            )

            if candidate.startswith(
                "//"
            ):
                candidate = (
                    "https:"
                    + candidate
                )

            elif not candidate.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                candidate = urljoin(
                    CATEGORY_URL,
                    candidate,
                )

            if candidate not in dash:
                dash.append(
                    candidate
                )

    # ----------------------------
    # YouTube
    # ----------------------------
    youtube_patterns = [
        (
            r'https?://'
            r'(?:www\.)?youtube\.com/'
            r'watch\?v=[A-Za-z0-9_-]+'
        ),
        (
            r'https?://'
            r'youtu\.be/'
            r'[A-Za-z0-9_-]+'
        ),
        (
            r'https?://'
            r'(?:www\.)?youtube\.com/'
            r'embed/[A-Za-z0-9_-]+'
        ),
    ]

    for pattern in youtube_patterns:
        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for candidate in matches:
            candidate = (
                candidate
                .replace("\\/", "/")
            )

            if candidate not in youtube:
                youtube.append(
                    candidate
                )

    return (
        hls,
        dash,
        youtube,
    )


def check_hls(url):
    try:
        response = requests.get(
            url,
            headers={
                **HEADERS,
                "Accept": "*/*",
            },
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        status = (
            response.status_code
        )

        if status >= 400:
            response.close()

            return (
                False,
                f"HTTP {status}",
            )

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        sample = b""

        try:
            for chunk in (
                response.iter_content(
                    chunk_size=4096
                )
            ):
                if chunk:
                    sample += chunk

                if len(sample) >= 16384:
                    break

        finally:
            response.close()

        text = sample.decode(
            "utf-8",
            errors="ignore",
        )

        valid = (
            "#EXTM3U" in text
            or "#EXT-X-" in text
            or (
                "application/vnd.apple.mpegurl"
                in content_type
            )
            or (
                "application/x-mpegurl"
                in content_type
            )
        )

        if valid:
            return (
                True,
                "VALID_HLS",
            )

        return (
            False,
            (
                "Response does not "
                "look like HLS"
            ),
        )

    except Exception as exc:
        return (
            False,
            str(exc),
        )


def main():
    print(
        "Scanning BhoomTV Malayalam..."
    )

    master_channels = (
        get_master_channels()
    )

    response = request_page(
        CATEGORY_URL
    )

    if response is None:
        raise SystemExit(
            "Could not load category page."
        )

    if response.status_code >= 400:
        raise SystemExit(
            (
                "Category page returned "
                f"HTTP {response.status_code}"
            )
        )

    category_html = (
        response.text
    )

    channel_links = (
        get_channel_links(
            category_html
        )
    )

    print(
        f"Channel pages found: "
        f"{len(channel_links)}"
    )

    results = []

    total_hls = 0
    valid_hls = 0
    total_mpd = 0
    total_youtube = 0

    for index, page_url in enumerate(
        channel_links,
        start=1,
    ):
        print(
            f"[{index}/"
            f"{len(channel_links)}] "
            f"{page_url}"
        )

        page_response = (
            request_page(
                page_url
            )
        )

        if page_response is None:
            results.append(
                {
                    "page_url":
                        page_url,
                    "name":
                        page_url,
                    "classification":
                        "PAGE_ERROR",
                    "hls":
                        [],
                    "dash":
                        [],
                    "youtube":
                        [],
                    "master_match":
                        False,
                }
            )

            continue

        if (
            page_response.status_code
            >= 400
        ):
            results.append(
                {
                    "page_url":
                        page_url,
                    "name":
                        page_url,
                    "classification":
                        (
                            "PAGE_ERROR "
                            f"HTTP "
                            f"{page_response.status_code}"
                        ),
                    "hls":
                        [],
                    "dash":
                        [],
                    "youtube":
                        [],
                    "master_match":
                        False,
                }
            )

            continue

        html = page_response.text

        name = (
            get_page_title(html)
            or page_url.rstrip("/")
            .split("/")[-1]
        )

        (
            hls,
            dash,
            youtube,
        ) = extract_urls(
            html
        )

        total_hls += len(hls)
        total_mpd += len(dash)
        total_youtube += (
            len(youtube)
        )

        checked_hls = []

        for hls_url in hls:
            ok, detail = check_hls(
                hls_url
            )

            if ok:
                valid_hls += 1

            checked_hls.append(
                {
                    "url":
                        hls_url,
                    "valid":
                        ok,
                    "detail":
                        detail,
                }
            )

        if checked_hls:
            if any(
                item["valid"]
                for item in checked_hls
            ):
                classification = (
                    "HLS_FOUND"
                )
            else:
                classification = (
                    "HLS_FOUND_BUT_FAILED"
                )

        elif dash:
            classification = (
                "DASH_FOUND"
            )

        elif youtube:
            classification = (
                "YOUTUBE_FOUND"
            )

        else:
            classification = (
                "NO_STREAM_IN_HTML"
            )

        master_match = (
            normalize_name(name)
            in master_channels
        )

        results.append(
            {
                "page_url":
                    page_url,
                "name":
                    name,
                "classification":
                    classification,
                "hls":
                    checked_hls,
                "dash":
                    dash,
                "youtube":
                    youtube,
                "master_match":
                    master_match,
            }
        )

        time.sleep(
            REQUEST_DELAY
        )

    report = [
        "# BhoomTV Malayalam Scan Report",
        "",
        f"Category: {CATEGORY_URL}",
        "",
        "# SUMMARY",
        "",
        (
            f"Channel pages found: "
            f"{len(channel_links)}"
        ),
        (
            f"HLS URLs found: "
            f"{total_hls}"
        ),
        (
            f"HLS URLs passing check: "
            f"{valid_hls}"
        ),
        (
            f"DASH/MPD URLs found: "
            f"{total_mpd}"
        ),
        (
            f"YouTube URLs found: "
            f"{total_youtube}"
        ),
        "",
    ]

    classification_counts = {}

    for item in results:
        key = item[
            "classification"
        ]

        classification_counts[
            key
        ] = (
            classification_counts.get(
                key,
                0,
            )
            + 1
        )

    report.extend(
        [
            "# CLASSIFICATIONS",
            "",
        ]
    )

    for key in sorted(
        classification_counts
    ):
        report.append(
            f"{key}: "
            f"{classification_counts[key]}"
        )

    report.extend(
        [
            "",
            "# CHANNEL DETAILS",
            "",
        ]
    )

    for item in results:
        report.append(
            f"## {item['name']}"
        )

        report.append(
            (
                "STATUS: "
                f"{item['classification']}"
            )
        )

        report.append(
            (
                "IN MASTER: "
                f"{'YES' if item['master_match'] else 'NO'}"
            )
        )

        report.append(
            (
                "PAGE: "
                f"{item['page_url']}"
            )
        )

        if item["hls"]:
            for hls_item in (
                item["hls"]
            ):
                report.append(
                    (
                        "HLS: "
                        f"{hls_item['url']}"
                    )
                )

                report.append(
                    (
                        "HLS CHECK: "
                        f"{hls_item['detail']}"
                    )
                )

        if item["dash"]:
            for dash_url in item[
                "dash"
            ]:
                report.append(
                    (
                        "DASH: "
                        f"{dash_url}"
                    )
                )

        if item["youtube"]:
            for youtube_url in (
                item["youtube"]
            ):
                report.append(
                    (
                        "YOUTUBE: "
                        f"{youtube_url}"
                    )
                )

        report.append("")

    missing = [
        item
        for item in results
        if not item[
            "master_match"
        ]
    ]

    report.extend(
        [
            "# NOT FOUND IN MASTER",
            "",
            (
                f"Count: "
                f"{len(missing)}"
            ),
            "",
        ]
    )

    for item in missing:
        report.append(
            (
                f"{item['name']} | "
                f"{item['classification']}"
            )
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
        "BHOOMTV MALAYALAM SCAN"
    )
    print(
        "=============================="
    )
    print(
        f"Channel pages: "
        f"{len(channel_links)}"
    )
    print(
        f"HLS found: "
        f"{total_hls}"
    )
    print(
        f"Valid HLS: "
        f"{valid_hls}"
    )
    print(
        f"DASH found: "
        f"{total_mpd}"
    )
    print(
        f"YouTube found: "
        f"{total_youtube}"
    )
    print(
        f"Missing from Master: "
        f"{len(missing)}"
    )
    print()
    print(
        "bhoomtv_malayalam_report.txt "
        "created."
    )


if __name__ == "__main__":
    main()
