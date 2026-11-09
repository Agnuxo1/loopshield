# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
"""Bounded official HL7 FHIR validation of synthetic bundles; no GPU or credentials."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OUTPUT = ROOT / "output-v3"
OUTPUT.mkdir(exist_ok=True)
JAR = ROOT / "validator_cli.jar"
EXPECTED = "9dfe9f305b0f9389eceade2a4a1c9a2740d7b0e614066fdf07a78b571c76d92f"
URL = "https://github.com/hapifhir/org.hl7.fhir.core/releases/download/7.0.5/validator_cli.jar"

if not JAR.exists():
    with urllib.request.urlopen(URL, timeout=45) as source, JAR.open("wb") as dest:
        while chunk := source.read(1024 * 1024):
            dest.write(chunk)
digest = hashlib.sha256(JAR.read_bytes()).hexdigest()
assert digest == EXPECTED, "Official validator digest differs from pinned historical 7.0.5; stop"
(OUTPUT / "validator_sha256.txt").write_text(digest + "\n")
java = shutil.which("java")
runtime = json.loads((ROOT / "runtime.json").read_text())
if java is None:
    archive = ROOT / runtime["name"]
    assert runtime["url"].startswith("https://github.com/adoptium/temurin21-binaries/releases/download/")
    if not archive.exists():
        with urllib.request.urlopen(runtime["url"], timeout=45) as source, archive.open("wb") as dest:
            while chunk := source.read(1024 * 1024):
                dest.write(chunk)
    assert archive.stat().st_size == runtime["size"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == runtime["sha256"]
    runtime_root = ROOT / "java-runtime"
    runtime_root.mkdir(exist_ok=True)
    with tarfile.open(archive) as package:
        package.extractall(runtime_root, filter="data")
    java = str(next(runtime_root.glob("*/bin/java")))
with (OUTPUT / "java-version.txt").open("w") as log:
    subprocess.run([java, "-version"], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=20)
(OUTPUT / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
summary = {"validator": "7.0.5", "fhir": "4.0.1", "terminology": "disabled (-tx n/a)",
           "jar_sha256": digest, "runtime": runtime["version"], "groups": {}}
for group in ("valid", "broken"):
    inputs = sorted((ROOT / "input" / group).glob("*.json"))
    command = [java, "-Xmx1024m", "-XX:ActiveProcessorCount=2", "-jar", str(JAR),
               *[str(path) for path in inputs], "-version", "4.0.1", "-tx", "n/a",
               "-output", str(OUTPUT / (group + ".json"))]
    with (OUTPUT / (group + ".log")).open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    summary["groups"][group] = {"exit_code": result.returncode,
                               "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    report = json.loads((OUTPUT / (group + ".json")).read_text())
    outcomes = [e["resource"] for e in report.get("entry", [])] if report.get("resourceType") == "Bundle" else [report]
    counts = [{severity: sum(i.get("severity") == severity for i in outcome.get("issue", []))
               for severity in ("fatal", "error", "warning")} for outcome in outcomes]
    summary["groups"][group]["outcomes"] = counts
(OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
receipts = ROOT / "receipts"
receipts.mkdir(exist_ok=True)
shutil.copytree(OUTPUT, receipts / "run3", dirs_exist_ok=True)
if (ROOT / "output").exists():
    shutil.copytree(ROOT / "output", receipts / "run2", dirs_exist_ok=True)
shutil.copytree(ROOT / "input", receipts / "inputs", dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("*.~*~"))
shutil.copy2(__file__, receipts / "run_validator.py")
print(json.dumps(summary), flush=True)
valid = summary["groups"]["valid"]["outcomes"]
broken = summary["groups"]["broken"]["outcomes"]
assert len(valid) == 6 and all(not (r["fatal"] or r["error"] or r["warning"]) for r in valid)
assert len(broken) == 3 and all(r["fatal"] or r["error"] for r in broken)
