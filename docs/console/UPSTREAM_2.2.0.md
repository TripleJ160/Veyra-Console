# Console 2.2.0 integration — 2026-11-22

Merged upstream main **c6633121f27948bc297c35b033a88d854882dfc8** (2.2.0) into the Console fork, preserving ancestry. Original Console additions were based on v2.1.5. This update includes upstream capture/deduplication/deadline handling, improved presentation scaling, PS5 SDR handling, controller-release/feedback fixes, persistence and UI fixes. See upstream's [2.2.0 notes](../RELEASE_NOTES_2.2.0.md) for its full scope; upstream benchmark numbers are not new measurements on this machine.

## Console integration decisions

- Preserve independent viewing presets and seven NR looks, capture requested/connected status, working color interpretation, audio settings, native title bar, FancyZones and Ctrl+Alt+C centered geometry.
- Extend the shared List-order description for upstream's NR stabilizer and final exclusion-mask stages. They are not enabled automatically.
- Retain the audio-sync button in the expanded capture-audio panel. Fix its merge boundary and reserve space for the new rotation control alongside long preset/look names in the cinema bar.
- Keep Performance/Lite off in the supplied viewing profiles. Keep experimental rejected-real release off. Upstream's new prolonged-rejection hold is also opt-in here via VEYRA_CAPTURE_FG_REJECTION_HOLD=1, read once per session, rather than silently enabling another fallback.
- Use the maintained upstream ANR adapter instead of combining incompatible implementations. The old private B15 adapter/runtime remains available in the preserved previous local folder; no ANR inference is claimed for the new adapter without its matching runtime. Standard DLSS is the handheld profile's default.
- Native PS5 Remote Play is enabled for capture-picture plus controller forwarding. The older private Console build compiled it out. Veyra's incoming Moonlight/Xbox clients are not required for streaming Veyra out through Apollo.
- No vendor model DLL upgrade, driver change, global display change or controller-driver installation. Existing local runtime files were retained and rehashed.

## Validation on the RTX 5090 PC

Optimized Windows x64 builds of the merged private and public source variants passed, parallelism 2. Native dependencies: pinned Chiaki 0e16950165f06e5c3291537c2eeba6e852be7120 plus reviewed patches 0001-0004; SDL 3.4.14 static; Opus/OpenSSL/json-c/miniupnpc/libevent from recorded vcpkg sources with static CRT. Qt 6.8.3, patched FFmpeg 9.0.1, DLSS SDK 310.7 and NVOF SDK 5.0.7 are retained.

- Preset/chain, capture format/color, live-timing, trigger-release, controller boundary, virtual-pad input, follow-last-pressed and encrypted feedback-loopback checks passed. The control stress fixture completed 200 invalid-host cycles without connecting to a console.
- Actual Main.qml native geometry passed with both caption styles: manual resize, centered work-area fit, maximize/center and fullscreen restoration. The public source build passed its own native geometry, actual bridge/preset and chain checks.
- Full software Qt Quick: **239 passed, 0 failed, 1 existing skip**. Initial failures are retained in local evidence: an omitted test-source staging folder, a capture-dialog merge syntax error, a cinema control clipped by the added rotation action, and an obsolete test expecting the old private ANR runtime. Final runs use the corrected stage/source and explicitly test refusal when the new ANR runtime is absent.
- A bounded replay of existing recorded footage completed with the copied NR look and standard DLSS 2x at native 2560x1440 processing: **683 real and 681 generated Present submissions**. These are software submissions; neither physical display cadence nor controller-to-photon latency was measured. No new live capture or gameplay benchmark was requested.
- Final package component checker: **0 failures**. Required native dependencies are statically linked; no missing external SDL/Opus/OpenSSL DLL is hidden by a development PATH.

The build omits optional libdovi, external libass, deinterlace, AMD AMF SDK and incoming Moonlight/Xbox clients. These are explicit scope/dependency limits, not a full upstream binary-package equivalence claim. No system virtual camera is installed. Public GitHub remains source-only for the existing distribution limitation; the Windows build is a private local delivery.

## Handheld setup and limits

Read [Odin / Artemis setup](HANDHELD.md). The installed host was identified as Apollo 1.18.4-stable.3, service ApolloService. An existing ViGEm bus reports OK. PS5 pairing, the particular Odin's input stream, virtual-display activation, Internet/WAN reliability, generated-picture preservation through encoding, and external latency remain unmeasured. The software route is enabled and offline-tested; it still requires one-time PS5 registration and Apollo input permission.

Physical display remains 5120x1440 at its existing 120Hz. For the handheld, use a supported 16:9 Apollo virtual display and an appropriate client rate; fullscreen on an ultrawide physical desktop alone does not crop the stream. GTA 6's actual rendering modes remain unknown. Frame generation cannot double console simulation or make remote input respond as fast as a native doubled game rate.

## Reproduce and rollback

Configure an optimized Release build with the existing Qt/FFmpeg/DLSS/NVOF/FSR/XeSS roots, VEYRA_DISPLAY_VERSION=2.2.0-console.3 and VEYRA_ENABLE_REMOTEPLAY=ON. Provision Chiaki through scripts/remoteplay/build-native.ps1 and verify-chiaki-stage.py with the pinned clean source and reviewed staged patches. Supply SDL3 3.4.14, matching static-CRT native libraries, protoc and Python protobuf. See [build entry](BUILD.md). Local command arrays, complete logs, source identities and dependency receipts are under reports/codex-upstream-console-20261122 outside source Git.

Normal playback uses the shipped desktop launcher; the separate Odin launcher selects its isolated data directory. Old folders and original profiles remain unchanged. To roll back, close the new app and open the prior Centered folder. Do not copy a new schema back into the old folder. No system restoration or driver rollback is required.
