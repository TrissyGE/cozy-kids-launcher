# Local PS1 short test

Parents can explicitly start, cancel, repeat and remove a local short test in
RetroGameCorner. It uses the already reviewed PCSX ReARMed Linux x86-64 core;
the launcher neither downloads a core implicitly nor asks for a family game
or BIOS. Normal game launches still require separately verified,
Parent-supplied firmware. An absent or incompatible reviewed core leaves the
test unavailable. Other candidate systems remain unmeasured.

## Workload and interpretation

`retro_workload.py` generates the launcher's own 12,288-byte PS-X EXE using
original MIPS instructions and vertex data. Version `ps1-primitives-v1` has
SHA-256 `129ed607f7d4680820e72d7f529f4b54fc4257fb18aa717c3bb59a33ddac0e8f`.
Each VBlank updates a private RAM signature/counter, clears a 320×240 image
and draws 512 flat, untextured triangles. Color changes let the frontend
distinguish an executing program from a static or empty video callback.

The separate ctypes frontend uses the [libretro ABI](https://docs.libretro.com/development/cores/developing-cores/),
not the installed RetroArch UI. The [core documentation](https://docs.libretro.com/library/pcsx_rearmed/)
describes PS-X EXE support and the HLE BIOS option. The worker checks options
actually queried by this pinned core: HLE BIOS, NTSC, dynamic recompiler
enabled and frameskip disabled. It accepts only 320×240 software video, warms
up for 60 frames, then times 240 unpaced `retro_run` calls. Validation requires
all 240 video frames, 240 counter increments and at least 24 distinct images.

The result records total throughput, median, nearest-rank 95th percentile
and maximum call time, target timing, core identity and settings. Python
callbacks and full-frame validation hashes are included in the call times.
Audio is discarded. This measures computation for this workload; it does not
measure visible display pacing, input latency, audio continuity, RetroArch
frontend overhead or a particular game's compatibility.

`within-budget` means this workload achieved at least 120% of its reported
NTSC target throughput and its 95th percentile stayed within one target frame
interval. Otherwise the result is `limited`. These are provisional workload
thresholds, not a console-wide hardware recommendation. No PS2, Wii U or PS3
recommendation follows from the PS1 result. Real gameplay, sound and controller
acceptance remain on the physical laptop list in [DESKTOP_TESTING.md](DESKTOP_TESTING.md).

## Process and HTTP boundaries

The Parent/origin-protected start API accepts exactly `{system: "ps1"}`.
It exposes no paths, arbitrary core, workload code, frame count or core options.
It refreshes the preflight and refuses an active owned app, active package
check/install or another benchmark. Start returns a job ID; cancel and removal
require that exact ID. A lost acknowledgement is recovered by reading status,
never by replaying the start request.

The manager copies checksum-verified core bytes into a private temporary
directory. The worker verifies them again before loading native code. Its
working directory, HOME and XDG directories point there; it is never given
the family's game or firmware directories. This is process isolation and
bounded resource use, not a security sandbox for arbitrary native libraries.
Only the pinned core is accepted.

The worker has a 25-second wall deadline, 15/16-second CPU soft/hard limits,
768 MiB address-space limit, 8 MiB file-size limit and disabled core dumps.
It owns a separate process group. Cancellation terminates that group; timeout
and shutdown have a kill fallback. Linux's parent-death signal terminates the
worker if its creating server thread dies, including an abrupt server exit.
Normal completion/cancellation removes temporary files. An abrupt OS or server
kill may leave generated files and a core copy in system temporary storage;
those files contain no family game or BIOS data.

Closing Parent settings requests cancellation, including an accepted reply
that arrives late. This UI request is best effort; server limits still apply
if the browser disappears. Starting an owned activity also requests cancellation.
A restarted server reports an unfinished job as interrupted and never replays it.

## Result lifetime and privacy

Only the latest job is retained in a bounded, atomically replaced mode-0600
file, `~/.local/state/cozy-kids-launcher/retro-benchmark.json`. It contains a
timestamp, random job ID, hashed scope and whitelisted aggregate result.
Per-frame samples, family names, paths, ROM names and hardware serials are not
stored. Removing the result clears saved metrics and the device panel's
attached measurement, leaving approvals, firmware and saves alone. Nothing
is uploaded.

A result attaches only when its scope still matches the observed CPU
model/microcode/count, kernel, instruction flags, usable RAM, graphics
identity/capabilities, registry revision, package/core versions and installation
route. Changing free VRAM, display IDs and driver UUIDs does not invalidate it.
Workload hash and fixed settings are revalidated when loading or attaching a
saved result. The UI marks a changed scope stale; parents can rerun after
updates. Power mode, thermal throttling and competing load can still change
performance, so repeat under comparable conditions.

## Repeating the native probe

Install the candidate Debian package in the disposable VM, supply the reviewed
local core ZIP and run as its ordinary user in the active session environment:

```sh
python3 scripts/linux/retro_benchmark_smoke.py \
  --desktop kde --session wayland \
  --core /path/to/reviewed-pcsx-rearmed.zip \
  --artifacts .test-artifacts/retro-benchmark/kde-wayland
```

Repeat for GNOME Wayland and XFCE X11. `--runtime` can point to an extracted
package for a headless WSL smoke. The probe creates its own private home and
checks real HTTP core import, validated execution, scope attachment, private
storage, restart, result removal and real-worker cancellation. It does not
discover or copy any family games or BIOS. Reports include runtime file hashes
so an uncommitted candidate remains identifiable. Browser tests use a separate
job fixture for error cases and all five languages at 800×600; fixture numbers
are never counted as native measurements.
