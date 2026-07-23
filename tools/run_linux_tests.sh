#!/usr/bin/env bash
set -euo pipefail

archive=${1:?usage: run_linux_tests.sh /path/to/b360gt-live-test.tar.gz}
test_dir=/tmp/b360gt-codex-test-20260723

mkdir -p "$test_dir"
tar -xzf "$archive" -C "$test_dir"
cd "$test_dir"

python - <<'PY'
import av
import hid
import numpy
import psutil
import usb
from PIL import __version__ as pillow_version

print("imports=ok")
print(f"numpy={numpy.__version__}")
print(f"pillow={pillow_version}")
print(f"pyusb={usb.__version__}")
print(f"pyav={av.__version__}")
print(f"hidapi={hid.__version__}")
print(f"psutil={psutil.__version__}")
PY

PYTHONPATH=src python -m unittest discover -s tests -v
