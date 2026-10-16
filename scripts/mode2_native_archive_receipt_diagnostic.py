"""Read-only comparison of Panda baseline and disposable XD native ZIP archives."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
ORIGINAL = ROOT/"MCP_Mode1_Panda_XD_38136531800.xd"
PANDA_COPY = ROOT/"mode2-isolated"/"Panda_Mode2_Editable_Experiment.xd"
DISPOSABLE = ROOT/"mode2-disposable-native"/"Mode2_Undo_E2E_38584984023.xd"
RECEIPT = DISPOSABLE.with_name("mode2_fill_rect_guid_receipt.json")
PANDA_SHA = "3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1"
GUID = "9989e92f-7c9b-4721-9cdc-b5b5ea33cdf2"
NAME = "MODE2_DISPOSABLE_FILL_RECT_GUID_E2E"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def analyze(path):
    result = {}
    matches = []
    with zipfile.ZipFile(path) as archive:
        failed = archive.testzip()
        if failed is not None:
            raise RuntimeError("MODE2_CORRUPT_NATIVE_ARCHIVE_ENTRY_" + failed)
        for info in archive.infolist():
            if info.file_size > 32_000_000:
                raise RuntimeError("MODE2_NATIVE_ARCHIVE_ENTRY_TOO_LARGE")
            raw = archive.read(info)
            entry_sha = hashlib.sha256(raw).hexdigest()
            result[info.filename] = (info.file_size, entry_sha)
            guid_found = GUID.encode("utf-8") in raw
            name_found = NAME.encode("utf-8") in raw
            if guid_found or name_found:
                matches.append({"file":info.filename,"guid":guid_found,"name":name_found})
    return result, matches

def main():
    if any(not p.is_file() for p in (ORIGINAL, PANDA_COPY, DISPOSABLE, RECEIPT)):
        raise RuntimeError("MODE2_ARCHIVE_MISSING_PROTECTED_FILE_OR_RECEIPT")
    if digest(ORIGINAL) != PANDA_SHA or digest(PANDA_COPY) != PANDA_SHA:
        raise RuntimeError("MODE2_ARCHIVE_PRODUCTION_BASELINE_CHANGED")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("state") != "applied" or receipt.get("node_id") != GUID or receipt.get("name") != NAME:
        raise RuntimeError("MODE2_ARCHIVE_RECEIPT_NOT_EXPECTED")
    original_entries, original_matches = analyze(ORIGINAL)
    test_entries, matches = analyze(DISPOSABLE)
    changed = []
    for name in sorted(set(original_entries) | set(test_entries)):
        if original_entries.get(name) != test_entries.get(name):
            changed.append(name)
    print("MODE2_ARCHIVE_ORIGINAL_SHA256="+digest(ORIGINAL),flush=True)
    print("MODE2_ARCHIVE_DISPOSABLE_SHA256="+digest(DISPOSABLE),flush=True)
    print("MODE2_ARCHIVE_ENTRY_COUNTS original="+str(len(original_entries))+" disposable="+str(len(test_entries)),flush=True)
    print("MODE2_ARCHIVE_CHANGED_ENTRIES="+json.dumps(changed),flush=True)
    print("MODE2_ARCHIVE_GUID_OCCURRENCES="+json.dumps(matches,sort_keys=True),flush=True)
    if original_matches:
        raise RuntimeError("MODE2_ARCHIVE_ORIGINAL_CONTAINS_TEST_GUID_OR_NAME")
    print("MODE2_ARCHIVE_ORIGINAL_PROTECTION=PASS",flush=True)
    print("MODE2_NATIVE_ARCHIVE_COMPARE_READONLY=PASS",flush=True)

if __name__=="__main__":
    main()
