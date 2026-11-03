# The committed generated TL layer must be exactly what tools/codegen.py
# produces from schema/api.tl. Edit the schema or the generator, then run
# `make codegen` and commit the result.

from __future__ import annotations

import filecmp
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import support  # noqa: E402

GENERATED = support.PACKAGE_DIR / "raw" / "generated"


def _diff(left: pathlib.Path, right: pathlib.Path) -> list[str]:
    problems: list[str] = []
    cmp = filecmp.dircmp(left, right, ignore=["__pycache__"])
    problems += [f"only in committed: {left / n}" for n in cmp.left_only]
    problems += [f"only in fresh run: {right / n}" for n in cmp.right_only]
    problems += [f"differs: {left / n}" for n in cmp.diff_files]
    for sub in cmp.common_dirs:
        problems += _diff(left / sub, right / sub)
    return problems


def test_generated_layer_matches_schema(tmp_path):
    out = tmp_path / "generated"
    subprocess.run(
        [sys.executable, str(support.ROOT / "tools" / "codegen.py"),
         str(support.ROOT / "schema" / "api.tl"), str(out)],
        check=True, capture_output=True, text=True,
    )
    problems = _diff(GENERATED, out)
    assert not problems, "run `make codegen`:\n" + "\n".join(problems[:20])
