import json
import time
from pathlib import Path
from urllib.parse import urlparse

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


def is_hls_response(
    content_type,
    sample_text,
):
    content_type = content_type.lower()

    return (
        "#EXTM3U" in sample_text
        or "#EXT-X-" in sample_text
        or "application/vnd.apple.mpegurl"
        in content_type
        or "application/x-mpegurl"
        in content_type
    )


def check_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in (
        "http",
        "https",
    ):
        return {
            "status": "INVALID",
            "detail": "Unsupported URL scheme",
            "hard_failure": False,
        }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        status_code = response.status_code

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
        )

        # 401/403 are not proof that a stream
        # is offline. They can depend on
        # headers, region or client context.
        if status_code in (401, 403):
            response.close()

            return {
                "status":
                    "ACCESS_RESTRICTED",
                "detail":
                    f"HTTP {status_code}",
                "hard_failure":
                    False,
            }

        # 404 and 410 are strong failures.
        if status_code in (404, 410):
            response.close()

            return {
                "status": "HTTP_ERROR",
                "detail":
                    f"HTTP {status_code}",
                "hard_failure": True,
            }

        # Other HTTP errors are uncertain.
        if status_code >= 400:
            response.close()

            return {
                "status": "HTTP_ERROR",
                "detail":
                    f"HTTP {status_code}",
                "hard_failure": False,
            }

        sample = b""

        try:
            for chunk in response.iter_content(
                chunk_size=4096
            ):
                sample += chunk

                if len(sample) >= 16384:
                    break
        finally:
            response.close()

        sample_text = sample.decode(
            "utf-8",
            errors="ignore",
        )

        if is_hls_response(
            content_type,
            sample_text,
        ):
            return {
                "status": "OK",
                "detail": (
                    f"HTTP {status_code}, "
                    "HLS playlist"
                ),
                "hard_failure": False,
            }

        if ".m3u8" in url.lower():
            return {
                "status": "SUSPECT",
                "detail": (
                    f"HTTP {status_code}, "
                    "response not recognized "
                    "as HLS"
                ),
                "hard_failure": False,
            }

        return {
            "status":
                "WEBPAGE_OR_UNKNOWN",
            "detail":
                f"HTTP {status_code}",
            "hard_failure": False,
        }

    except requests.exceptions.Timeout:
        return {
            "status": "TIMEOUT",
            "detail": (
                f"Timed out after "
                f"{TIMEOUT}s"
            ),
            "hard_failure": True,
        }

    except (
        requests.exceptions.RequestException
    ) as exc:
        detail = str(exc)

        hard_terms = [
            "Failed to resolve",
            "NameResolutionError",
            "Name or service not known",
            "No address associated with hostname",
            "Connection refused",
            "Failed to establish a new connection",
        ]

        hard_failure = any(
            term.lower() in detail.lower()
            for term in hard_terms
        )

        return {
            "status": "ERROR",
            "detail": detail,
            "hard_failure": hard_failure,
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "detail": str(exc),
            "hard_failure": False,
        }


def old_result_was_hard(info):
    if not info:
        return False

    if info.get("hard_failure") is True:
        return True

    status = info.get(
        "last_status",
        "",
    )

    detail = info.get(
        "last_detail",
        "",
    ).lower()

    if status == "TIMEOUT":
        return True

    if "http 404" in detail:
        return True

    if "http 410" in detail:
        return True

    hard_terms = [
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
    if status == "OK":
        return "WORKING"

    if status == "ACCESS_RESTRICTED":
        return "ACCESS_RESTRICTED"

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

        result = check_url(url)

        status = result["status"]
        detail = result["detail"]
        hard_failure = (
            result["hard_failure"]
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

        if status == "OK":
            hard_count = 0

        elif hard_failure:
            if old_result_was_hard(old):
                hard_count = old_count + 1
            else:
                hard_count = 1

        else:
            # Access restricted / uncertain
            # does not count toward hiding.
            hard_count = 0

        classification = classify(
            status,
            hard_count,
        )

        checked_time = time.strftime(
            "%Y-%m-%d "
            "%H:%M:%S UTC",
            time.gmtime(),
        )

        current[url] = {
            "name": name,
            "group": group,
            "last_status": status,
            "last_detail": detail,
            "hard_failure":
                hard_failure,
            "consecutive_hard_failures":
                hard_count,
            # Keep old field too for
            # compatibility.
            "consecutive_failures":
                hard_count,
            "classification":
                classification,
            "last_checked_utc":
                checked_time,
        }

        status_counts[status] = (
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

    save_status(current)

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
