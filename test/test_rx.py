"""Drive the actual Tiny Tapeout pins and compare against an independent model."""

from random import Random

import cocotb
from cocotb.triggers import Timer

PREAMBLE = (1,) * 8 + (0, 1)
PAYLOAD = (1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1)
UNMASKED, MASKED, CENTER = "unmasked", "masked", "center"
HALF_CLOCK_NS = 6250


class Receiver:
    def __init__(self, dut):
        self.dut = dut

    async def tick(self, comp=0, blank=0, mode=UNMASKED, sync=0, invert=0):
        value = (int(comp) ^ invert) | (int(blank) << 1) | (sync << 3) | (invert << 5)
        if mode == MASKED:
            value |= 0x04
        if mode == CENTER:
            value |= 0x10
        self.dut.clk.value = 0
        self.dut.ui_in.value = value
        await Timer(HALF_CLOCK_NS, unit="ns")
        self.dut.clk.value = 1
        await Timer(HALF_CLOCK_NS, unit="ns")
        return int(self.dut.uo_out.value)

    async def reset(self):
        self.dut.rst_n.value = 0
        for _ in range(5):
            output = await self.tick()
            assert output == 0, f"Reset did not clear outputs: {output:#04x}"
        assert int(self.dut.uio_oe.value) == 0
        self.dut.rst_n.value = 1


def manchester(bits):
    return [int((phase >= 16) == bool(bit)) for bit in bits for phase in range(32)]


def clean_payload(bits=PAYLOAD):
    return [(level, 0) for level in manchester(bits)]


def ideal_decision(samples, mode):
    offsets = [8] if mode == CENTER else range(4, 12)
    votes = []
    for i in offsets:
        first, first_flag = samples[i]
        second, second_flag = samples[i + 16]
        if mode == MASKED and (first_flag or second_flag):
            continue
        votes.append(second - first)
    total = sum(votes)
    erased = total == 0 or (mode != CENTER and len(votes) < 4)
    return (len(votes), erased, int(total > 0))


def check_decisions(events, expected):
    assert len(events) == len(expected), f"Expected {len(expected)} decisions, got {len(events)}"
    for i, ((tick, output), (pairs, erased, data)) in enumerate(zip(events, expected)):
        assert (output >> 4) == pairs, f"Tick {tick}, bit {i}: retained pairs at {output >> 4}, expected {pairs}"
        assert bool(output & 4) == erased, f"Tick {tick}, bit {i}: unexpected erasure state"
        assert bool(output & 8) == (i != 15), f"Tick {tick}, bit {i}: frame-active timing wrong"
        if not erased:
            assert (output & 1) == data, f"Tick {tick}, bit {i}: wrong data"


async def send(receiver, samples, mode, *, wired=False, invert=0, header_glitches=(), changes_at=None):
    for _ in range(12):
        assert not (await receiver.tick(mode=mode, invert=invert) & 0x0A)
    header = [] if wired else manchester(PREAMBLE)
    for tick in header_glitches:
        header[tick] ^= 1
    start = len(header)
    trace = [(level, 0) for level in header] + samples + [(0, 0)] * 18
    events = []
    for tick, (comp, blank) in enumerate(trace):
        selection = mode if changes_at is None or tick < start + changes_at else CENTER
        output = await receiver.tick(comp, blank, selection, int(wired and tick == 0), invert)
        if output & 2:
            events.append((tick, output))
    assert [tick for tick, _ in events] == [start + 33 + 32 * i for i in range(16)]
    expected = [
        ideal_decision(samples[i:i + 32], mode)
        for i in range(0, len(samples), 32)
    ]
    check_decisions(events, expected)
    return events


@cocotb.test()
async def nominal_optical_wired_inversion_and_modes(dut):
    receiver = Receiver(dut)
    await receiver.reset()
    for mode in (UNMASKED, CENTER, MASKED):
        await send(receiver, clean_payload(), mode)
        await send(receiver, clean_payload(), mode, wired=True)
    await send(receiver, clean_payload(), UNMASKED, invert=1)
    await send(receiver, clean_payload(), MASKED, header_glitches=(7, 27, 106, 231, 312))
    # A mode change during a frame takes effect on the next frame.
    await send(receiver, clean_payload(), UNMASKED, wired=True, changes_at=96)
    await send(receiver, clean_payload(), CENTER)


@cocotb.test()
async def selected_corruption_and_erasure_boundaries(dut):
    receiver = Receiver(dut)
    await receiver.reset()
    four_flipped_pairs = []
    second_half_only = []
    first_half_only = []
    center_error = []
    for tick, (level, _) in enumerate(clean_payload()):
        phase = tick % 32
        flip = int(4 <= phase % 16 <= 7)
        four_flipped_pairs.append((level ^ flip, flip))
        second_half_only.append((level, int(20 <= phase <= 24)))
        first_half_only.append((level, int(4 <= phase <= 8)))
        center_error.append((level ^ int(phase == 8), 0))
    bad = await send(receiver, four_flipped_pairs, UNMASKED, wired=True)
    recovered = await send(receiver, four_flipped_pairs, MASKED, wired=True)
    assert all(output & 4 for _, output in bad)
    assert all(not (output & 4) and output >> 4 == 4 for _, output in recovered)
    await send(receiver, second_half_only, MASKED, wired=True)
    await send(receiver, first_half_only, MASKED, wired=True)
    await send(receiver, [(level, 1) for level, _ in clean_payload()], MASKED, wired=True)
    await send(receiver, [(0, 0)] * 512, UNMASKED, wired=True)
    await send(receiver, center_error, CENTER, wired=True)
    await send(receiver, center_error, UNMASKED, wired=True)


@cocotb.test()
async def randomized_votes_against_reference(dut):
    receiver = Receiver(dut)
    await receiver.reset()
    rng = Random(81127)
    for mode in (UNMASKED, MASKED, CENTER):
        for index in range(8):
            bits = [rng.randrange(2) for _ in range(16)]
            samples = [
                (level ^ int(rng.random() < (index + 1) / 16), int(rng.random() < index / 12))
                for level, _ in clean_payload(bits)
            ]
            await send(receiver, samples, mode, wired=True)


@cocotb.test()
async def clean_link_with_clock_offset_and_unknown_initial_phase(dut):
    receiver = Receiver(dut)
    await receiver.reset()
    bits = (0,) * 12 + PREAMBLE + PAYLOAD + (0,) * 4
    # Idle levels before and after the packet. Only the packet is Manchester.
    samples = [0] * (12 * 32) + manchester(PREAMBLE + PAYLOAD) + [0] * (4 * 32)
    for ppm in (-5000, -2500, 0, 2500, 5000):
        for fractional_tick in (0, 250_000, 750_000):
            for mode in (UNMASKED, MASKED, CENTER):
                events = []
                for tick in range(len(bits) * 32):
                    tx_tick = (tick * (1_000_000 + ppm) + fractional_tick) // 1_000_000
                    level = samples[tx_tick] if tx_tick < len(samples) else 0
                    output = await receiver.tick(level, mode=mode)
                    if output & 2:
                        events.append((tick, output))
                pairs = 1 if mode == CENTER else 8
                check_decisions(events, [(pairs, False, bit) for bit in PAYLOAD])


@cocotb.test()
async def malformed_header_stuck_input_and_reset_recovery(dut):
    receiver = Receiver(dut)
    await receiver.reset()
    # Correct rising-edge cadence, wrong widths during the regular preamble.
    bad = [0] * 440
    rises = [16 + 32 * k for k in range(8)]
    for start in rises[:-1]:
        bad[start:start + 8] = [1] * 8
    last = rises[-1]
    bad[last:last + 32] = [1] * 32
    bad[last + 64:last + 80] = [1] * 16
    for level in bad + [0] * 256 + [1] * 256 + [0] * 128:
        assert not (await receiver.tick(level) & 0x0A), "False frame acquisition"
    await send(receiver, clean_payload(), UNMASKED)

    # Start a wired frame, abort with reset, and require a new start.
    await receiver.tick(sync=1)
    for _ in range(9):
        await receiver.tick()
    await receiver.reset()
    for _ in range(96):
        assert not (await receiver.tick() & 0x0A), "Strobe after aborted frame"
    await send(receiver, clean_payload(), MASKED, wired=True)
