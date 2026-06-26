"""
quick_run.py

Seed the local *manual* store with a few sample streams for hands-on exploration.
Run via `make quick-run` (which points PENSIEVE_HOME at .local/manual), then inspect
with `make manual ARGS="ls"`.
"""

from __future__ import annotations

import os
from pathlib import Path

SAMPLES = [
    ("Recs", "Build and grow Recs"),
    ("Employment", "Navigate my career"),
    ("Writing", "The 'I used to think' essay series"),
]


def main() -> None:
    # Safety net: default to the local manual store if PENSIEVE_HOME isn't set,
    # so a stray run never touches the real ~/.pensieve.
    os.environ.setdefault("PENSIEVE_HOME", str(Path(".local/manual").resolve()))

    from pensieve.database.session import init_db
    from pensieve.services import streams

    init_db()
    for name, purpose in SAMPLES:
        try:
            node = streams.create_stream(name, purpose)
            print(f"created  {node.id}")
        except streams.StreamExists:
            print(f"exists   {streams.slugify(name)}")

    print("\nStreams:")
    for node in streams.list_streams():
        print(f"  {node.id:<14} {node.properties.get('purpose')}")


if __name__ == "__main__":
    main()
