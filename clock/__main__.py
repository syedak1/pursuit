"""One entry point for everything:

    python -m clock refresh      crawl new items, then rebuild (what the nightly job runs)
    python -m clock fetch ...    crawl only        (see clock/fetch.py)
    python -m clock build ...    rebuild only      (see clock/build.py)
    python -m clock serve ...    run the web app   (see clock/serve.py)
    python -m clock eval ...     accuracy check    (see clock/eval.py)
"""

import sys

from . import build, eval as evaluate, fetch, serve

COMMANDS = {"fetch": fetch.main, "build": build.main, "serve": serve.main, "eval": evaluate.main}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "refresh":
        try:
            code = fetch.main([a for a in rest if a != "--llm"])
        except Exception as e:  # network trouble shouldn't look like a crash; the committed data still works
            print(f"\nCouldn't download from Legistar: {e}\n"
                  "The data already in the repo still works: python3 -m clock serve")
            return 1
        return code or build.main(["--llm"] if "--llm" in rest else [])
    if cmd not in COMMANDS:
        print(f"Unknown command {cmd!r}.\n{__doc__}")
        return 2
    return COMMANDS[cmd](rest) or 0


if __name__ == "__main__":
    raise SystemExit(main())