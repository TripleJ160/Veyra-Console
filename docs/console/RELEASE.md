# Veyra Console 2.1.5-console.1 — source preview

Independent Windows console-capture fork of upstream Veyra v2.1.5, commit `dc6f6e1e5e51b31d027e4d369949332c130238de`. This is a **source/evidence prerelease, not a downloadable Windows application release**.

## Changes

- Four integrated viewing presets, separate from seven NR looks.
- NR correction shortcut, persisted selections and accurate Custom/protection status.
- Native title-bar/FancyZones workflow, full-height Fit and Settings access.
- Requested versus connected capture/color information; no engine-FPS claim.
- List processing-order display corrected to match the existing engine graph.
- Optional diagnostic queries/logging gated; rejected-real fallback stays off.
- Preset, bridge, cadence/scheduling fixtures and reusable analysis tools.

DLSS/VFG, NR models, residual blending, protection masks and AA algorithms are inherited. No new model, lower controller latency, sharper gameplay or resolved stalls is claimed. Performance/Lite remains off in viewing presets.

## Why no public executable

The prepared app statically links the proprietary NGX core, in addition to loading optional models. Applicable distribution permission for that combination with GPL was not established. Omitting model DLLs alone does not clear the executable. The no-NGX build experiment failed because playback still depends on NGX headers/graph targets. See [runtime audit](RUNTIMES.md). The working private application and user configuration remain untouched.

No NR/FG/SR model DLLs, CUDA/VFX package, personal settings, capture identifiers, research logs/recordings, research ZIP or credentials are uploaded. The source contains adapters and their existing notices, not proprietary model implementations. Upstream history and its previously public promotional media are retained; the large promo videos/GIF are excluded from source release archives. Research-specific personal reports are excluded from the publication delta.

## Validation scope

The optimized AI-enabled publication candidate built successfully with parallelism 2. Focused checks passed: 645 preset checks, 461 chain checks, 154 actual bridge checks; capture format/color, presentation worker, live/GPU timing contracts; 52 Python analysis/session tests. QtQuick: **176 passed, 0 failed, 1 existing skip**. Two earlier QtQuick invocations failed due to test staging (missing test DLL path, then missing QML test folder); the corrected test environment passed without a product change.

A bounded 14-phase recorded-playback check passed with optional runtimes installed only in an isolated validation copy: all seven NR looks, four AA methods, NR+DLAA, model switching and recovery to standard DLSS 2×. A separate missing-runtime run refused all six NR-on looks and applied Originals/Reference. These are local tests, **not evidence that the source download includes runtimes**.

Pixel sheets reuse prior identical-frame native-1440p evidence from unchanged processing code. No new live-capture, audio-sync, high-speed-camera or sustained-performance measurement was performed. Native caption is visible in actual UI screenshots. Full-height behavior uses existing source/prior evidence; a clean fullscreen screenshot was not obtained during publication. No upstream UI image was fabricated: the upstream comparison is source-backed.

The release's machine-readable build manifest identifies the exact source commit, local executable hash, toolchain and final archive check. It is published separately to avoid a self-referential source hash. SHA256SUMS covers the uploaded assets. Initial failed tests are retained locally rather than rewritten as successes.

## Build, install and rollback

Use [BUILD.md](BUILD.md) for local source builds and [RUNTIMES.md](RUNTIMES.md) for exact optional identities and discovery. Public source acquisition does not grant vendor runtime rights. Keep a working installation intact and deploy any local build into a separate writable folder. Copy no personal configuration into a distributed package. Rollback means closing the new app and opening the preserved old folder.

The inherited update checker still points at upstream Veyra and opens upstream release pages; it is not a Console updater. Do not use an upstream package to overwrite this fork. Automated star-history commits are disabled in the fork; the workflow is manual-only.

Next publication work is resolving the combined-binary distribution question or implementing a genuinely independent base player, then validating and publishing a Windows package. New rendering algorithms and more manual benchmarks are not prerequisites.
