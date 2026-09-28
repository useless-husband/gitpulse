"""File extension -> language name mapping (for the language breakdown)."""

import os

_EXT = {
    ".py": "Python", ".pyi": "Python", ".pyw": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".c": "C", ".h": "C/C++ Header", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".hpp": "C/C++ Header", ".hh": "C/C++ Header",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C",
    ".lua": "Lua", ".pl": "Perl", ".pm": "Perl", ".r": "R", ".dart": "Dart",
    ".hs": "Haskell", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".clj": "Clojure", ".jl": "Julia", ".zig": "Zig", ".nim": "Nim",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".fish": "Shell",
    ".ps1": "PowerShell", ".bat": "Batch", ".cmd": "Batch",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "SCSS",
    ".less": "Less", ".vue": "Vue", ".svelte": "Svelte",
    ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".svg": "SVG", ".ini": "INI", ".cfg": "INI",
    ".md": "Markdown", ".markdown": "Markdown", ".rst": "reStructuredText",
    ".txt": "Text", ".tex": "TeX", ".sql": "SQL", ".proto": "Protocol Buffers",
    ".gradle": "Gradle", ".cmake": "CMake", ".mk": "Makefile",
    ".ipynb": "Jupyter Notebook", ".csv": "CSV", ".lock": "Lockfile",
}

_NAMES = {
    "makefile": "Makefile", "dockerfile": "Dockerfile", "cmakelists.txt": "CMake",
    "license": "Text", "readme": "Text", "gemfile": "Ruby",
}

OTHER = "Other"


def language_of(path):
    """Guess a language from a file path. Unknown files map to ``Other``."""
    base = os.path.basename(path)
    low = base.lower()
    if low in _NAMES:
        return _NAMES[low]
    ext = os.path.splitext(low)[1]
    return _EXT.get(ext, OTHER)
