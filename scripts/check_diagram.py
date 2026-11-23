#!/usr/bin/env python3
"""Audit the native Tiny Tapeout portion of this Wokwi diagram."""

import argparse
import hashlib
import json
import re
from pathlib import Path


# Each entry maps a Wokwi part and its pins to the Tiny Tapeout cells.v model.
TWO_INPUTS = {"A": "a", "B": "b"}
CELLS = {
    "wokwi-gate-and-2": ("and_cell", TWO_INPUTS, "OUT", "out"),
    "wokwi-gate-nand-2": ("nand_cell", TWO_INPUTS, "OUT", "out"),
    "wokwi-gate-or-2": ("or_cell", TWO_INPUTS, "OUT", "out"),
    "wokwi-gate-xor-2": ("xor_cell", TWO_INPUTS, "OUT", "out"),
    "wokwi-gate-not": ("not_cell", {"IN": "in"}, "OUT", "out"),
    "wokwi-mux-2": ("mux_cell", {"A": "a", "B": "b", "SEL": "sel"}, "OUT", "out"),
    "wokwi-flip-flop-d": ("dff_cell", {"CLK": "clk", "D": "d"}, "Q", "q"),
}
BENCH = {
    "board-tt-block-input", "board-tt-block-output", "wokwi-clock-generator",
    "wokwi-gnd", "wokwi-vcc", "wokwi-logic-analyzer", "wokwi-slide-switch", "wokwi-text",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(diagram, *, allow_fixture=False):
    parts = {part["id"]: part for part in diagram["parts"]}
    require(len(parts) == len(diagram["parts"]), "Duplicate Wokwi part ID")
    for part_id, direction in (("ttin", "input"), ("ttout", "output")):
        part = parts.get(part_id, {})
        require(part.get("type") == f"board-tt-block-{direction}"
                and part.get("attrs", {}).get("verilogRole") == direction,
                f"{part_id} is missing its Tiny Tapeout {direction} assignment")
        matches = [candidate for candidate in parts.values()
                   if candidate["type"] == f"board-tt-block-{direction}"]
        require(len(matches) == 1, f"Expected one Tiny Tapeout {direction} block")

    sources = {f"ttin:IN{i}": f"ui_in[{i}]" for i in range(8)}
    sources.update({"ttin:CLK": "clk", "ttin:RST_N": "rst_n"})
    sinks = {f"ttout:OUT{i}" for i in range(8)}
    devices = {}
    for part_id, part in sorted(parts.items()):
        kind = part["type"]
        if kind == "wokwi-gnd":
            sources[f"{part_id}:GND"] = "1'b0"
        if kind == "wokwi-vcc":
            sources[f"{part_id}:VCC"] = "1'b1"
        if part_id.startswith("rx_"):
            require(re.fullmatch(r"rx_[A-Za-z0-9_]+", part_id), f"Invalid receiver ID {part_id}")
            require(kind in CELLS, f"Unsupported receiver part {part_id}: {kind}")
            require(not part.get("attrs"), f"Unexpected behavior attributes on {part_id}")
            devices[part_id] = kind
            _, pins, output, _ = CELLS[kind]
            sinks.update(f"{part_id}:{pin}" for pin in pins)
            sources[f"{part_id}:{output}"] = f"n_{part_id}"
        elif not allow_fixture:
            require(kind in BENCH and not part_id.startswith("test_"),
                    f"Unexpected part in the tapeout diagram: {part_id} ({kind})")

    drivers = {}
    for a, b, *_ in diagram["connections"]:
        require(a.split(":")[0] in parts and b.split(":")[0] in parts,
                f"Wire refers to an absent part: {a}, {b}")
        if a in sinks or b in sinks:
            sink, source = (a, b) if a in sinks else (b, a)
            require(source in sources, f"Unsupported silicon driver: {source} → {sink}")
            require(sink not in drivers, f"More than one wire reaches {sink}")
            drivers[sink] = sources[source]
        elif a.split(":")[0] in devices or b.split(":")[0] in devices:
            raise ValueError(f"Unexpected wire leaving the receiver: {a}, {b}")
    require(set(drivers) == sinks, f"Unconnected silicon pins: {sorted(sinks - set(drivers))}")
    require(len(devices) == 458, f"Expected 458 receiver primitives, got {len(devices)}")
    require(sum(kind == "wokwi-flip-flop-d" for kind in devices.values()) == 74,
            "Expected 74 receiver flip-flops")
    for name, kind in devices.items():
        if kind == "wokwi-flip-flop-d":
            require(drivers[f"{name}:CLK"] == "clk", f"{name} is on an unexpected clock")
    return {"devices": devices, "drivers": drivers}


def project_verilog(graph, top):
    """Translate only the audited hardware using the official cells.v interface."""
    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", top), "Invalid top-module name")
    devices, drivers = graph["devices"], graph["drivers"]
    lines = [
        "// Local projection of the Wokwi diagram using Tiny Tapeout cell models.",
        "\u0060default_nettype none",
        f"module {top} (",
        "    input wire [7:0] ui_in,",
        "    output wire [7:0] uo_out,",
        "    input wire [7:0] uio_in,",
        "    output wire [7:0] uio_out,",
        "    output wire [7:0] uio_oe,",
        "    input wire ena, clk, rst_n",
        ");",
    ]
    lines.extend(f"    wire n_{name};" for name in devices)
    lines.extend(
        f"    assign uo_out[{index}] = {drivers[f'ttout:OUT{index}']};"
        for index in range(8)
    )
    lines += ["    assign uio_out = 8'b0;", "    assign uio_oe = 8'b0;"]
    for name, kind in devices.items():
        module, pins, _, output_port = CELLS[kind]
        connections = [f".{port}({drivers[f'{name}:{pin}']})" for pin, port in pins.items()]
        connections.append(f".{output_port}(n_{name})")
        if module == "dff_cell":
            connections.append(".notq()")
        lines.append(f"    {module} {name} ({', '.join(connections)});")
    lines += ["endmodule", "\u0060default_nettype wire"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagram", type=Path)
    parser.add_argument("--built-diagram", type=Path,
                        help="Compare against the exact diagram downloaded in the GDS job")
    parser.add_argument("--verilog", type=Path, help="Write an independent local projection")
    parser.add_argument("--top", default="tt_um_slipt_wokwi")
    args = parser.parse_args()
    graph = audit(json.loads(args.diagram.read_text(encoding="utf-8-sig")))
    if args.built_diagram:
        built = json.loads(args.built_diagram.read_text(encoding="utf-8-sig"))
        require(audit(built) == graph, "The GDS build used different Wokwi wiring")
        print("The diagram used by the GDS build matches this repository.")
    if args.verilog:
        args.verilog.write_text(project_verilog(graph, args.top), encoding="utf-8")
    digest = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()
    print(f"Audited 458 receiver primitives (74 flip-flops). Circuit SHA-256 {digest}")


if __name__ == "__main__":
    main()
