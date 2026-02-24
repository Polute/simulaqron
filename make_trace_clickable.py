import argparse
import re
from pathlib import Path


LINE_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s+\[([A-Z]+)\]\s+(.+?):(\d+)\s+#\s*(.+?)\s*$"
)


def remap_path(path: str, cwd: Path) -> str:
    # Some traces were captured in another machine path.
    path = path.replace("/home/luis/TFG/simulaqron", str(cwd))
    return path


def convert_trace(input_path: Path, output_path: Path, cwd: Path) -> tuple[int, int]:
    raw = input_path.read_bytes().replace(b"\x00", b"")
    lines = raw.decode("utf-8", errors="ignore").splitlines()

    converted = 0
    kept = 0
    out_lines: list[str] = []

    for line in lines:
        m = LINE_RE.match(line)
        if not m:
            continue
        ts, kind, py_path, line_no, func = m.groups()
        py_path = remap_path(py_path, cwd)
        uri = f"file://{py_path}#L{line_no}"
        out_lines.append(
            f"- [{func}]({uri})  |  {py_path}:{line_no}:1  |  [{kind}]  |  t={ts}"
        )
        converted += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    kept = len(out_lines)
    return converted, kept


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert traces to clickable links.")
    parser.add_argument("inputs", nargs="+", help="Input trace files")
    parser.add_argument(
        "--out-dir",
        default="clicker",
        help="Directory for converted files (default: clicker)",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    out_dir = Path(args.out_dir)

    for input_name in args.inputs:
        in_path = Path(input_name)
        out_path = out_dir / f"{in_path.stem}_clickable.md"
        converted, kept = convert_trace(in_path, out_path, cwd)
        print(f"{in_path} -> {out_path} ({kept} lines)")
        if converted == 0:
            print(f"  warning: no trace lines matched in {in_path}")


if __name__ == "__main__":
    main()
