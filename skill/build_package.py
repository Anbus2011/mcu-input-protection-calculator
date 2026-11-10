#!/usr/bin/env python3
"""
Builds the skill package that is installed in Claude Desktop.

    python skill/build_package.py [folder]

Writes <name>.zip to dist/ in this repository (or to the folder given),
where <name> is the "name" in the front matter of skill/SKILL.md. The zip
holds one folder, <name>/, with SKILL.md and examples/ (the .div copies for
the skill's self-test) and nothing else: the MCP server is not part of the
package, it runs from this repository.

dist/ is in .gitignore: the package is built, not committed. skill/SKILL.md
is the master copy; build and install again after changing it.

Line ends are written as "\\n" whatever the checkout has, so the package is
the same from any machine and the examples are the text solve_div returns.

Standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from typing import Optional

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SKILL_DIR)
DIST_DIR = os.path.join(REPO, "dist")       # where the package is written
SKILL_MD = "SKILL.md"
EXAMPLES = "examples"
EXAMPLE_SUFFIX = ".div"
NAME_FORM = r"[a-z0-9]+(?:-[a-z0-9]+)*"     # a skill name: lower case, digits, hyphens


def skill_name(text: str) -> str:
    """The "name" in the front matter of SKILL.md's text. ValueError when
    there is no front matter, no name, or a name that is not lower-case
    words joined by hyphens (it is also the folder and the file name)."""
    front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if not front:
        raise ValueError(f"{SKILL_MD}: no front matter (--- lines) at the top")
    name = re.search(r"^name:[ \t]*(.*?)[ \t]*$", front.group(1), re.MULTILINE)
    if not name:
        raise ValueError(f"{SKILL_MD}: no name in the front matter")
    if not re.fullmatch(NAME_FORM, name.group(1)):
        raise ValueError(f"{SKILL_MD}: name {name.group(1)!r} must be lower-case "
                         "letters and digits, joined by hyphens")
    return name.group(1)


def package_files() -> list:
    """(path inside the package folder, file on disk) of every file of the
    package: SKILL.md and the .div files of examples/."""
    folder = os.path.join(SKILL_DIR, EXAMPLES)
    examples = sorted(n for n in os.listdir(folder) if n.endswith(EXAMPLE_SUFFIX))
    if not examples:
        raise ValueError(f"{folder}: no {EXAMPLE_SUFFIX} files")
    return ([(SKILL_MD, os.path.join(SKILL_DIR, SKILL_MD))]
            + [(f"{EXAMPLES}/{n}", os.path.join(folder, n)) for n in examples])


def build(out_dir: Optional[str] = None) -> str:
    """Write the package to out_dir (DIST_DIR when not given) and return
    its path. An existing package of the same name is replaced."""
    out_dir = DIST_DIR if out_dir is None else out_dir
    contents = []
    for inside, path in package_files():
        with open(path, "rb") as f:
            contents.append((inside, f.read().replace(b"\r\n", b"\n")))
    name = skill_name(contents[0][1].decode("utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    package = os.path.join(out_dir, name + ".zip")
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for inside, data in contents:
            archive.writestr(f"{name}/{inside}", data)
    return package


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_package.py",
        description="Builds the skill package for Claude Desktop: a zip of "
                    "SKILL.md and examples/.")
    parser.add_argument("folder", nargs="?", default=None,
                        help="folder to write the package to (default: dist/ "
                             "in the repository)")
    args = parser.parse_args(argv)
    try:
        package = build(args.folder)
    except (OSError, ValueError) as e:
        print(f"build_package.py: {e}", file=sys.stderr)
        return 1
    print(f"Wrote {package}")
    with zipfile.ZipFile(package) as archive:
        for inside in archive.namelist():
            print(f"  {inside}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
