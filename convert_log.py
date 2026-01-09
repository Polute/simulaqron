import sys
import re
import os

def parse_line(line):
    """
    Parse a raw line of the dump into the standard log format.
    Expected formats:
      - swapped / active:
            ID  Estado  link  w_gen  w_out  t_gen  t_recv  t_diff  Medicion
      - swapper:
            ID  Estado  link   (rest empty)
    """

    parts = re.split(r"\s+", line.strip())

    # Ignore header if present
    if parts[0] == "ID":
        return None

    # SWAPPER lines
    if len(parts) >= 2 and parts[1] == "swapper":
        ID = parts[0]
        Estado = "swapper"
        # Rebuild link from all remaining parts and remove spaces
        raw_link = " ".join(parts[2:])
        link = raw_link.replace(" ", "")
        return [ID, Estado, link, '""', '""', '""', '""', '""', '""']

    # Otherwise: swapped or active
    # Ensure at least 9 fields
    while len(parts) < 9:
        parts.append('""')

    ID, Estado, link, w_gen, w_out, t_gen, t_recv, t_diff, Medicion = parts[:9]

    return [
        ID,
        Estado,
        link,
        w_gen if w_gen != "" else '""',
        w_out if w_out != "" else '""',
        t_gen if t_gen != "" else '""',
        t_recv if t_recv != "" else '""',
        t_diff if t_diff != "" else '""',
        Medicion if Medicion != "" else '""'
    ]


def convert_file(input_path, output_path):
    # Create output directory if needed
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(input_path, "r") as fin:
        lines = [l for l in fin.readlines() if l.strip()]

    rows = []

    for line in lines:
        row = parse_line(line)
        if row is None:
            continue
        rows.append(row)

    with open(output_path, "w") as fout:
        fout.write("ID\tEstado\tlink\tw_gen\tw_out\tt_gen\tt_recv\tt_diff\tMedicion\n")
        for r in rows:
            fout.write("\t".join(r) + "\n")

    print(f"Converted {input_path} → {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_log.py input.txt output.txt")
        sys.exit(1)

    convert_file(sys.argv[1], sys.argv[2])
