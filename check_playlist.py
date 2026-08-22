import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


MASTER_FILE = Path("Master.m3u")
STATUS_FILE = Path("playlist_status.json")
REPORT_FILE = Path("playlist_report.txt")

TIMEOUT = 15
HARD_FAILURE_LIMIT = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def load_previous_status():
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


def save_status(data):
    STATUS_FILE.write_text(
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def get_group(extinf):
    marker = 'group-title="'

    if marker not in extinf:
        return ""

    try:
        return (
            extinf.split(marker, 1)[1]
            .split('"', 1)[0]
            .strip()
        )
    except Exception:
        return ""


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

    entries = []

    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line.startswith("#EXTINF:"):
            i += 1
            continue

        extinf = line
        name = get_name(extinf)
        group = get_group(extinf)

        urls = []

        i += 1

        while i < len(lines):
            value = lines[i].strip()

            if value.startswith("#EXTINF:"):
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
                    "group": group,
                    "extinf": extinf,
                    "urls": urls,
                }
            )

    return entries


def parse_manifest_lines(text):
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def find_variant_url(base_url, lines):
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            j = i + 1

            while j < len(lines):
                candidate = lines[j]

                if not candidate.startswith("#"):
                    return urljoin(
                        base_url,
                        candidate,
                    )

                j += 1

    return None


def find_segment_url(base_url, lines):
    for line in lines:
        if line.startswith("#"):
            continue

        if ".m3u8" in line.lower():
            continue

        return urljoin(
            base_url,
            line,
        )

    return None


def test_segment(segment_url):
    try:
        response = requests.get(
            segment_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        status = response.status_code

        if status in (401, 403):
            response.close()

            return {
                "status":
                    "SEGMENT_ACCESS_RESTRICTED",
                "detail":
                    f"Segment HTTP {status}",
                "hard_failure":
                    False,
            }

        if status in (404, 410):
            response.close()

            return {
                "status":
                    "SEGMENT_FAILED",
                "detail":
                    f"Segment HTTP {status}",
                "hard_failure":
                    True,
            }

        if status >= 400:
            response.close()

            return {
                "status":
                    "SEGMENT_FAILED",
                "detail":
                    f"Segment HTTP {status}",
                "hard_failure":
                    False,
            }

        got_data = False

        for chunk in response.iter_content(
            chunk_size=4096
        ):
            if chunk:
                got_data = True
                break

        response.close()

        if got_data:
            return {
                "status":
                    "IPTV_PLAYABLE",
                "detail":
                    "Manifest and media segment reachable",
                "hard_failure":
                    False,
            }

        return {
            "status":
                "SEGMENT_FAILED",
            "detail":
                "Segment returned no data",
            "hard_failure":
                False,
        }

    except requests.exceptions.Timeout:
        return {
            "status":
                "SEGMENT_TIMEOUT",
            "detail":
                f"Segment timed out after {TIMEOUT}s",
            "hard_failure":
                True,
        }

    except requests.exceptions.RequestException as exc:
        return {
            "status":
                "SEGMENT_ERROR",
            "detail":
                str(exc),
            "hard_failure":
                False,
        }


def check_hls_deep(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        status = response.status_code

        if status in (401, 403):
            return {
                "status":
                    "ACCESS_RESTRICTED",
                "detail":
                    f"Manifest HTTP {status}",
                "hard_failure":
                    False,
            }

        if status in (404, 410):
            return {
                "status":
                    "HTTP_ERROR",
                "detail":
                    f"Manifest HTTP {status}",
                "hard_failure":
                    True,
            }

        if status >= 400:
            return {
                "status":
                    "HTTP_ERROR",
                "detail":
                    f"Manifest HTTP {status}",
                "hard_failure":
                    False,
            }

        text = response.text

        if (
            "#EXTM3U" not in text
            and "#EXT-X-" not in text
        ):
            return {
                "status":
                    "SUSPECT",
                "detail":
                    "Response does not look like HLS",
                "hard_failure":
                    False,
            }

        lines = parse_manifest_lines(
            text
        )

        variant_url = find_variant_url(
            response.url,
            lines,
        )

        if variant_url:
            variant_response = requests.get(
                variant_url,
                headers=HEADERS,
                timeout=TIMEOUT,
                allow_redirects=True,
            )

            variant_status = (
                variant_response.status_code
            )

            if variant_status >= 400:
                return {
                    "status":
                        "HTTP_ERROR",
                    "detail":
                        (
                            "Variant playlist "
                            f"HTTP {variant_status}"
                        ),
                    "hard_failure":
                        variant_status in (404, 410),
                }

            segment_url = find_segment_url(
                variant_response.url,
                parse_manifest_lines(
                    variant_response.text
                ),
            )

        else:
            segment_url = find_segment_url(
                response.url,
                lines,
            )

        if not segment_url:
            return {
                "status":
                    "HLS_NO_SEGMENT",
                "detail":
                    "No media segment found",
                "hard_failure":
                    False,
            }

        return test_segment(
            segment_url
        )

    except requests.exceptions.Timeout:
        return {
            "status": "TIMEOUT",
            "detail":
                f"Timed out after {TIMEOUT}s",
            "hard_failure": True,
        }

    except requests.exceptions.RequestException as exc:
        return {
            "status": "ERROR",
            "detail": str(exc),
            "hard_failure": False,
        }


def check_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in (
        "http",
        "https",
    ):
        return {
            "status": "INVALID",
            "detail":
                "Unsupported URL scheme",
            "hard_failure": False,
        }

    lower_url = url.lower()

    if (
        "youtube.com/watch" in lower_url
        or "youtu.be/" in lower_url
    ):
        return {
            "status":
                "WEBPAGE_SOURCE",
            "detail":
                "YouTube page URL, not direct HLS",
            "hard_failure":
                False,
        }

    if ".m3u8" in lower_url:
        return check_hls_deep(url)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        status = response.status_code

        if status in (401, 403):
            return {
                "status":
                    "ACCESS_RESTRICTED",
                "detail":
                    f"HTTP {status}",
                "hard_failure":
                    False,
            }

        if status in (404, 410):
            return {
                "status":
                    "HTTP_ERROR",
                "detail":
                    f"HTTP {status}",
                "hard_failure":
                    True,
            }

        if status >= 400:
            return {
                "status":
                    "HTTP_ERROR",
                "detail":
                    f"HTTP {status}",
                "hard_failure":
                    False,
            }

        return {
            "status":
                "WEBPAGE_OR_UNKNOWN",
            "detail":
                f"HTTP {status}",
            "hard_failure":
                False,
        }

    except requests.exceptions.Timeout:
        return {
            "status":
                "TIMEOUT",
            "detail":
                f"Timed out after {TIMEOUT}s",
            "hard_failure":
                True,
        }

    except requests.exceptions.RequestException as exc:
        return {
            "status":
                "ERROR",
            "detail":
                str(exc),
            "hard_failure":
                False,
        }


def classify_channel(
    results,
    old_info,
):
    working = [
        item
        for item in results
        if item["status"]
        == "IPTV_PLAYABLE"
    ]

    if working:
        return {
            "classification": "WORKING",
            "selected_url":
                working[0]["url"],
            "hard_failures": 0,
        }

    restricted = [
        item
        for item in results
        if item["status"] in (
            "ACCESS_RESTRICTED",
            "SEGMENT_ACCESS_RESTRICTED",
        )
    ]

    if restricted:
        return {
            "classification":
                "ACCESS_RESTRICTED",
            "selected_url":
                restricted[0]["url"],
            "hard_failures": 0,
        }

    all_hard = (
        len(results) > 0
        and all(
            item["hard_failure"]
            for item in results
        )
    )

    old_count = old_info.get(
        "consecutive_hard_failures",
        old_info.get(
            "consecutive_failures",
            0,
        ),
    )

    if all_hard:
        hard_count = old_count + 1
    else:
        hard_count = 0

    if hard_count == 1:
        classification = (
            "TEMPORARY_FAILURE"
        )
    elif hard_count == 2:
        classification = (
            "REPEATED_FAILURE"
        )
    elif hard_count >= HARD_FAILURE_LIMIT:
        classification = (
            "CONSISTENTLY_BROKEN"
        )
    else:
        classification = (
            "CHECK_REQUIRED"
        )

    return {
        "classification":
            classification,
        "selected_url":
            None,
        "hard_failures":
            hard_count,
    }


def main():
    entries = parse_master()
    previous = load_previous_status()

    current = {}
    report = [
        "# Playlist URL Check Report",
        "",
        f"Checked {len(entries)} channels",
        time.strftime(
            "Time: %Y-%m-%d "
            "%H:%M:%S UTC",
            time.gmtime(),
        ),
        "",
    ]

    print(
        f"Checking {len(entries)} "
        "channels from Master.m3u"
    )

    for index, entry in enumerate(
        entries,
        start=1,
    ):
        name = entry["name"]
        group = entry["group"]
        urls = entry["urls"]

        print()
        print(
            f"[{index}/{len(entries)}] "
            f"{name}"
        )

        results = []

        for url_index, url in enumerate(
            urls,
            start=1,
        ):
            print(
                f"  URL {url_index}/"
                f"{len(urls)}"
            )

            result = check_url(url)

            result["url"] = url
            results.append(result)

            print(
                f"    {result['status']}"
            )

        old_info = previous.get(
            name,
            {},
        )

        decision = classify_channel(
            results,
            old_info,
        )

        classification = (
            decision["classification"]
        )

        selected_url = (
            decision["selected_url"]
        )

        hard_failures = (
            decision["hard_failures"]
        )

        current[name] = {
            "name": name,
            "group": group,
            "classification":
                classification,
            "selected_url":
                selected_url,
            "consecutive_hard_failures":
                hard_failures,
            "consecutive_failures":
                hard_failures,
            "urls":
                results,
            "last_checked_utc":
                time.strftime(
                    "%Y-%m-%d "
                    "%H:%M:%S UTC",
                    time.gmtime(),
                ),
        }

        report.extend(
            [
                f"## {name}",
                f"Group: {group}",
                (
                    "Classification: "
                    f"{classification}"
                ),
                (
                    "Selected URL: "
                    f"{selected_url or 'NONE'}"
                ),
                (
                    "Consecutive hard "
                    "failures: "
                    f"{hard_failures}"
                ),
                "",
            ]
        )

        for item in results:
            report.extend(
                [
                    f"URL: {item['url']}",
                    (
                        f"Status: "
                        f"{item['status']}"
                    ),
                    (
                        f"Detail: "
                        f"{item['detail']}"
                    ),
                    "",
                ]
            )

        time.sleep(0.1)

    save_status(current)

    REPORT_FILE.write_text(
        "\n".join(report)
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "playlist_status.json updated"
    )
    print(
        "playlist_report.txt updated"
    )


if __name__ == "__main__":
    main()
