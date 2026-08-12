from pathlib import Path

playlist = Path("Playlist.m3u")

if not playlist.exists():
    raise SystemExit("Playlist.m3u not found")

text = playlist.read_text(encoding="utf-8")

# Normalize line endings
text = text.replace("\r\n", "\n").replace("\r", "\n")

# Ensure M3U header
if not text.startswith("#EXTM3U"):
    text = "#EXTM3U\n" + text

# Remove trailing whitespace and excessive blank lines
lines = [line.rstrip() for line in text.split("\n")]

cleaned = []
previous_blank = False

for line in lines:
    if not line.strip():
        if not previous_blank:
            cleaned.append("")
        previous_blank = True
    else:
        cleaned.append(line)
        previous_blank = False

playlist.write_text(
    "\n".join(cleaned).rstrip() + "\n",
    encoding="utf-8"
)

print("Playlist cleaned successfully.")
