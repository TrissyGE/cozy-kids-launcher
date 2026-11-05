# RetroGameCorner device preflight

The Parent device check reads local capabilities and a reviewed data registry
in `src/retro_requirements.json`. It never starts an emulator, reads family
game files, installs a package or sends a hardware report to a service. Source
links open only when a parent chooses them. Each probe has a two-second limit;
missing, failed or oversized output stays unknown.

## Reviewed scope

The registry records its revision and review date, with HTTPS primary sources.
These are observable prerequisites and upstream guidance. They do not qualify
an emulator installation recipe, establish working drivers or measure gameplay.

| Candidate | Current observed checks and source |
| --- | --- |
| mGBA and Mednafen | Identify the installed package when mapped. Numeric performance requirements stay unknown. See [mGBA](https://mgba.io/) and [Mednafen](https://mednafen.github.io/documentation/). |
| PCSX ReARMed | Restrict the launcher's currently reviewed binary to x86-64. This is the specific core build's boundary, not a claim about every RetroArch or PCSX build. Show the qualified core version and checksum when present. See [the core guide](https://docs.libretro.com/library/pcsx_rearmed/). |
| PCSX2 | Linux x86-64 and SSE4.1, 8 GiB guidance, Vulkan 1.1 or OpenGL 3.3. Check the three OpenGL extensions named in the [requirements](https://pcsx2.net/docs/setup/requirements/). |
| Dolphin | 64-bit environment, 2 GiB guidance, OpenGL 4.4 or Vulkan. The Vulkan 1.0 baseline is inferred from the upstream renderer's explicit [1.0 fallback](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/VideoBackends/Vulkan/VulkanContext.cpp), not a verification of its required features or extensions. See the [FAQ](https://dolphin-emu.org/docs/faq/). |
| xemu | Check the documented OpenGL 4.0 baseline. CPU and memory limits remain unknown. See [system requirements](https://xemu.app/docs/about/). |
| Cemu | 64-bit environment, 4 GiB guidance, OpenGL 4.5 or Vulkan 1.2. See [hardware guidance](https://cemu.info/) and the [Linux project](https://github.com/cemu-project/Cemu). |
| RPCS3 | Keep numeric requirements unknown pending a current complete review. The quickstart site returned HTTP 403 during this review. Do not apply an assumed x86-only restriction; upstream also publishes [Linux ARM64 builds](https://github.com/RPCS3/rpcs3-binaries-linux-arm64). |

An absent probe or an unreviewed alternative renderer cannot establish a hard
GPU incompatibility. Software renderers are excluded from accelerated GPU
capability reporting. Memory below guidance and an observed graphics limit
produce `limited`; known incompatible build architecture or required CPU
instructions produce `incompatible`. Otherwise the result stays `untested`.
No result is called `recommended` without an emulator workload measurement.
OpenGL extension results and Vulkan alternatives are shown separately.

## Installation and result lifetime

The catalog's shared package-route policy determines whether installation is
available on the current distribution. This is separate from the hardware
result. Parent emulator installation refreshes the preflight before opening
the normal app-store review and consent flow. A confirmed incompatibility or
unavailable route prevents installation; unknown performance with a reviewed
route keeps the action available. Leaving Parent settings cancels a pending
preflight's ability to open the installation flow.

Reports carry a check time, registry revision, local device fingerprint and
per-system result key. The fingerprint uses CPU model/microcode/count, kernel,
instruction flags, usable RAM and stable graphics identity/capabilities. It
excludes clocks, free VRAM, display IDs and driver UUIDs and contains no
hostname, account name, family path,
ROM name or machine serial. Package versions are queried through the detected
native package tool and accepted only in a bounded version syntax. For PS1,
the result also includes the reviewed core version and checksum. The result
key changes with device/driver observations, requirements or package/core
versions. Preflight reports are freshly computed on each request and are not
persisted. An explicitly requested [PS1 short test](RETRO_BENCHMARK.md) stores
one private aggregate result and attaches it only to the matching preflight.

The UI explains its scope and supports rerunning after updates. It does not
attach these observations to a game's approval or replace per-game
compatibility. The generated PS1 primitive workload now measures core call
times with fixed settings, separately from desktop display pacing. Broader
representative workloads, complete driver-feature qualification and physical
gameplay acceptance remain open.
