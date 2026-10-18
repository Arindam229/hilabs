"""Resolve inputs inside the one dataset archive by path suffix, never by a hard-coded root folder."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def find_member(z: zipfile.ZipFile, suffix: str) -> str | None:
    """First member whose path ends with `suffix` (archive root folder name is irrelevant)."""
    return next((n for n in z.namelist() if n.endswith(suffix) and not n.endswith("/")), None)


def require_member(z: zipfile.ZipFile, suffix: str) -> str:
    name = find_member(z, suffix)
    if name is None:
        raise FileNotFoundError(f"no member ending with {suffix!r} in {z.filename}")
    return name


@contextmanager
def as_zip(source: zipfile.ZipFile | Path | None) -> Iterator[zipfile.ZipFile | None]:
    """Accept an already-open zip (nested member) or a path; None/missing path yields None."""
    if source is None or isinstance(source, zipfile.ZipFile):
        yield source
    elif Path(source).is_file():
        with zipfile.ZipFile(source) as z:
            yield z
    else:
        yield None


@contextmanager
def open_source_zip(archive: Path, member_suffix: str, standalone: Path | None = None
                    ) -> Iterator[tuple[zipfile.ZipFile | None, str]]:
    """Yield (zip, label) for a source shipped as a zip inside the dataset archive.

    A standalone file (env override) wins when it exists; otherwise the nested member is opened in
    place from the archive (stored members seek cheaply; nothing is extracted to disk).
    Yields (None, reason) when neither exists, so optional sources degrade instead of failing.
    """
    if standalone is not None and standalone.is_file():
        with zipfile.ZipFile(standalone) as z:
            yield z, str(standalone)
        return
    if not archive.is_file():
        yield None, f"archive missing: {archive}"
        return
    with zipfile.ZipFile(archive) as outer:
        name = find_member(outer, member_suffix)
        if name is None:
            yield None, f"not in archive: {member_suffix}"
            return
        with outer.open(name) as raw, zipfile.ZipFile(raw) as z:
            yield z, f"{archive.name}::{name}"
