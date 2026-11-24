#!/usr/bin/env bash
# Raspberry Pi 5 (Pi OS Trixie) setup: Python 3.11 venv + packages + models.
# Usage:  bash setup_pi.sh        (idempotent - safe to rerun)
set -euo pipefail
cd "$(dirname "$0")"
DIR="$PWD"
PYVER=3.11.11
step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

step "1. apt packages"
PKGS="git curl v4l-utils fonts-nanum build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev
  libsqlite3-dev libncurses-dev xz-utils tk-dev libffi-dev liblzma-dev"
if dpkg -s $PKGS >/dev/null 2>&1; then echo "already installed"; else sudo apt update && sudo apt install -y $PKGS; fi

step "2. Python $PYVER (pyenv; first build takes ~10 min)"
export PYENV_ROOT="$HOME/.pyenv"
[ -d "$PYENV_ROOT" ] || git clone --depth 1 https://github.com/pyenv/pyenv.git "$PYENV_ROOT"
"$PYENV_ROOT/bin/pyenv" install -s "$PYVER"
PYBASE="$PYENV_ROOT/versions/$PYVER/bin/python"

step "3. venv + pip packages"
[ -x .venv/bin/python ] || "$PYBASE" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

step "4. models"
mkdir -p models known events
get() { [ -s "models/$1" ] && echo "models/$1 exists" || { echo "download $1"; curl -fSL --retry 3 -o "models/$1" "$2"; }; }
get yunet.onnx            https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
get sface.onnx            https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
if [ ! -s models/ssd_mobilenet_v1.tflite ]; then
  echo "download ssd_mobilenet_v1"
  curl -fSL --retry 3 -o models/ssd.zip https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
  .venv/bin/python -c "import zipfile; open('models/ssd_mobilenet_v1.tflite','wb').write(zipfile.ZipFile('models/ssd.zip').read('detect.tflite'))"
  rm models/ssd.zip
fi
ls -lh models

step "5. check"
.venv/bin/python - <<'EOF'
import cv2, numpy, time
from seccam import config as C
from seccam.detectors import PersonDetector, FaceID
cfg = C.load()
p = PersonDetector(C.resolve(cfg["person"]["model"]))
f = FaceID(C.resolve(cfg["face"]["detector"]), C.resolve(cfg["face"]["recognizer"]))
img = numpy.zeros((480, 640, 3), numpy.uint8)
p(img); t = time.time(); [p(img) for _ in range(5)]
print(f"numpy {numpy.__version__} | opencv {cv2.__version__} | person det {(time.time()-t)/5*1000:.0f} ms")
EOF
ls /dev/video* 2>/dev/null || echo "!! no /dev/video* - plug in the USB webcam"
chmod +x run.sh
step "DONE - run:  ./run.sh   then open http://$(hostname -I | awk '{print $1}'):8000"
