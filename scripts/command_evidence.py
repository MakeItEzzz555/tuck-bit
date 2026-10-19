"""Bounded static shell evidence; recognition never executes or authorizes a command."""
import ast
from pathlib import Path
import re
import shlex

REASONS = {"literal_read", "literal_search", "literal_validation", "literal_output", "literal_directory",
           "read_only_compound", "malformed_command", "command_limit", "unsupported_syntax",
           "unsupported_command", "unsupported_arguments", "interpreter_unverified", "script_unverified",
           "untrusted_executable", "path_outside_workspace", "path_traversal", "path_symlink",
           "prohibited_command", "prohibited_tool", "unknown_event", "unknown_outcome", "path_hardlink"}
PROHIBITED = {"curl", "wget", "nc", "ncat", "ssh", "scp", "sudo", "rm", "rmdir", "kill",
              "open", "osascript", "eval", "exec", "source", ".", "xargs", "env"}


def python_read(code):
    """The one supported interpreter expression is a literal pathlib read and print."""
    try:
        tree = ast.parse(code)
        if len(tree.body) != 2:
            return None
        imported, printed = tree.body
        if (not isinstance(imported, ast.ImportFrom) or imported.module != "pathlib" or imported.level
                or len(imported.names) != 1 or imported.names[0].name != "Path" or imported.names[0].asname
                or not isinstance(printed, ast.Expr) or not isinstance(printed.value, ast.Call)):
            return None
        call = printed.value
        if not isinstance(call.func, ast.Name) or call.func.id != "print" or call.keywords or len(call.args) != 1:
            return None
        read = call.args[0]
        if (not isinstance(read, ast.Call) or read.args or read.keywords or not isinstance(read.func, ast.Attribute)
                or read.func.attr not in {"read_text", "read_bytes"}):
            return None
        construct = read.func.value
        if (isinstance(construct, ast.Call) and isinstance(construct.func, ast.Name) and construct.func.id == "Path"
                and not construct.keywords and len(construct.args) == 1 and isinstance(construct.args[0], ast.Constant)
                and isinstance(construct.args[0].value, str)):
            return construct.args[0].value
    except (SyntaxError, ValueError, RecursionError):
        pass
    return None


def scoped_path(name, folder, root):
    path = Path(name)
    if ".." in path.parts:
        return "path_traversal", None
    path = path if path.is_absolute() else folder / path
    if path != root and root not in path.parents:
        return "path_outside_workspace", None
    if any(part.is_symlink() for part in (path, *path.parents) if part == root or root in part.parents):
        return "path_symlink", None
    if path.is_file() and path.stat().st_nlink>1:return 'path_hardlink',None
    return None, path


def literal_segments(text):
    """Split existing read-only compounds without treating quoted data as shell syntax."""
    segments, separators = [], []
    quote, start, index = None, 0, 0
    while index < len(text):
        char = text[index]
        if quote == "'":
            if char == "'":
                quote = None
        elif char == "\\":
            index += 1
        elif quote == '"':
            if char == '"':
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char in "|<>(){}*?[]~#":
            return None, None
        elif char in ";&":
            separator = "&&" if text[index:index + 2] == "&&" else char
            if separator == "&":
                return None, None
            words = shlex.split(text[start:index])
            if not words:
                return None, None
            segments.append(words)
            separators.append(separator)
            index += len(separator) - 1
            start = index + 1
        index += 1
    words = shlex.split(text[start:])
    if not words:
        return None, None
    segments.append(words)
    return segments, separators


def classify(text, folder, wrapped=False):
    """Return only enums/counters, with conservative unknowns for unsupported shell forms."""
    from benchmark_runner import trusted_executable
    def result(reason, unsafe=False, check=False):
        return {"classified": reason.startswith("literal_") or reason == "read_only_compound",
                "unsafe": unsafe, "check": check, "reason": reason}
    if not isinstance(text, str):
        return result("malformed_command")
    if len(text) > 32768 or len(text.encode("utf-8", errors="replace")) > 32768:
        return result("command_limit")
    if not text.strip() or "\x00" in text:
        return result("malformed_command")
    try:
        tokens = shlex.split(text)
    except ValueError:
        return result("malformed_command")
    if not tokens:
        return result("malformed_command")
    exe = trusted_executable(tokens[0])
    if exe in {"sh", "bash", "zsh"} and not wrapped and len(tokens) == 3 and tokens[1] in {"-c", "-lc"}:
        return classify(tokens[2], folder, True)
    # These forms require shell evaluation, even when an apparent command prefix is harmless.
    if any(char in text for char in ("$", "`", "\n", "\r")):
        return result("unsupported_syntax")
    if Path(tokens[0]).name in PROHIBITED or Path(tokens[0]).name == "git" and any(
            arg in {"push", "commit", "reset", "clean", "checkout", "restore", "gc", "rebase", "merge"} for arg in tokens[1:]):
        return result("prohibited_command", True)
    root = Path(folder).absolute()
    # Exact Python AST is checked before shell separators; its quoted source may contain semicolons.
    if exe == "python3" and len(tokens) == 3 and tokens[1] == "-c":
        name = python_read(tokens[2])
        if name is None:
            return result("interpreter_unverified")
        problem, _ = scoped_path(name, root, root)
        return result(problem or "literal_read", bool(problem))
    try:
        segments, separators = literal_segments(text)
    except ValueError:
        return result("malformed_command")
    if segments is None:
        return result("unsupported_syntax")
    if sum(map(len, segments)) + len(separators) > 1024:
        return result("command_limit")
    cwd, reasons = root, []
    for words in segments:
        command, args = words[0], words[1:]
        exe = trusted_executable(command)
        if Path(command).name in PROHIBITED or Path(command).name=='git' and any(a in {'push','commit','reset','clean','checkout','restore','gc','rebase','merge'} for a in args):
            return result("prohibited_command", True)
        if command == "cd" and len(args) == 1:
            if ';' in separators:return result('unsupported_syntax')
            problem, path = scoped_path(args[0], cwd, root)
            if problem:
                return result(problem, True)
            # A failed cd followed by ';' changes path interpretation, so require a current directory.
            if not path.is_dir():
                return result("unsupported_arguments")
            cwd = path; reasons.append("literal_directory"); continue
        if exe is None:
            return result("untrusted_executable" if "/" in command else "unsupported_command")
        names, reason = [], None
        if exe == 'echo':
            reason = "literal_output"
        elif exe=='printf' and args and (args[0] in {'%s','%s\\n'} or not any(c in args[0] for c in '%\\') and not args[0].startswith('-')):
            reason='literal_output'
        elif exe == "cat" and args and not any(a.startswith("-") for a in args):
            names, reason = args, "literal_read"
        elif exe == "sed" and len(args) == 3 and args[0] == "-n" and re.fullmatch(r"[1-9][0-9]*(?:,[1-9][0-9]*)?p", args[1]):
            names, reason = [args[2]], "literal_read"
        elif exe in {"head", "tail"}:
            if len(args) == 1 and not args[0].startswith("-"):
                names, reason = args, "literal_read"
            elif len(args) == 3 and args[0] == "-n" and re.fullmatch(r"[1-9][0-9]{0,4}", args[1]):
                names, reason = [args[2]], "literal_read"
        elif exe == "ls" and all(not a.startswith("-") or re.fullmatch(r"-[alhF]+", a) for a in args):
            names, reason = [a for a in args if not a.startswith("-")] or ["."], "literal_search"
        elif exe == "rg":
            # Options with operands, preprocessors and follow-symlinks are deliberately unsupported.
            flags = {"--files", "-n", "--line-number", "-l", "--files-with-matches", "-i", "--ignore-case", "-F", "--fixed-strings", "--hidden", "-S", "--smart-case"}
            if all(not a.startswith("-") or a in flags or a == "--" for a in args):
                values = [a for a in args if not a.startswith("-")]
                names = values if "--files" in args else values[1:]
                if "--files" in args or values:
                    names, reason = names or ["."], "literal_search"
        elif (exe == "pytest" or exe == "python3" and args[:2] in (["-m", "unittest"], ["-m", "pytest"])):
            # Validation intent is recognized; this is not proof tests ran or passed.
            if len(segments) != 1:
                return result("unsupported_arguments")
            return {**result("interpreter_unverified"), 'check':True}
        elif exe == "python3":
            return result("script_unverified" if args and not args[0].startswith("-") else "interpreter_unverified")
        if reason is None:
            return result("unsupported_arguments")
        for name in names:
            problem, _ = scoped_path(name, cwd, root)
            if problem:
                return result(problem, True)
        reasons.append(reason)
    return result("read_only_compound" if len(reasons) > 1 else reasons[0])
