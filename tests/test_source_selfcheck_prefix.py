"""Exercise the real public launcher's byte-prefix gate without starting Max."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_selfcheck.ps1"
POWERSHELL = shutil.which("pwsh") or str(
    Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    / "PowerShell" / "7" / "pwsh.exe"
)


class SourceSelfcheckPrefixTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32" and Path(POWERSHELL).is_file(),
                         "The native public launcher requires PowerShell 7 on Windows.")
    def test_actual_prefix_gate_rejects_rewrite_with_same_tail_and_truncation(self):
        # Only these two pure function ASTs are evaluated; no launcher body,
        # process control, artifact write, or native log read is executed.
        script = r"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$tokens = $null; $errors = $null
$tree = [Management.Automation.Language.Parser]::ParseFile(
    $env:F2M_PREFIX_TEST_RUNNER, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Public launcher syntax is invalid.' }
foreach ($name in @('Get-ByteHash', 'Assert-FullLogPrefix')) {
    $definitions = @($tree.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq $name
    }, $true))
    if ($definitions.Count -ne 1) { throw "Expected exactly one pure function: $name" }
    . ([ScriptBlock]::Create($definitions[0].Extent.Text))
}
function IsRejected([byte[]]$Before, [byte[]]$After) {
    try { [void](Assert-FullLogPrefix $Before $After); return $false }
    catch { return $true }
}
$before = [byte[]]::new(1024)
for ($index = 0; $index -lt $before.Length; $index++) { $before[$index] = $index % 251 }
$after = [byte[]]::new(1030)
[Array]::Copy($before, 0, $after, 0, $before.Length)
$after[1029] = 42
$changed = [byte[]]$after.Clone()
$changed[100] = 252
$sameTail = (Get-ByteHash ([byte[]]$changed[768..1023])) -ceq
    (Get-ByteHash ([byte[]]$before[768..1023]))
$tailChanged = [byte[]]$after.Clone(); $tailChanged[1023] = 252
$empty = [byte[]]::new(0)
$oversized = [byte[]]::new(32MB + 1)
[ordered]@{
    same_tail_despite_middle_change = $sameTail
    unchanged = (Assert-FullLogPrefix $before $before)
    append_only = (Assert-FullLogPrefix $before $after)
    new_empty_log = (Assert-FullLogPrefix $empty $after)
    reject_same_tail_middle_rewrite = (IsRejected $before $changed)
    reject_truncated = (IsRejected $before ([byte[]]$before[0..511]))
    reject_tail_rewrite = (IsRejected $before $tailChanged)
    reject_oversized_before = (IsRejected $oversized $oversized)
    reject_oversized_after = (IsRejected $empty $oversized)
} | ConvertTo-Json -Compress
"""
        environment = dict(os.environ)
        environment["F2M_PREFIX_TEST_RUNNER"] = str(RUNNER)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        cases = json.loads(result.stdout)
        self.assertEqual(len(cases), 9)
        for name, accepted in cases.items():
            with self.subTest(case=name):
                self.assertIs(accepted, True)

    def test_complete_snapshots_and_scope_are_required_in_launcher(self):
        text = RUNNER.read_text(encoding="utf-8-sig")
        self.assertIn("Read-LogBytes $path 0 ([int]$length)", text)
        self.assertIn("Assert-FullLogPrefix $checkpoint.bytes $raw", text)
        for suffix in (".before.bin", ".raw.bin", ".delta.bin"):
            self.assertIn(suffix, text)
        for gate in ("$verifiedLogPaths.Contains($path)", "if (-not $fullPrefixVerified)",
                     "Saved complete Max.log snapshot differs", "Saved appended Max.log delta differs"):
            self.assertIn(gate, text)
        self.assertNotIn("tail_length", text)
        self.assertNotIn("$offset = 0", text)
        self.assertIn("no profile isolation", text)


if __name__ == "__main__":
    unittest.main()
