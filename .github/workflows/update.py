import subprocess
import os

PLAYLIST = "Playlist.m3u"

if not os.path.exists(PLAYLIST):
    print("Playlist.m3u not found")
    exit(1)

with open(PLAYLIST, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

new_lines = []

for line in lines:
    url = line.strip()

    if url.startswith("https://www.youtube.com") or url.startswith("http://www.youtube.com") \
       or url.startswith("https://youtu.be") or url.startswith("http://youtu.be"):

        print("Updating:", url)

        try:
            stream = subprocess.check_output(
                ["yt-dlp", "-g", url],
                text=True,
                timeout=60
            ).strip()

            if stream.startswith("http"):
                new_lines.append(stream + "\n")
                continue

        except Exception as e:
            print("Failed:", e)

    new_lines.append(line)

with open(PLAYLIST, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Playlist updated.")
