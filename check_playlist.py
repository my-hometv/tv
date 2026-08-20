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

    current_name = "Unknown"
    current_group = ""

    for raw_line in lines:
        line = raw_line.strip()

        if line.startswith("#EXTINF:"):
            if "," in line:
                current_name = (
                    line.split(",", 1)[1]
                    .strip()
                )
            else:
                current_name = "Unknown"

            current_group = get_group(line)

        elif (
            line
            and not line.startswith("#")
            and line.startswith(
                ("http://", "https://")
            )
        ):
            entries.append(
                {
                    "name": current_name,
                    "group": current_group,
                    "url": line,
                }
            )

            current_name = "Unknown"
            current_group = ""

    return entries


def fetch_text(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    return response


def parse_manifest_lines(text):
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def find_variant_url(
    base_url,
    lines,
):
    for i, line in enumerate(lines):
        if line.startswith(
            "#EXT-X-STREAM-INF"
        ):
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


def find_segment_url(
    base_url,
    lines,
):
    for line in lines:
        if line.startswith("#"):
            continue

        lower = line.lower()

        # Avoid choosing another playlist
        # as the media segment.
        if ".m3u8" in lower:
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
                "ok": False,
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
                "ok": False,
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
                "ok": False,
                "status":
                    "SEGMENT_FAILED",
                "detail":
                    f"Segment HTTP {status}",
                "hard_failure":
                    False,
            }

        # Read only a small amount.
        found_data = False

        for chunk in response.iter_content(
            chunk_size=4096
        ):
            if chunk:
                found_data = True
                break

        response.close()

        if found_data:
            return {
                "ok": True,
                "status":
                    "IPTV_PLAYABLE",
                "detail":
                    "Manifest and media segment reachable",
                "hard_failure":
                    False,
            }

        return {
            "ok": False,
            "status":
                "SEGMENT_FAILED",
            "detail":
                "Segment returned no data",
            "hard_failure":
                False,
        }

    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "status":
                "SEGMENT_TIMEOUT",
            "detail":
                f"Segment timed out after {TIMEOUT}s",
            "hard_failure":
                True,
        }

    except requests.exceptions.RequestException as exc:
        detail = str(exc)

        hard_terms = [
            "failed to resolve",
            "nameresolutionerror",
            "name or service not known",
            "connection refused",
            "failed to establish a new connection",
        ]

        hard_failure = any(
            term in detail.lower()
            for term in hard_terms
        )

        return {
            "ok": False,
            "status":
                "SEGMENT_ERROR",
            "detail": detail,
            "hard_failure":
                hard_failure,
        }


def check_hls_deep(url):
    try:
        response = fetch_text(url)

        status_code = (
            response.status_code
        )

        if status_code in (401, 403):
            return {
                "status":
                    "ACCESS_RESTRICTED",
                "detail":
                    f"Manifest HTTP {status_code}",
                "hard_failure":
                    False,
            }

        if status_code in (404, 410):
            return {
                "status":
                    "HTTP_ERROR",
                "detail":
                    f"Manifest HTTP {status_code}",
                "hard_failure":
                    True,
            }

        if status_code >= 400:
            return {
                "status":
                    "HTTP_ERROR",
                "detail":
                    f"Manifest HTTP {status_code}",
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
                    (
                        f"HTTP {status_code}, "
                        "response does not look like HLS"
                    ),
                "hard_failure":
                    False,
            }

        lines = parse_manifest_lines(
            text
        )

        variant_url = (
            find_variant_url(
                response.url,
                lines,
            )
        )

        # Master playlist:
        # follow one variant.
        if variant_url:
            try:
                variant_response = (
                    fetch_text(
                        variant_url
                    )
                )

                variant_status = (
                    variant_response
                    .status_code
                )

                if variant_status in (
                    401,
                    403,
                ):
                    return {
                        "status":
                            "ACCESS_RESTRICTED",
                        "detail":
                            (
                                "Variant playlist "
                                f"HTTP {variant_status}"
                            ),
                        "hard_failure":
                            False,
                    }

                if variant_status in (
                    404,
                    410,
                ):
                    return {
                        "status":
                            "HTTP_ERROR",
                        "detail":
                            (
                                "Variant playlist "
                                f"HTTP {variant_status}"
                            ),
                        "hard_failure":
                            True,
                    }

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
                            False,
                    }

                variant_text = (
                    variant_response.text
                )

                variant_lines = (
                    parse_manifest_lines(
                        variant_text
                    )
                )

                segment_url = (
                    find_segment_url(
                        variant_response.url,
                        variant_lines,
                    )
                )

            except requests.exceptions.RequestException as exc:
                return {
                    "status":
                        "ERROR",
                    "detail":
                        (
                            "Variant fetch failed: "
                            f"{exc}"
                        ),
                    "hard_failure":
                        False,
                }

        else:
            # Media playlist directly.
            segment_url = (
                find_segment_url(
                    response.url,
                    lines,
                )
            )

        if not segment_url:
            return {
                "status":
                    "HLS_NO_SEGMENT",
                "detail":
                    (
                        "HLS manifest loaded but "
                        "no media segment found"
                    ),
                "hard_failure":
                    False,
            }

        segment_result = (
            test_segment(
                segment_url
            )
        )

        return {
            "status":
                segment_result[
                    "status"
                ],
            "detail":
                segment_result[
                    "detail"
                ],
            "hard_failure":
                segment_result[
                    "hard_failure"
                ],
        }

    except requests.exceptions.Timeout:
        return {
            "status": "TIMEOUT",
            "detail":
                (
                    f"Manifest timed out "
                    f"after {TIMEOUT}s"
                ),
            "hard_failure": True,
        }

    except requests.exceptions.RequestException as exc:
        detail = str(exc)

        hard_terms = [
            "failed to resolve",
            "nameresolutionerror",
            "name or service not known",
            "connection refused",
            "failed to establish a new connection",
        ]

        hard_failure = any(
            term in detail.lower()
            for term in hard_terms
        )

        return {
            "status": "ERROR",
            "detail": detail,
            "hard_failure":
                hard_failure,
        }


def check_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in (
        "http",
        "https",
    ):
        return {
            "status":
                "INVALID",
            "detail":
                "Unsupported URL scheme",
            "hard_failure":
                False,
        }

    lower_url = url.lower()

    # YouTube watch pages are source pages,
    # not direct IPTV HLS streams.
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
        return check_hls_deep(
            url
        )

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


def old_result_was_hard(info):
    if not info:
        return False

    if info.get(
        "hard_failure"
    ) is True:
        return True

    status = info.get(
        "last_status",
        "",
    )

    detail = info.get(
        "last_detail",
        "",
    ).lower()

    if status in (
        "TIMEOUT",
        "SEGMENT_TIMEOUT",
    ):
        return True

    hard_terms = [
        "http 404",
        "http 410",
        "failed to resolve",
        "nameresolutionerror",
        "name or service not known",
        "connection refused",
        "failed to establish a new connection",
    ]

    return any(
        term in detail
        for term in hard_terms
    )


def classify(
    status,
    hard_failures,
):
    if status == "IPTV_PLAYABLE":
        return "WORKING"

    if status in (
        "ACCESS_RESTRICTED",
        "SEGMENT_ACCESS_RESTRICTED",
    ):
        return "ACCESS_RESTRICTED"

    if status in (
        "WEBPAGE_SOURCE",
        "WEBPAGE_OR_UNKNOWN",
        "SUSPECT",
        "HLS_NO_SEGMENT",
    ):
        return "CHECK_REQUIRED"

    if hard_failures == 1:
        return "TEMPORARY_FAILURE"

    if hard_failures == 2:
        return "REPEATED_FAILURE"

    if (
        hard_failures
        >= HARD_FAILURE_LIMIT
    ):
        return "CONSISTENTLY_BROKEN"

    return "CHECK_REQUIRED"


def main():
    entries = parse_master()
    previous = load_previous_status()

    current = {}

    status_counts = {}
    class_counts = {}

    report = [
        "# Playlist URL Check Report",
        "",
        f"Checked {len(entries)} URLs",
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
        url = entry["url"]

        print(
            f"[{index}/{len(entries)}] "
            f"{name}"
        )

        result = check_url(
            url
        )

        status = result[
            "status"
        ]

        detail = result[
            "detail"
        ]

        hard_failure = (
            result[
                "hard_failure"
            ]
        )

        old = previous.get(
            url,
            {},
        )

        old_count = old.get(
            "consecutive_hard_failures",
            old.get(
                "consecutive_failures",
                0,
            ),
        )

        if status == "IPTV_PLAYABLE":
            hard_count = 0

        elif hard_failure:
            if old_result_was_hard(
                old
            ):
                hard_count = (
                    old_count + 1
                )
            else:
                hard_count = 1

        else:
            hard_count = 0

        classification = classify(
            status,
            hard_count,
        )

        checked_time = (
            time.strftime(
                "%Y-%m-%d "
                "%H:%M:%S UTC",
                time.gmtime(),
            )
        )

        current[url] = {
            "name": name,
            "group": group,
            "last_status":
                status,
            "last_detail":
                detail,
            "hard_failure":
                hard_failure,
            "consecutive_hard_failures":
                hard_count,
            "consecutive_failures":
                hard_count,
            "classification":
                classification,
            "last_checked_utc":
                checked_time,
        }

        status_counts[
            status
        ] = (
            status_counts.get(
                status,
                0,
            )
            + 1
        )

        class_counts[
            classification
        ] = (
            class_counts.get(
                classification,
                0,
            )
            + 1
        )

        print(
            f"  {status} | "
            f"{classification} | "
            f"hard failures="
            f"{hard_count}"
        )

        report.extend(
            [
                f"## {name}",
                f"Group: {group}",
                f"Status: {status}",
                (
                    "Classification: "
                    f"{classification}"
                ),
                (
                    "Consecutive hard "
                    "failures: "
                    f"{hard_count}"
                ),
                f"Detail: {detail}",
                f"URL: {url}",
                "",
            ]
        )

        time.sleep(0.15)

    save_status(
        current
    )

    report.extend(
        [
            "# SUMMARY BY STATUS",
            "",
        ]
    )

    for key in sorted(
        status_counts
    ):
        report.append(
            f"{key}: "
            f"{status_counts[key]}"
        )

    report.extend(
        [
            "",
            (
                "# SUMMARY BY "
                "CLASSIFICATION"
            ),
            "",
        ]
    )

    for key in [
        "WORKING",
        "ACCESS_RESTRICTED",
        "CHECK_REQUIRED",
        "TEMPORARY_FAILURE",
        "REPEATED_FAILURE",
        "CONSISTENTLY_BROKEN",
    ]:
        report.append(
            f"{key}: "
            f"{class_counts.get(key, 0)}"
        )

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
