"""Generate the launcher's own bounded PS1 primitive-rendering test program."""

import hashlib
import struct


WORKLOAD_VERSION = "ps1-primitives-v1"
ENTRY = 0x80010000
TABLE = 0x80011000
SIGNATURE_OFFSET = 0x1F000
SIGNATURE = 0x435A5931
TRIANGLES = 512


def generated_ps1_exe():
    """Return a self-contained PS-X EXE. Contains no third-party game or BIOS."""
    code, labels, branches = [], {}, []
    def emit(word):
        code.append(word)
    def immediate(op, target, source, value):
        emit((op << 26) | (source << 21) | (target << 16) | (value & 0xFFFF))
    def constant(register, value):
        immediate(15, register, 0, value >> 16)
        immediate(13, register, register, value)
    def store(source, address, offset=0):
        immediate(43, source, address, offset)
    def branch(op, left, right, label):
        branches.append((len(code), label))
        emit((op << 26) | (left << 21) | (right << 16))
        emit(0)
    def gpu(value, control=False):
        constant(8, value)
        store(8, 16, 4 if control else 0)

    constant(29, 0x801FFF00)  # private stack
    constant(16, 0x1F801810)  # GPU GP0/GP1
    constant(17, 0x1F801070)  # interrupt status, VBlank bit
    constant(18, 0x80000000 + SIGNATURE_OFFSET)
    constant(8, SIGNATURE)
    store(8, 18)
    store(0, 18, 4)
    gpu(0, True)             # GPU reset
    gpu(0x03000000, True)    # enable display
    gpu(0x08000001, True)    # 320x240 NTSC, 15-bit
    gpu(0x06C60260, True)    # horizontal display range
    gpu(0x07042018, True)    # vertical display range
    gpu(0xE3000000)          # drawing area origin
    gpu(0xE403BD3F)          # drawing area bottom right, 319x239
    gpu(0xE5000000)          # drawing offset
    gpu(0xE6000000)          # mask off
    constant(20, 0)
    labels["frame"] = len(code)
    labels["vblank"] = len(code)
    immediate(37, 8, 17, 0)  # lhu t0, I_STAT
    emit(0)                 # R3000 load delay
    immediate(12, 8, 8, 1)
    branch(4, 8, 0, "vblank")
    immediate(41, 0, 17, 0)  # clear interrupt status
    immediate(9, 20, 20, 1)
    store(20, 18, 4)
    gpu(0x02080808)          # clear background
    gpu(0)
    gpu((240 << 16) | 320)
    constant(19, TABLE)
    constant(9, TRIANGLES)
    constant(10, 0x20306080) # flat triangle, RGB
    # Shift the color every frame so validation can reject an idle/black core.
    emit((10 << 21) | (20 << 16) | (10 << 11) | 0x26)  # xor t2,t2,s4
    labels["triangle"] = len(code)
    store(10, 16)
    immediate(35, 11, 19, 0)
    immediate(35, 12, 19, 4)
    immediate(35, 13, 19, 8)
    store(11, 16)
    store(12, 16)
    store(13, 16)
    immediate(9, 19, 19, 12)
    immediate(9, 9, 9, -1)
    branch(5, 9, 0, "triangle")
    branch(4, 0, 0, "frame")
    for index, label in branches:
        code[index] |= (labels[label] - index - 1) & 0xFFFF
    program = bytearray(struct.pack("<" + "I" * len(code), *code))
    if len(program) > TABLE - ENTRY:
        raise ValueError("Generated program overlaps its vertex table")
    program.extend(bytes(TABLE - ENTRY - len(program)))
    for triangle in range(TRIANGLES):
        x, y = (triangle % 32) * 10, (triangle // 32) * 15
        program.extend(struct.pack("<III", (y << 16) | x, (y << 16) | (x + 16), ((y + 16) << 16) | x))
    program.extend(bytes(-len(program) % 2048))
    header = bytearray(2048)
    header[:8] = b"PS-X EXE"
    struct.pack_into("<IIII", header, 0x10, ENTRY, 0, ENTRY, len(program))
    struct.pack_into("<II", header, 0x30, 0x801FFF00, 0)
    return bytes(header + program)


def workload_sha256():
    return hashlib.sha256(generated_ps1_exe()).hexdigest()
