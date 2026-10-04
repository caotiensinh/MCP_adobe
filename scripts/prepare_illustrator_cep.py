from __future__ import annotations

import argparse
import re
from pathlib import Path

START_ON = """<StartOn>\n                        <Event>applicationActivate</Event>\n                        <Event>com.adobe.csxs.events.ApplicationActivate</Event>\n                    </StartOn>"""
MODULE_ENTRY_RE = re.compile(
    r'<script type="module"\s+crossorigin\s+src="(?P<src>\./assets/[^\"]+\.js)"></script>'
)
DEFERRED_ENTRY_RE = re.compile(
    r'<script defer src="(?P<src>\./assets/[^\"]+\.js)"></script>'
)
DIAGNOSTIC_MARKERS = (
    "mcp_adobe_cep_inline_probe",
    "INLINE_START",
    "ROOT_LEN:",
    "WS_OPEN",
)


class CepPreparationError(RuntimeError):
    pass


def _patch_manifest(text: str) -> tuple[str, bool]:
    if "<StartOn>" in text:
        if "applicationActivate" not in text:
            raise CepPreparationError("existing StartOn is missing applicationActivate")
        return text, False

    needle = "<AutoVisible>true</AutoVisible>"
    if needle not in text:
        raise CepPreparationError("CEP manifest AutoVisible marker not found")
    replacement = f"{needle}\n                    {START_ON}"
    patched = text.replace(needle, replacement, 1)
    if "<StartOn>" not in patched or "applicationActivate" not in patched:
        raise CepPreparationError("StartOn patch verification failed")
    return patched, True


def _patch_index(text: str) -> tuple[str, bool]:
    for marker in DIAGNOSTIC_MARKERS:
        if marker in text:
            raise CepPreparationError(
                f"diagnostic-only marker must not ship in production CEP payload: {marker}"
            )

    module_matches = list(MODULE_ENTRY_RE.finditer(text))
    deferred_matches = list(DEFERRED_ENTRY_RE.finditer(text))

    if module_matches and deferred_matches:
        raise CepPreparationError("mixed module and deferred CEP entries are ambiguous")
    if len(module_matches) > 1 or len(deferred_matches) > 1:
        raise CepPreparationError("expected exactly one production CEP entry")

    if module_matches:
        src = module_matches[0].group("src")
        patched = MODULE_ENTRY_RE.sub(f'<script defer src="{src}"></script>', text, count=1)
        if 'type="module"' in patched:
            raise CepPreparationError("module script remained after CEP compatibility patch")
        if not DEFERRED_ENTRY_RE.search(patched):
            raise CepPreparationError("deferred classic CEP entry verification failed")
        return patched, True

    if deferred_matches:
        if 'type="module"' in text:
            raise CepPreparationError("unexpected module script remains beside deferred entry")
        return text, False

    raise CepPreparationError("expected Vite production module entry was not found")


def prepare(root: Path) -> dict[str, bool]:
    manifest = root / "CSXS" / "manifest.xml"
    index = root / "dist" / "index.html"
    for path in (manifest, index):
        if not path.is_file():
            raise CepPreparationError(f"required CEP file is missing: {path}")

    manifest_text = manifest.read_text(encoding="utf-8")
    index_text = index.read_text(encoding="utf-8")
    manifest_text, manifest_changed = _patch_manifest(manifest_text)
    index_text, index_changed = _patch_index(index_text)

    manifest.write_text(manifest_text, encoding="utf-8", newline="\n")
    index.write_text(index_text, encoding="utf-8", newline="\n")

    return {
        "manifest_changed": manifest_changed,
        "index_changed": index_changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the pinned Illustrator CEP panel for Illustrator 2023/CEP 11."
    )
    parser.add_argument("root", type=Path, help="Path to the built cep-extension directory")
    args = parser.parse_args()

    try:
        result = prepare(args.root.resolve())
    except CepPreparationError as exc:
        parser.error(str(exc))

    print(f"CEP_STARTON_READY=PASS changed={str(result['manifest_changed']).lower()}")
    print(f"CEP_DEFERRED_CLASSIC_ENTRY_READY=PASS changed={str(result['index_changed']).lower()}")
    print("CEP_PRODUCTION_PAYLOAD_DIAGNOSTICS=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
