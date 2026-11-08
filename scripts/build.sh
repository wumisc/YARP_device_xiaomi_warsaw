#!/usr/bin/env bash
# Build YARP (TWRP 16 / GUI2) recovery for SM8750, including REDMI K90 Ultra (warsaw).
# Usage: bash scripts/build.sh {sync|build|package}
set -euo pipefail

builder_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="${YARP_SOURCE_DIR:-/build/yarp}"
dist_root="${YARP_DIST_DIR:-${builder_root}/dist}"
lock_file="${builder_root}/sources.json"
mkdir -p "${source_root}" "${dist_root}"

json_get() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))'"$1"')' "${lock_file}"
}

case "${1:-}" in
  sync)
    cd "${source_root}"
    repo init -u "$(json_get '["manifest"]["url"]')" \
      -b "$(json_get '["manifest"]["revision"]')" \
      --depth=1 --no-clone-bundle --no-tags
    repo sync -c -j "${SYNC_JOBS:-8}" --fail-fast --no-tags --no-clone-bundle \
      --optimized-fetch --retry-fetches=3

    # Pin the YARP/GUI2 projects to the revisions recorded in sources.json.
    while read -r path sha; do
      [ -n "${path}" ] || continue
      echo "Pinning ${path} -> ${sha}"
      git -C "${path}" fetch --depth=1 origin "${sha}" \
        || git -C "${path}" fetch origin
      git -C "${path}" checkout -f "${sha}"
    done < <(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
for p in d["projects"]:
    print(p["path"], p["revision"])
' "${lock_file}")

    # The unified SM8750/SM8850 device tree is not part of the TWRP manifest.
    device_path="$(json_get '["device"]["path"]')"
    device_url="$(json_get '["device"]["url"]')"
    device_sha="$(json_get '["device"]["revision"]')"
    mkdir -p "$(dirname "${device_path}")"
    if [ ! -d "${device_path}/.git" ]; then
      git clone --filter=blob:none --no-checkout "${device_url}" "${device_path}"
    fi
    git -C "${device_path}" fetch --depth=1 origin "${device_sha}" \
      || git -C "${device_path}" fetch origin
    git -C "${device_path}" checkout -f "${device_sha}"
    echo "Device tree ${device_path} -> ${device_sha}"
    git -C "${device_path}" log -1 --format='%H %cd %s' --date=iso

    repo manifest -r -o "${dist_root}/source-manifest.xml"
    cp "${lock_file}" "${dist_root}/sources.json"
    df -h "${source_root}"
    available_kib="$(df -Pk "${source_root}" | awk 'NR == 2 {print $4}')"
    if (( available_kib < 15 * 1024 * 1024 )); then
      echo '::error::Less than 15 GiB remains after the source sync.'
      exit 1
    fi
    ;;

  build)
    cd "${source_root}"
    export ALLOW_MISSING_DEPENDENCIES=true
    export USE_CCACHE=0
    export MALLOC_ARENA_MAX=2
    export SOONG_GOMEMLIMIT=8GiB
    export GOMEMLIMIT=8GiB
    export GOGC=50
    export GOMAXPROCS=2
    export SOONG_UI_NINJA_ARGS=-j1
    export NINJA_HIGHMEM_NUM_JOBS=1
    export YARP_PLATFORM="$(json_get '["platform"]')"
    lunch_target="$(json_get '["lunch"]')"
    set +u
    source build/envsetup.sh
    lunch "${lunch_target}"
    mka -j"${BUILD_JOBS:-2}" installclean
    mka -j"${BUILD_JOBS:-2}" recoveryimage
    ;;

  package)
    product="$(json_get '["product"]')"
    product_root="${source_root}/out/target/product/${product}"
    image="${product_root}/recovery.img"
    if [ ! -f "${image}" ]; then
      echo "::error::Missing ${image}"
      exit 1
    fi
    short_sha="$(json_get '["device"]["revision"]')"
    short_sha="${short_sha:0:7}"
    out_name="YARP-16-sm8750-warsaw-${short_sha}-recovery.img"
    python3 - "${image}" > "${dist_root}/verification.json" <<'PY'
import json, struct, sys, os
p = sys.argv[1]
with open(p, "rb") as f:
    head = f.read(4096)
ok = head[:8] == b"ANDROID!"
kernel_size, ramdisk_size = struct.unpack_from("<II", head, 8)
header_version = struct.unpack_from("<I", head, 40)[0]
result = {
    "image": os.path.basename(p),
    "bytes": os.path.getsize(p),
    "android_magic": ok,
    "header_version": header_version,
    "kernel_size": kernel_size,
    "ramdisk_size": ramdisk_size,
    "expected": "ramdisk-only v4 image, kernel supplied by vendor_boot",
    "passed": bool(ok and header_version == 4 and kernel_size == 0 and ramdisk_size > 0),
}
print(json.dumps(result, indent=2))
if not result["passed"]:
    sys.exit("recovery.img failed verification")
PY
    cp "${image}" "${dist_root}/${out_name}"
    cd "${dist_root}"
    sha256sum "${out_name}" > SHA256SUMS.txt
    cat verification.json
    ls -lh .
    ;;

  *)
    printf 'Usage: %s {sync|build|package}\n' "$0" >&2
    exit 2
    ;;
esac
