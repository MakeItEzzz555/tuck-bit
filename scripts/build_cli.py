#!/usr/bin/env python3
"""Build an optional stdlib-only, self-contained TuckBit source ZIP CLI."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

# Extract source to a private temporary directory so existing scripts retain
# their real filesystem assets and imports; never install into the host.
ENTRY = '''import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def main():
    with zipfile.ZipFile(sys.argv[0]) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or sum(entry.file_size for entry in entries) > 20000000:
            raise ValueError("Invalid or oversized CLI archive")
        manifest = json.loads(archive.read("CONTENTS.json"))
        if not isinstance(manifest, dict) or set(names) != set(manifest) | {"CONTENTS.json", "__main__.py"}:
            raise ValueError("CLI archive manifest mismatch")
        for name, expected in manifest.items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or "\\\\" in name or not isinstance(expected, str):
                raise ValueError("Unsafe CLI archive path")
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("CLI archive integrity mismatch")
        commands = sorted(Path(name).stem for name in manifest if name.startswith("scripts/") and name.endswith(".py") and b"if __name__" in archive.read(name))
        args = sys.argv[1:]
        if not args or args[0] in ("-h", "--help"):
            print("TuckBit portable CLI: python3 tuckbit-cli.zip COMMAND [arguments]")
            print("Commands: doctor, config, " + ", ".join(commands))
            print("Local source distribution; no automatic skill activation or permissions changes.")
            return 0
        command = args.pop(0)
        if command in ("doctor", "config"):
            args.insert(0, command)
            command = "tuckbit"
        if command not in commands:
            raise ValueError("Unknown CLI command: " + command)
        with tempfile.TemporaryDirectory(prefix="tuckbit-cli-") as folder:
            root = Path(folder).resolve()
            for name in manifest:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))
            return subprocess.run([sys.executable, str(root / "scripts" / (command + ".py")), *args]).returncode


try:
    raise SystemExit(main())
except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
    print("TuckBit CLI error: " + str(exc), file=sys.stderr)
    raise SystemExit(2)
'''


def build(output, root=ROOT):
    root, output = Path(root), Path(output)
    files = {}
    for name in ("README.md", "LICENSE", "distribution.json", "plugin.json", "gemini-extension.json"):
        files[name] = root / name
    for directory in ("scripts", "skills", "evals", "examples", "docs", "web", ".claude-plugin", ".codex-plugin", ".agents/plugins"):
        source_dir = root / directory
        if source_dir.is_symlink():
            raise ValueError("Refusing symlink source directory: " + str(source_dir))
        for file in source_dir.rglob("*"):
            if file.is_symlink():
                raise ValueError("Refusing symlink in CLI source: " + str(file))
            if file.is_file() and "__pycache__" not in file.parts and file.suffix in (".py", ".json", ".jsonl", ".md", ".html", ".css", ".js", ".svg"):
                files[file.relative_to(root).as_posix()] = file
    data = {}
    for name, file in sorted(files.items()):
        if file.is_symlink() or not file.is_file():
            raise ValueError("Missing or unsafe CLI source: " + name)
        data[name] = file.read_bytes()
    if sum(map(len, data.values())) > 19000000:
        raise ValueError("CLI source is too large for the portable archive")
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in {**data, "CONTENTS.json": json.dumps(manifest, sort_keys=True), "__main__.py": ENTRY}.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    # Exclusive creation refuses existing files and dangling symlinks.
    with output.open("xb") as handle:
        handle.write(stream.getvalue())
    return hashlib.sha256(stream.getvalue()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        digest = build(args.output)
        print(f"Built {args.output} SHA256 {digest}")
        return 0
    except (ValueError, OSError) as exc:
        print("TuckBit CLI build error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
