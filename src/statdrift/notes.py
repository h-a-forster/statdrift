"""Fetch release notes once, hash them, and find which functions they name."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

FETCH_TIMEOUT = 60.0  # seconds, so a stalled server fails instead of hanging the command
ANY = "any"  # anywhere except the author list
NARRATIVE = "narrative"  # outside the issue and pull-request lists
COMPATIBILITY = "compatibility"  # a backwards-incompatible or deprecation section
TIERS = (ANY, NARRATIVE, COMPATIBILITY)
_LIST = "list"  # section of issue and pull-request titles
_SKIP = "skip"  # author lists: surnames collide with function names

SCIPY_RAW = "https://raw.githubusercontent.com/scipy/scipy/{commit}/doc/source/release/"
STATSMODELS_RAW = (
    "https://raw.githubusercontent.com/statsmodels/statsmodels/{commit}/docs/source/release/"
)
STATSMODELS_RELEASE = (
    "https://api.github.com/repos/statsmodels/statsmodels/releases/tags/v{version}"
)

HEADING_RULE = re.compile(r"^[=*~^\-#]{3,}\s*$")
AUTHORS = re.compile(r"author|contributor|thank|credit", re.I)
LISTS = re.compile(r"issues? closed|pull requests?|merged", re.I)
BREAKING = re.compile(r"backwards?[- ]incompatible|breaking|deprecat|expired", re.I)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "statdrift"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        return response.read()


def scipy_versions(chain: list[str]) -> dict[str, list[str]]:
    """For each release after the first, its minor's patches up to that release."""
    out = {}
    for version in chain[1:]:
        major, minor, patch = version.split(".")
        out[version] = [f"{major}.{minor}.{p}" for p in range(int(patch) + 1)]
    return out


def download(config: dict, root: Path) -> None:
    """Store each note and its hash. Existing files are kept: notes are fetched once."""
    settings = config["notes"]
    sources: dict[str, str] = {}
    scipy_chain = sorted(
        {v for c in config["chains"] if c["lib"] == "scipy" for v in c["versions"]},
        key=lambda v: tuple(int(p) for p in v.split(".")),
    )
    base = SCIPY_RAW.format(commit=settings["scipy_commit"])
    for versions in scipy_versions(scipy_chain).values():
        for version in versions:
            sources[f"scipy/{version}.rst"] = f"{base}{version}-notes.rst"
    base = STATSMODELS_RAW.format(commit=settings["statsmodels_commit"])
    for version, name in settings["statsmodels_files"].items():
        sources[f"statsmodels/{version}.rst"] = base + name
    for version in settings["statsmodels_github_only"]:
        sources[f"statsmodels/{version}.md"] = STATSMODELS_RELEASE.format(version=version)

    manifest = {}
    for relative, url in sorted(sources.items()):
        path = root / "notes" / relative
        if not path.exists():
            raw = fetch(url)
            if "api.github.com" in url:
                raw = json.loads(raw)["body"].replace("\r\n", "\n").encode()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        manifest[relative] = {
            "url": url,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    text = json.dumps(manifest, indent=1, sort_keys=True) + "\n"
    (root / "notes" / "MANIFEST.json").write_text(text, encoding="utf-8", newline="\n")


def _is_top(lines: list[str], index: int) -> bool:
    """A heading overlined (SciPy) or underlined with = (statsmodels)."""
    under = lines[index + 1] if index + 1 < len(lines) else ""
    over = lines[index - 1] if index else ""
    return under.startswith("=") or bool(HEADING_RULE.match(over))


def sections(text: str) -> list[tuple[str, str]]:
    """Split notes into (tier of section, line). Works on RST and on GitHub markdown."""
    lines = text.splitlines()
    tier = NARRATIVE
    out = []
    for index, line in enumerate(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        rule = bool(HEADING_RULE.match(line))
        if (line.strip() and not rule and HEADING_RULE.match(following)) or (
            line.startswith("#") and not rule
        ):
            if AUTHORS.search(line):
                tier = _SKIP
            elif LISTS.search(line):
                tier = _LIST
            elif BREAKING.search(line):
                tier = COMPATIBILITY
            elif tier != NARRATIVE and _is_top(lines, index):
                tier = NARRATIVE
        out.append((tier, line))
    return out


def short_name(fn: str) -> str:
    """The name a release note would use: drop the module path and any method."""
    parts = fn.split(".")
    if parts[-1] in ("pmf", "logpmf"):
        parts = parts[:-1]
    if "mstats" in parts:
        return "mstats." + parts[-1]
    return parts[-1]


def pattern(name: str) -> re.Pattern:
    if name.startswith("mstats."):
        return re.compile(r"mstats(?:_basic)?\." + re.escape(name[7:]) + r"(?!\w)")
    return re.compile(r"(?<!mstats\.)(?<!\w)" + re.escape(name) + r"(?!\w)")


def tiers_naming(fn: str, texts: list[str]) -> dict[str, list[str]]:
    """For each tier, the note lines that name the function."""
    regex = pattern(short_name(fn))
    found: dict[str, list[str]] = {tier: [] for tier in TIERS}
    for text in texts:
        for tier, line in sections(text):
            if tier == _SKIP or not regex.search(line):
                continue
            found[ANY].append(line.strip())
            if tier != _LIST:
                found[NARRATIVE].append(line.strip())
            if tier == COMPATIBILITY:
                found[COMPATIBILITY].append(line.strip())
    return found


def notes_for(lib: str, version: str, root: Path) -> list[str]:
    """The note texts a reader moving to `version` from the previous release would read."""
    directory = root / "notes" / lib
    versions = scipy_versions(["", version])[version] if lib == "scipy" else [version]
    texts = []
    for name in versions:
        paths = [p for p in (directory / f"{name}.rst", directory / f"{name}.md") if p.exists()]
        if not paths:
            raise FileNotFoundError(f"no notes for {lib} {name}: run `statdrift notes`")
        texts.append(paths[0].read_text(encoding="utf-8"))
    return texts
