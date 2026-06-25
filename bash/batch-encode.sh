#!/usr/bin/env bash
set -euo pipefail

# Encodes any non-AV1, non-HDR video with first video-stream height >= 1080 to AV1+Opus,
# writing output next to the input as: "<name>_av1<ext>"
# Requires ffprobe + ffmpeg in PATH.
#
# Note: -map 0:v:0 -map 0:a:0 keeps only the first video and first audio stream.
# Subtitles, secondary audio tracks, and chapters are NOT carried over.

extensions=(mp4 mkv mov m4v webm avi ts m2ts mts wmv flv 3gp)

# Build a case-insensitive find expression matching any of the extensions.
find_args=()
for e in "${extensions[@]}"; do
  find_args+=(-iname "*.${e}" -o)
done
unset 'find_args[${#find_args[@]}-1]'  # drop trailing -o

find . -type f \( "${find_args[@]}" \) -print0 |
while IFS= read -r -d '' inFile; do

  dir=$(dirname -- "$inFile")
  base=$(basename -- "$inFile")
  ext="${base##*.}"
  name="${base%.*}"

  # Skip files that already look like outputs.
  if [[ "$name" == *_av1 ]]; then
    continue
  fi

  # Probe codec, height, frame rate, and color transfer of first video stream.
  probe=$(ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,height,r_frame_rate,color_transfer \
    -of default=nokey=1:noprint_wrappers=1 "$inFile" 2>/dev/null) || true

  codec=$(sed -n '1p' <<<"$probe")
  h=$(sed -n '2p' <<<"$probe")
  rate=$(sed -n '3p' <<<"$probe")
  transfer=$(sed -n '4p' <<<"$probe")

  if [[ "$codec" == "av1" ]]; then
    echo "SKIP (already AV1): $inFile"
    continue
  fi

  # HDR sources need tone mapping to look right in SDR; this script does not
  # do that, so skip rather than silently producing washed-out output.
  if [[ "$transfer" == "smpte2084" || "$transfer" == "arib-std-b67" ]]; then
    echo "SKIP (HDR $transfer, no tonemap): $inFile" >&2
    continue
  fi

  if ! [[ "$h" =~ ^[0-9]+$ ]]; then
    echo "SKIP (ffprobe returned no height): $inFile" >&2
    continue
  fi

  if (( h >= 1080 )); then
    # Parse frame rate (e.g., 30000/1001) into numeric fps.
    fps=0
    if [[ "$rate" =~ ^([0-9]+)[[:space:]]*/[[:space:]]*([0-9]+)$ ]]; then
      num=${BASH_REMATCH[1]}
      den=${BASH_REMATCH[2]}
      if (( den != 0 )); then
        fps=$(awk "BEGIN { printf \"%.4f\", $num / $den }")
      fi
    fi

    is4k=0; (( h >= 2160 )) && is4k=1
    is60=0; awk "BEGIN { exit !($fps >= 50.0) }" && is60=1

    if (( is4k && is60 )); then
      maxRateK=28000
    elif (( is4k )); then
      maxRateK=18000
    elif (( is60 )); then
      maxRateK=10000
    else
      maxRateK=6000
    fi

    buffSizeK=$(( maxRateK * 2 ))

    outFile="${dir}/${name}_av1.${ext}"

    # Skip if output already exists.
    if [[ -e "$outFile" ]]; then
      echo "SKIP (exists): $outFile"
      continue
    fi

    printf 'ENCODE (%sp @ %.2f fps, maxRate %sk): %s\n' "$h" "$fps" "$maxRateK" "$inFile"
    echo " -> $outFile"

    if ffmpeg -nostdin -hide_banner -y -i "$inFile" \
      -map 0:v:0 -map 0:a:0 \
      -c:v libsvtav1 -preset 4 -crf 24 -maxrate "${maxRateK}k" -bufsize "${buffSizeK}k" -g 240 -pix_fmt yuv420p10le \
      -c:a libopus -b:a 128k -movflags +faststart \
      "$outFile"; then
      # Carry over original mtime so date-sorted media libraries keep ordering.
      touch -r "$inFile" "$outFile"
    else
      echo "ffmpeg failed for: $inFile" >&2
      [[ -e "$outFile" ]] && rm -f "$outFile"
    fi
  fi
done
