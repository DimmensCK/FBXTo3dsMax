#!/usr/bin/env python3
"""Read-only repository checks, using Python 3.9 and the standard library.

No plug-in modules are imported and no Max process is started. Results go to
stdout. Static checks do not prove installation or plug-in functionality.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Set

ENGINES = (
    "f2m_topology_transfer.py", "f2m_skin_replace.py", "f2m_smoothing.py",
    "f2m_fbx_metadata.py", "f2m_selfcheck.py",
    "f2m_test_fixtures.py", "f2m_i18n.py", "f2m_report_i18n.py",
)
ENGINES = tuple("contents/" + name for name in ENGINES)
EXPECTED_INSTALL_COUNT = 32
SCRIPT_SUFFIXES = {".py", ".ms", ".mcr", ".ps1"}
TEXT_SUFFIXES = SCRIPT_SUFFIXES | {
    ".md", ".xml", ".txt", ".files", ".version", ".svg", ".yml", ".yaml",
}
PUBLIC_TREES = {"contents", "tests", "tools", "docs", ".github"}
PERSONAL_PATH = re.compile(
    r"(?i)\b[a-z]:[\\/]+(?:ai[\\/]+codex|users[\\/]+user(?:[\\/]|$))"
)
SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def is_link(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def inventory(root: Path) -> List[Path]:
    result = []
    for entry in root.iterdir():
        if is_link(entry):
            continue
        if entry.is_file():
            result.append(entry)
        elif entry.name in PUBLIC_TREES:
            for directory, names, files in os.walk(str(entry), followlinks=False):
                current = Path(directory)
                names[:] = sorted(
                    name for name in names
                    if name != "__pycache__" and not is_link(current / name)
                )
                result.extend(current / name for name in files
                              if not is_link(current / name))
    return sorted(result, key=lambda path: path.relative_to(root).as_posix().lower())


def safe_parts(value: str):
    path = PureWindowsPath(value)
    parts = re.split(r"[\\/]", value)
    if not value or path.is_absolute() or path.drive or path.root:
        raise ValueError("absolute, drive-relative, or empty path")
    if any(not part or part in {".", ".."} or part.rstrip(" .") != part
           or re.search(r'[<>:"|?*\x00-\x1f]', part)
           or PureWindowsPath(part).is_reserved() for part in parts):
        raise ValueError("unsafe path component")
    return parts


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def literal_assignment(path: Path, name: str) -> str:
    tree = ast.parse(read(path), filename=path.name, feature_version=(3, 9))
    values = [
        node.value.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name
                for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    if len(values) != 1:
        raise ValueError("expected exactly one literal " + name)
    return values[0]


def dependency_closure(root: Path, files: List[Path], seeds: Set[str]) -> Dict:
    """Conservatively keep file-name references, comments, and local imports."""
    scripts = {path.relative_to(root).as_posix(): path for path in files
               if path.suffix.lower() in SCRIPT_SUFFIXES}
    contents = {name: read(path) for name, path in scripts.items()}
    retained = seeds.intersection(scripts)
    reasons = {name: "seed" for name in retained}
    pending = sorted(retained)
    while pending:
        source = pending.pop()
        raw = contents[source]
        imports = set()
        if source.endswith(".py"):
            try:
                parsed = ast.parse(raw, filename=source, feature_version=(3, 9))
            except SyntaxError:
                # A referenced legacy diagnostic can still be retained from raw
                # source. Its executability is outside this dependency inventory.
                parsed = ast.parse("")
            for node in ast.walk(parsed):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.rsplit(".", 1)[-1])
        for target, path in scripts.items():
            if target not in retained and (
                path.name.lower() in raw.lower() or path.stem in imports
            ):
                retained.add(target)
                reasons[target] = source
                pending.append(target)
    tests = {name for name in scripts if name.startswith("tests/")}
    private_gates = [
        name for name in sorted(retained) if name.startswith("tests/")
        and "F2M_PRIVATE_" in contents[name]
    ]
    return {
        "method": "conservative file-name references and local Python imports",
        "retained_scripts": sorted(retained),
        "retention_reasons": {name: reasons[name] for name in sorted(reasons)},
        "migration_candidates": sorted(tests - retained),
        "retained_private_asset_gates": private_gates,
        "limit": "Computed paths/dynamic imports need review; candidates are not moved.",
    }


def inspect(root: Path) -> Dict:
    root = root.resolve(strict=True)
    errors, notes = [], []
    private_roots = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name.casefold() in {"release", "test"} or child.name.startswith((
            "PROTECTED_RELEASE_EVIDENCE_", "RELEASE_EVIDENCE_", "_iso_",
        )):
            if is_link(child) or any(child.iterdir()):
                private_roots.append(child.name)
    if private_roots:
        errors.append("Private/build roots remain beside public source: " + ", ".join(sorted(private_roots)))
    files = inventory(root)
    named = {path.relative_to(root).as_posix(): path for path in files}
    versions = {"contents/VERSION.txt": read(root / "contents/VERSION.txt").strip()}
    version = versions["contents/VERSION.txt"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("VERSION.txt must contain a numeric three-part version")
    for name in ENGINES:
        versions[name] = literal_assignment(root / name, "TOOL_VERSION")
    versions["contents/FBXTo3dsMax.version"] = read(
        root / "contents/FBXTo3dsMax.version"
    ).strip()
    for name, pattern in (
        ("contents/FBXTo3dsMax_UI.ms", r'local\s+toolVersion\s*=\s*"([0-9.]+)"'),
        ("contents/FBXTo3dsMax_Bootstrap.ms", r'\bversion\s*=\s*"([0-9.]+)"'),
        ("Install_FBXTo3dsMax.ms", r'local\s+installerVersion\s*=\s*"([0-9.]+)"'),
    ):
        found = re.findall(pattern, read(root / name))
        if len(found) != 1:
            errors.append(name + ": expected one declared version")
        else:
            versions[name] = found[0]
    ui = read(root / "contents/FBXTo3dsMax_UI.ms")
    if re.findall(r"版本：([0-9.]+)", ui) != [version]:
        errors.append("UI displayed version differs from VERSION.txt")
    xml = ET.parse(str(root / "PackageContents.xml")).getroot()
    versions["PackageContents.xml"] = xml.get("AppVersion", "")
    host = xml.find("./Components/RuntimeRequirements")
    if host is None:
        errors.append("PackageContents.xml has no host requirements")
    toolbar_path = root / "contents/f2m_toolbar.py"
    toolbar = read(toolbar_path)
    if re.search(r"(?m)^TOOL_VERSION\s*=", toolbar):
        versions["contents/f2m_toolbar.py"] = literal_assignment(toolbar_path, "TOOL_VERSION")
    else:
        notes.append("Toolbar has no independent version constant; Bootstrap supplies package version.")
    if not re.search(r"(?m)^def install_and_schedule\(", toolbar):
        errors.append("Toolbar install entry is missing")
    if not (root / "contents/icons/FBXTo3dsMax.svg").is_file():
        errors.append("Toolbar icon is missing")
    for name, found in versions.items():
        if found != version:
            errors.append(name + ": version differs from VERSION.txt")

    manifest = read(root / "contents/FBXTo3dsMax.files")
    if re.findall(r"(?m)^#\s*FBXTo3dsMax v([0-9.]+)", manifest) != [version]:
        errors.append("Installation manifest version comment differs from VERSION.txt")
    sources, targets, records = set(), set(), []
    for number, raw in enumerate(manifest.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if line.count("|") != 1:
                raise ValueError("expected source|destination")
            source, target = [part.strip() for part in line.split("|", 1)]
            parts, target_parts = safe_parts(source), safe_parts(target)
            source_name, target_name = "/".join(parts), "/".join(target_parts)
            if source_name.casefold() in sources or target_name.casefold() in targets:
                raise ValueError("duplicate source/target (case-insensitive)")
            source_path = root.joinpath(*parts)
            source_path.resolve(strict=True).relative_to(root)
            if not source_path.is_file() or any(
                is_link(root.joinpath(*parts[:i])) for i in range(1, len(parts) + 1)
            ):
                raise ValueError("source is missing or uses a filesystem link")
            if parts[0].casefold() in {"release", "test"}:
                raise ValueError("installation requires private Release/Test tree")
            sources.add(source_name.casefold())
            targets.add(target_name.casefold())
            records.append({"source": source_name, "target": target_name,
                            "bytes": source_path.stat().st_size, "sha256": digest(source_path)})
        except (ValueError, OSError) as exc:
            errors.append("Manifest line {}: {}".format(number, exc))
    if len(records) != EXPECTED_INSTALL_COUNT:
        errors.append("Expected 32 valid installation entries; found " + str(len(records)))

    installer_source = read(root / "Install_FBXTo3dsMax.ms")
    required_blocks = re.findall(
        r"local\s+requiredManifestDestinations\s*=\s*#\((.*?)\)\s*"
        r"for\s+requiredDestination\s+in\s+requiredManifestDestinations",
        installer_source, flags=re.DOTALL,
    )
    required_targets = []
    if len(required_blocks) != 1:
        errors.append("Installer must declare one literal required-destination list")
    else:
        required_literal = r'"((?:\\.|[^"\\])*)"'
        array_remainder = re.sub(required_literal, "", required_blocks[0])
        if re.search(r"[^,\s]", array_remainder):
            errors.append("Installer required destinations must contain only literal strings")
        for raw_target in re.findall(required_literal, required_blocks[0]):
            try:
                target = "/".join(safe_parts(raw_target.replace("\\\\", "\\")))
                if target.casefold() in {item.casefold() for item in required_targets}:
                    raise ValueError("duplicate required target")
                required_targets.append(target)
                if target.casefold() not in targets:
                    errors.append("Installer requires a target absent from the manifest: " + target)
                if Path(target).suffix.lower() in {".fbx", ".max", ".blend", ".blend1"}:
                    errors.append("Installer still requires a bundled DCC asset: " + target)
            except ValueError as exc:
                errors.append("Unsafe installer required destination: " + str(exc))
        required_lower = {item.casefold() for item in required_targets}
        for mandatory in ("contents/f2m_test_fixtures.py", "contents/license",
                          "contents/f2m_i18n.py", "contents/f2m_report_i18n.py"):
            if mandatory not in required_lower:
                errors.append("Installer required destinations omit " + mandatory)

    # The PowerShell preflight is an independent installer gate. Its literal
    # list must remain closed over the same public manifest as the native gate.
    ps_source = read(root / "tools/Install_FBXTo3dsMax.ps1")
    ps_blocks = re.findall(
        r"foreach\s*\(\s*\$requiredDestination\s+in\s+@\((.*?)\)\s*\)",
        ps_source, flags=re.DOTALL,
    )
    ps_required_targets = []
    if len(ps_blocks) != 1:
        errors.append("PowerShell installer must declare one required-target list")
    else:
        ps_literal = r'"([^"\r\n]*)"'
        remainder = re.sub(ps_literal, "", ps_blocks[0])
        if re.search(r"[^,\s]", remainder):
            errors.append("PowerShell installer requirements must be literal strings")
        for raw_target in re.findall(ps_literal, ps_blocks[0]):
            try:
                target = "/".join(safe_parts(raw_target))
                if target.casefold() in {item.casefold() for item in ps_required_targets}:
                    raise ValueError("duplicate required target")
                ps_required_targets.append(target)
                if target.casefold() not in targets:
                    errors.append("PowerShell installer requires a target absent from the manifest: " + target)
                if Path(target).suffix.lower() in {".fbx", ".max", ".blend", ".blend1"}:
                    errors.append("PowerShell installer requires a bundled DCC asset: " + target)
            except ValueError as exc:
                errors.append("Unsafe PowerShell required destination: " + str(exc))
        for mandatory in ("contents/f2m_test_fixtures.py", "contents/license",
                          "contents/f2m_i18n.py", "contents/f2m_report_i18n.py"):
            if mandatory not in {item.casefold() for item in ps_required_targets}:
                errors.append("PowerShell installer requirements omit " + mandatory)

    runtime = set(ENGINES) | {
        "contents/FBXTo3dsMax_UI.ms", "Install_FBXTo3dsMax.ms",
        "tools/Install_FBXTo3dsMax.ps1", "Uninstall_FBXTo3dsMax.ms",
    }
    runtime.update(name for name in named if name.startswith("contents/")
                   and Path(name).suffix in SCRIPT_SUFFIXES)
    for name in sorted(runtime):
        raw = read(root / name)
        if name.endswith(".py"):
            tree = ast.parse(raw, filename=name, feature_version=(3, 9))
            path_literals = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and (
                    (isinstance(node.func, ast.Attribute) and node.func.attr in {"join", "joinpath"})
                    or (isinstance(node.func, ast.Name) and node.func.id == "Path")
                ):
                    path_literals.extend(arg.value for arg in node.args
                                         if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
                elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                    path_literals.extend(part.value for part in (node.left, node.right)
                                         if isinstance(part, ast.Constant) and isinstance(part.value, str))
            if any(value.casefold() in {"release", "test"} for value in path_literals):
                errors.append(name + ": literal Release/Test directory dependency")
        elif re.search(r"""(?i)["'][^"'\r\n]*(?:\bRelease|\bTest)[\\/]""", raw):
            errors.append(name + ": Release/Test path dependency")

    secrets, personal, fixture_paths = [], [], []
    for name, path in named.items():
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {
            "LICENSE", ".gitignore", ".gitattributes",
        }:
            raw = read(path)
            for kind, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(raw):
                    secrets.append({"file": name, "kind": kind,
                                    "line": raw.count("\n", 0, match.start()) + 1})
            for match in PERSONAL_PATH.finditer(raw):
                line = raw.count("\n", 0, match.start()) + 1
                personal.append({"file": name, "line": line})
                if name in runtime or (name.endswith(".md") and name not in {
                    "AGENTS.md", "docs/development/PROJECT_MEMORY.md",
                }):
                    errors.append("{}: personal machine path at line {}".format(name, line))
        elif name.startswith("tests/fixtures/"):
            data = path.read_bytes().lower().replace(b"\\", b"/")
            if re.search(rb"[a-z]:/(?:users/user/|ai/codex/)", data):
                fixture_paths.append(name)
    if secrets:
        errors.append("Potential credential/private key patterns detected (values withheld)")
    if fixture_paths:
        errors.append("Packaged fixtures contain personal machine paths")
    if personal:
        notes.append("Test/project guidance contains machine-path references; inspect reported locations.")
    if not (root / "LICENSE").is_file():
        errors.append("Public repository LICENSE is missing")
    bundled_assets = [name for name in named if Path(name).suffix.lower() in {".fbx", ".max", ".blend"}]
    if bundled_assets:
        errors.append("Public source repository contains forbidden bundled DCC assets")
    seeds = runtime | {record["source"] for record in records}
    seeds.update(name for name in named if name.startswith("tests/")
                 and Path(name).name.startswith("test_") and name.endswith(".py"))
    closure = dependency_closure(root, files, seeds)
    return {
        "ok": not errors, "scope": "public source static checks",
        "private_roots": private_roots,
        "errors": errors, "notes": notes, "versions": versions,
        "declared_host_range": dict(host.attrib) if host is not None else {},
        "installation": {"count": len(records), "expected_count": EXPECTED_INSTALL_COUNT,
                         "bytes": sum(item["bytes"] for item in records), "files": records,
                         "required_destinations": required_targets,
                         "powershell_required_destinations": ps_required_targets},
        "privacy": {"secret_findings": secrets, "personal_path_locations": personal,
                    "fixture_path_findings": fixture_paths,
                    "limit": "Pattern checks cannot establish complete privacy or asset ownership."},
        "test_dependency_closure": closure,
        "proof_limit": "Static checks only; pure regressions and isolated real-Max tests are separate.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root, default: script's parent project")
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    args = parser.parse_args()
    try:
        result = inspect(args.root)
    except (OSError, ValueError, SyntaxError, ET.ParseError) as exc:
        result = {"ok": False, "scope": "public source static checks",
                  "errors": [type(exc).__name__ + ": " + str(exc)], "notes": []}
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print("Repository static check: " + ("PASS" if result["ok"] else "FAIL"))
        if "installation" in result:
            package = result["installation"]
            print("Installation sources: {}/32; {} bytes".format(
                package["count"], package["bytes"]))
            closure = result["test_dependency_closure"]
            print("Retained scripts: {}; optional migration candidates: {}".format(
                len(closure["retained_scripts"]), len(closure["migration_candidates"])))
        for error in result["errors"]:
            print("ERROR: " + error)
        for note in result["notes"]:
            print("NOTE: " + note)
        print("Static checks do not prove plug-in functionality or installation.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
