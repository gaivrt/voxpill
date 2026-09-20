"""Build a native portable release; run on the target OS (no cross-compilation)."""
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    from PIL import Image
    if sys.platform == "darwin":
        with Image.open(ROOT / "assets/voxpill.ico") as icon:
            icon.resize((1024, 1024)).save(ROOT / "assets/voxpill.icns")
    staging = ROOT / "build/release-dist"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(staging), "voicekey.spec"], cwd=ROOT, check=True)
    binary = staging / ("VoxPill.app/Contents/MacOS/VoxPill" if sys.platform == "darwin" else "VoxPill/VoxPill")
    subprocess.run([str(binary), "--smoke-acoustic-gate"], check=True, timeout=60)
    subprocess.run([str(binary), "--smoke-hotkey-settings"], check=True, timeout=60)
    subprocess.run([str(binary), "--smoke-models"], check=True, timeout=120)
    subprocess.run([str(binary), "--smoke-desktop"], check=True, timeout=60)
    for theme in ("dark", "light"):
        subprocess.run([str(binary), "--smoke-overlay", str(ROOT / "build/overlay-smoke" / theme), theme], check=True, timeout=30)
    subprocess.run([str(binary), "--smoke-overlay-client"], check=True, timeout=30)
    output = ROOT / "dist/release"
    output.mkdir(parents=True, exist_ok=True)
    stem = f"VoxPill-{version}-{platform.system().lower()}-{platform.machine().lower()}"
    if sys.platform == "darwin":
        archive = output / (stem + ".zip")
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(staging / "VoxPill.app"), str(archive)], check=True)
    else:
        shutil.copyfile(ROOT / "README.md", staging / "VoxPill/README.md")
        archive = output / (stem + ".tar.gz")
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(staging / "VoxPill", arcname="VoxPill")
    digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
    (output / (stem + ".sha256")).write_text(f"{digest}  {archive.name}\n")


if __name__ == "__main__":
    main()
