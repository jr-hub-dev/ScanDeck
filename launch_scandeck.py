"""PyInstaller entry point — absolute import so the frozen exe has a package."""

from scandeck.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
