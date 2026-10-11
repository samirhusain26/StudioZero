#!/bin/zsh
# Final render (paths relative to engines/motion/): ./render/render.sh <CompositionId> [out.mp4]
# Remotion's own AAC step leaves the encoder priming in the stream with no edit list (~43 ms late audio,
# enough to smear beat hits), so we render muted video + sample-exact WAV and mux with fdk-AAC,
# whose mp4 muxing writes the priming edit list. Then check sync against the WAV.
set -e
cd "${0:A:h}/.."
ID=$1; OUT=${2:-out/$ID.mp4}
R=./node_modules/.bin/remotion
if [[ "$ID" == LibraryEpisode ]]; then
  # Library quiz episode: props from LIBRARY_PROPS_FILE (frozen job input). fdk-AAC mux with the priming edit list,
  # 48 kHz stereo, fast-start; written to <out>.partial.mp4 and moved into place only after the sync/spec check passes.
  [[ -z "$LIBRARY_PROPS_FILE" ]] && { echo "LIBRARY_PROPS_FILE is required for LibraryEpisode" >&2; exit 1; }
  TMP=.audio-work/library_${OUT:t:r}; mkdir -p $TMP "${OUT:h}"
  # PNG frames: the project default (JPEG) makes x264 emit full-range yuvj420p; the contract needs yuv420p.
  $R render src/index.ts $ID $TMP/video.mp4 --props="$LIBRARY_PROPS_FILE" --codec=h264 --pixel-format=yuv420p --image-format=png --crf=${LIBRARY_CRF:-20} --x264-preset=slow --muted --log=error
  $R render src/index.ts $ID $TMP/audio.wav --props="$LIBRARY_PROPS_FILE" --codec=wav --log=error
  .venv/bin/python render/master_audio.py $TMP/audio.wav $TMP/master.wav   # −14 LUFS, ≤ −1 dBTP
  $R ffmpeg -v error -y -i $TMP/video.mp4 -i $TMP/master.wav -map 0:v -map 1:a -c:v copy \
    -c:a libfdk_aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart -shortest -f mp4 "$OUT.partial.mp4"
  .venv/bin/python render/check_sync.py "$OUT.partial.mp4" $TMP/master.wav
  mv "$OUT.partial.mp4" "$OUT"
  exit 0
fi
echo "Unknown composition $ID: only LibraryEpisode is registered" >&2
exit 1
