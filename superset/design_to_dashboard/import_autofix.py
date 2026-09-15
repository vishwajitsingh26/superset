# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Remove the unused imports the compiler named, without asking a model.

The frontend compiles with `jsx: react-jsx` and `noUnusedLocals`, so a
component that writes `import React from 'react'` out of habit fails the
type-check. Handing that to a model cost a whole regeneration per plugin --
70 to 280 seconds -- for an edit that needs no judgement: the compiler has
already said which binding is unused and on which line.

Its own module rather than part of `frontend`, which runs node tooling as
subprocesses: this is an edit to TypeScript source, and keeping it pure --
text and errors in, text out -- is what lets it be tested without a compiler.

Only import bindings are touched. An unused local is a sign the code meant to
use something and did not, which is a question for whoever wrote it. Anything
this cannot parse with confidence is left for the model.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import Iterable

from superset.design_to_dashboard import frontend

# `'X' is declared but its value is never read.` and, for a binding of an
# `import type` declaration, `'X' is declared but never used.`
UNUSED_BINDING_CODES = frozenset({"TS6133", "TS6196"})
# `All imports in import declaration are unused.` -- names no binding.
ALL_UNUSED_CODE = "TS6192"

_UNUSED_NAME = re.compile(r"^'([^']+)' is declared but")
_IDENT = r"[A-Za-z_$][\w$]*"
# A top-level import with bindings. The clause stops at a quote or a
# semicolon, so a side-effect import (`import './a.css'`) never matches and a
# string-named specifier is left alone. Import attributes (`with { type:
# 'json' }`, or the older `assert`) belong to the declaration: a removal that
# stopped at the module string would leave them behind as a stray statement.
_IMPORT = re.compile(
    r"^import\s+(?P<clause>[^;'\"`]*?)\s*\bfrom\s*(?:'[^'\n]*'|\"[^\"\n]*\")"
    r"(?:\s*\b(?:with|assert)\s*\{[^{}]*\})?[ \t]*;?",
    re.M,
)
# Attributes the pattern above could not take in -- nested braces, say. The
# declaration's end is then unknown, so it is left for the model.
_UNREAD_ATTRIBUTES = re.compile(r"\s*\b(?:with|assert)\s*\{")
_TYPE_ONLY = re.compile(r"type\s+(?=[{*A-Za-z_$])")
_DEFAULT = re.compile(rf"({_IDENT})\s*(?:,\s*|$)")
_NAMESPACE = re.compile(rf"\*\s*as\s+({_IDENT})")
_SPECIFIER = re.compile(rf"(?:type\s+)?({_IDENT})(?:\s+as\s+({_IDENT}))?")


@dataclass
class _Clause:
    """The bindings of one import declaration, as written."""

    type_only: bool
    default: str | None
    namespace: str | None
    # Specifiers with whitespace collapsed, or None when there are no braces.
    named: list[str] | None
    # The braces exactly as written, kept verbatim when nothing in them goes.
    braces: str

    @property
    def bound(self) -> set[str]:
        names = {name for name in (self.default, self.namespace) if name}
        return names | {_local(spec) for spec in self.named or []}


@dataclass
class _Declaration:
    start: int
    end: int
    clause_start: int
    clause_end: int
    first_line: int
    last_line: int
    clause: _Clause | None


def _local(specifier: str) -> str:
    """The name a specifier binds: the alias when there is one."""
    match = _SPECIFIER.fullmatch(specifier)
    return (match.group(2) or match.group(1)) if match else ""


def _parse_clause(text: str) -> _Clause | None:  # noqa: C901
    """Parse an import clause, or None when it is not plainly one.

    A comment inside the clause, a string-named specifier or anything else
    unexpected returns None, which leaves the declaration to the model.
    """
    if "/*" in text or "//" in text:
        return None
    rest = text.strip()
    type_only = False
    # `import type from 'x'` binds a default import named `type`.
    if match := _TYPE_ONLY.match(rest):
        type_only = True
        rest = rest[match.end() :]
    default = namespace = None
    named: list[str] | None = None
    braces = ""
    if not rest.startswith(("{", "*")):
        match = _DEFAULT.match(rest)
        if not match:
            return None
        default = match.group(1)
        rest = rest[match.end() :]
    if rest.startswith("*"):
        match = _NAMESPACE.fullmatch(rest)
        if not match:
            return None
        namespace = match.group(1)
        rest = ""
    elif rest.startswith("{"):
        if not rest.endswith("}") or "{" in rest[1:-1] or "}" in rest[1:-1]:
            return None
        braces = rest
        specifiers = [" ".join(part.split()) for part in rest[1:-1].split(",")]
        if specifiers and not specifiers[-1]:
            specifiers.pop()
        if not all(_SPECIFIER.fullmatch(spec) for spec in specifiers):
            return None
        named = specifiers
        rest = ""
    if rest.strip() or (default is None and namespace is None and named is None):
        return None
    return _Clause(type_only, default, namespace, named, braces)


def _declarations(contents: str) -> list[_Declaration]:
    found = []
    for match in _IMPORT.finditer(contents):
        found.append(
            _Declaration(
                start=match.start(),
                end=match.end(),
                clause_start=match.start("clause"),
                clause_end=match.end("clause"),
                first_line=contents.count("\n", 0, match.start()) + 1,
                last_line=contents.count("\n", 0, match.end()) + 1,
                clause=None
                if _UNREAD_ATTRIBUTES.match(contents, match.end())
                else _parse_clause(match.group("clause")),
            )
        )
    return found


def _render_braces(clause: _Clause, kept: list[str]) -> str:
    """The braces with only `kept` in them, in the style they were written."""
    if clause.named == kept:
        return clause.braces
    inner = clause.braces[1:-1]
    trailing_comma = inner.rstrip().endswith(",")
    if "\n" not in inner:
        pad = " " if inner.startswith(" ") else ""
        return "{" + pad + ", ".join(kept) + pad + "}"
    lines = [line for line in inner.split("\n") if line.strip()]
    indent = lines[0][: len(lines[0]) - len(lines[0].lstrip())] if lines else "  "
    closing = inner.rsplit("\n", 1)[-1]
    body = ",\n".join(f"{indent}{spec}" for spec in kept)
    return "{\n" + body + ("," if trailing_comma else "") + "\n" + closing + "}"


def _render_clause(clause: _Clause, removed: set[str]) -> str | None:
    """The clause without `removed`, or None when nothing is left to import."""
    parts = []
    if clause.default and clause.default not in removed:
        parts.append(clause.default)
    if clause.namespace and clause.namespace not in removed:
        parts.append(f"* as {clause.namespace}")
    kept = [spec for spec in clause.named or [] if _local(spec) not in removed]
    if kept:
        parts.append(_render_braces(clause, kept))
    if not parts:
        return None
    return ("type " if clause.type_only else "") + ", ".join(parts)


def _referenced(
    contents: str, declarations: list[_Declaration], names: set[str]
) -> bool:
    """Whether any of `names` appears outside the import declarations.

    Deliberately crude: a mention in a comment or a string counts. It guards
    the one error that names no binding, so it only ever errs towards leaving
    a declaration for the model -- and it is what keeps a second pass over
    shifted lines from removing an import that is in use.
    """
    body, cursor = [], 0
    for declaration in declarations:
        body.append(contents[cursor : declaration.start])
        cursor = declaration.end
    body.append(contents[cursor:])
    text = "".join(body)
    return any(
        re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", text) for name in names
    )


def _removals(
    contents: str,
    declarations: list[_Declaration],
    errors: Iterable[dict[str, str]],
) -> dict[int, set[str]]:
    """Which names to remove from which declaration, by declaration index."""
    removals: dict[int, set[str]] = {}
    for error in errors:
        located = frontend.error_location(error.get("detail") or "")
        if located is None:
            continue
        line, code, message = located
        index = next(
            (
                i
                for i, declaration in enumerate(declarations)
                if declaration.first_line <= line <= declaration.last_line
            ),
            None,
        )
        clause = declarations[index].clause if index is not None else None
        if index is None or clause is None:
            continue
        if code in UNUSED_BINDING_CODES:
            named = _UNUSED_NAME.match(message)
            if named and named.group(1) in clause.bound:
                removals.setdefault(index, set()).add(named.group(1))
        elif code == ALL_UNUSED_CODE and declarations[index].first_line == line:
            if clause.bound and not _referenced(contents, declarations, clause.bound):
                removals.setdefault(index, set()).update(clause.bound)
    return removals


def remove_unused_imports(
    contents: str, errors: Iterable[dict[str, str]]
) -> tuple[str, int]:
    """Remove the import bindings the compiler reported unused in one file.

    Returns the new source and how many bindings went. Every error is read
    against the source it was reported on, and edits are applied bottom-up,
    so one line's removal never moves the line another error names.

    Idempotent: a binding already removed is no longer bound on its line, and
    a whole-declaration error is acted on only while none of its names is
    used anywhere else.
    """
    declarations = _declarations(contents)
    removals = _removals(contents, declarations, errors)
    updated, removed = contents, 0
    for index in sorted(removals, reverse=True):
        declaration = declarations[index]
        if declaration.clause is None:
            continue
        rendered = _render_clause(declaration.clause, removals[index])
        if rendered is None:
            end = declaration.end
            if updated[end : end + 1] == "\n":
                end += 1
            updated = updated[: declaration.start] + updated[end:]
        else:
            updated = (
                updated[: declaration.clause_start]
                + rendered
                + updated[declaration.clause_end :]
            )
        removed += len(removals[index])
    return updated, removed


def fix_plugin(
    repo_root: str | pathlib.Path,
    directory: str,
    errors: list[dict[str, str]],
    protected: set[str] | frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Apply `remove_unused_imports` to one plugin's files on disk.

    Returns how many bindings were removed from each file changed. `protected`
    holds the skeleton's own files: they are re-rendered on every write, so an
    edit to one would not last, and a fault in one is the skeleton's to fix.
    """
    root = pathlib.Path(repo_root)
    fixed: dict[str, int] = {}
    for path, mine in frontend.errors_by_file(errors, directory).items():
        if path in protected or not path.endswith((".ts", ".tsx")):
            continue
        target = root / path
        try:
            contents = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated, removed = remove_unused_imports(contents, mine)
        if removed and updated != contents:
            target.write_text(updated, encoding="utf-8")
            fixed[path] = removed
    return fixed
