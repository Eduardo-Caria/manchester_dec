# SLIPT Manchester Receiver

A digital receiver for an underwater node that receives optical commands through its photovoltaic cell while harvesting energy. The PCB supplies a comparator signal, an 80 kHz clock, and an optional boost switching marker. The receiver detects a Manchester preamble, decodes a 16-bit payload at 2.5 kb/s, and outputs each bit with a strobe, an erasure flag, and the number of usable sample pairs.

The same receiver can compare one center pair, vote over eight pairs, or discard noise-marked pairs before voting. The PCB front end and the boost marker supply the two digital inputs used by the sample-pair decision.

## Build from Wokwi

The initial `wokwi_id: 0` is a placeholder. The layout build starts after you commit the saved receiver's project ID.

1. Load the repository's `diagram.json` in the [Tiny Tapeout Wokwi template](https://wokwi.com/projects/354858054593504257). Save a copy and set `project.wokwi_id` in `info.yaml` to the number at the end of your new receiver project URL.
2. Push to GitHub and check **gds**, **precheck**, and **gl_test** in Actions. The workflow fetches the Verilog and schematic from the saved Wokwi project. The schematic check compares its hardware with the checked-in `diagram.json`, and the gate test runs on the powered netlist from the build.
3. Share the repository and the passed run for review. Use the project's assigned shuttle flow at submission.

This repository uses the standard Tiny Tapeout SKY130 1×1 footprint of 161.00 × 111.52 µm. [Tiny Tapeout definition](https://github.com/TinyTapeout/tt-support-tools/blob/main/tech/sky130A/tile_sizes.yaml)

The datasheet source has the pin map, reset sequence, and Manchester stimulus. [How to operate and test the receiver](docs/info.md)
