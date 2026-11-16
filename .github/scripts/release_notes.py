"""Print the CHANGELOG.md section for one version, for use as release notes."""

import re
import sys

version = sys.argv[1]
with open("CHANGELOG.md", encoding="utf-8") as f:
    text = f.read()

pattern = rf"^#{{2,3}} {re.escape(version)} \(.*?\n(.*?)(?=^#{{2,3}} \d|\Z)"
match = re.search(pattern, text, re.S | re.M)
body = match.group(1).strip() if match else ""
print(body or "See CHANGELOG.md for details.")
