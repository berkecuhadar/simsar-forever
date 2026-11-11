"""Build the release archives into dist/.

    python scripts/build_release.py            build both zips
    python scripts/build_release.py --test     run the test suite first

Produces:
    dist/simsar-forever-<version>.zip          the app, with the web UI already built (no Node.js needed)
    dist/SimsarForeverExport-<version>.zip     the in-game addon, laid out for CurseForge
    dist/SHA256SUMS.txt
"""

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
STATIC = ROOT / "simsar_forever" / "web" / "static"
ADDON = ROOT / "addon" / "SimsarForeverExport"


def run(cmd, cwd=ROOT):
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, shell=sys.platform == "win32" and cmd[0] == "npm")


def versions():
    found = {
        "simsar_forever/__init__.py": re.search(r'__version__ = "([^"]+)"',
                                                (ROOT / "simsar_forever" / "__init__.py").read_text()).group(1),
        "pyproject.toml": re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1),
        "frontend/package.json": re.search(r'"version": "([^"]+)"', (ROOT / "frontend" / "package.json").read_text()).group(1),
        "addon .toc": re.search(r"^## Version: (\S+)", (ADDON / "SimsarForeverExport.toc").read_text(), re.M).group(1),
    }
    if len(set(found.values())) != 1:
        sys.exit("Version numbers disagree: " + ", ".join(f"{k}={v}" for k, v in found.items()))
    return next(iter(found.values()))


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [f for f in out.decode().split("\0") if f]


def check_clean():
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout
    if status.strip():
        sys.exit("The working tree has uncommitted changes; commit them before building a release.\n" + status)


def add(zf, path, arcname):
    info = zipfile.ZipInfo.from_file(path, arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    with open(path, "rb") as f:
        zf.writestr(info, f.read())


def build_app_zip(version):
    name = f"simsar-forever-{version}"
    target = DIST / f"{name}.zip"
    with zipfile.ZipFile(target, "w") as zf:
        for f in tracked_files():
            add(zf, ROOT / f, f"{name}/{f}")
        for f in sorted(STATIC.rglob("*")):
            if f.is_file():
                add(zf, f, f"{name}/{f.relative_to(ROOT).as_posix()}")
    return target


def build_addon_zip(version):
    target = DIST / f"SimsarForeverExport-{version}.zip"
    with zipfile.ZipFile(target, "w") as zf:
        for f in sorted(ADDON.rglob("*")):
            if f.is_file():
                add(zf, f, f"SimsarForeverExport/{f.relative_to(ADDON).as_posix()}")
        add(zf, ROOT / "LICENSE", "SimsarForeverExport/LICENSE")
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="run the test suite before packaging")
    parser.add_argument("--allow-dirty", action="store_true", help="skip the clean working tree check")
    args = parser.parse_args()

    version = versions()
    if not args.allow_dirty:
        check_clean()
    if args.test:
        run([sys.executable, "-m", "pytest", "-q"])

    if not (ROOT / "frontend" / "node_modules").exists():
        run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend")
    run(["npm", "run", "build"], cwd=ROOT / "frontend")
    if not (STATIC / "index.html").exists():
        sys.exit("UI build produced no index.html")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    built = [build_app_zip(version), build_addon_zip(version)]
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in built]
    (DIST / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    for p in built:
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:,.0f} KB")


if __name__ == "__main__":
    main()
