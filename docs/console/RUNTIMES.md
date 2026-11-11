# Optional runtimes and public packaging

**No Windows binary is published in this source preview.** The local staged executable links NVIDIA's proprietary `nvsdk_ngx_s.lib` from SDK 310.7.0. Its distribution terms include restrictions in §4(e), while the application is GPL-3.0 and no applicable linking exception/permission was established. This is an unresolved distribution question, not a claim that NVIDIA has rejected this project. The local private build remains intact.

Omitting optional model DLLs is insufficient to resolve the linked-core issue. A bounded build with `VEYRA_ENABLE_EXPERIMENTAL_DLSSNR=OFF`, DLSS SR/FG off failed in `EngineController.cpp`: `NgxCoreHost.h` still requires `nvsdk_ngx.h`; the shared graph also depends on the NGX target. A usable no-NGX build is not an existing packaging toggle. We did not substitute stubs, bypass checks, or claim a successful base build.

Next distribution step: establish applicable permission for the combined binary, or separate and validate a genuinely independent base player. The source preview and local-use build instructions do not grant third-party runtime rights. Hardware eligibility, filenames and availability menus are not proof of successful feature evaluation.

## Tested optional identities

Paths below are relative to the extracted application. Install only components you are entitled to obtain/use, with their original accompanying files and terms. Close the app first, keep previous files for rollback, then restart; availability is cached. Do not copy DLLs into Windows/System32 or replace a driver. Do not mix model families or assume a newer file is compatible.

| Component | Tested version | Discovery path | Publication decision |
|---|---|---|---|
| SF NR, A/B | 310.9.16.0, community modified, unsigned | `runtime/experimental/nr-ampere/nvngx_dlssnr.dll` | Omitted: public redistribution permission not established |
| NVIDIA-original NR | 310.8.0.0 | `runtime/experimental/nr-original/nvngx_dlssnr.dll` | Omitted: exact component's redistribution provenance not established |
| DLSS SR / DLAA | 310.7.0.0 | `runtime/experimental/nvngx_dlss.dll` | Omitted: optional vendor distribution outside this release's allowlist |
| Standard DLSS FG | 310.9.1.0 | `runtime/experimental/nvngx_dlssg.dll` | Omitted; no Performance/Lite recommendation |
| NVIDIA VFG | 1.3.0.0 | `runtime/nvidia-vfg/` complete matching set | Omitted: separate Maxine/VFX runtime terms and models |
| RTX Video SR / HDR | Existing private set, not changed | `runtime/experimental/nvngx_vsr.dll`, `nvngx_truehdr.dll` | Omitted; not a new validation |
| AMD FSR / Intel XeSS | SDK adapters built against 2.3.0 / 3.0.2 | Existing vendor-specific discovery paths | No vendor runtime binaries shipped; outside verified console profile |
| NVOF / CUDA / NGX driver | Installed driver 32.0.16.1692 in prior tests | Installed NVIDIA driver | Never copied into release |

Exact NR SHA-256:

- SF, 276162560 bytes: `cdfa6c1ec784867182164c7836f324f087b5c9f374d0c9fe46f54999feabf3ed`.
- Original, 165840496 bytes: `e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e`.

The release dependency inventory records other inspected files' hashes and inclusion decisions. These identities describe supported private-test inputs, **not a license grant or a download mirror**. No public acquisition route is asserted for the exact SF-modified/original NR files. If you cannot lawfully obtain them, those looks remain unavailable. This release has no public executable.

For public SDKs, start with [NVIDIA DLSS](https://github.com/NVIDIA/DLSS), [Optical Flow](https://developer.nvidia.com/opticalflow/download), [Maxine VFX](https://developer.nvidia.com/maxine), [AMD FidelityFX](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK) and [Intel XeSS](https://github.com/intel/xess). Obtain the documented version through its vendor release channel and review that artifact's terms. A vendor page mentioning a feature does not establish this adapter/runtime pairing works. SDK upgrades are separate engineering changes.

The VFG directory requires its matching `NVVideoEffects.dll`, `nvVFXVideoFrameGeneration.dll`, `NVCVImage.dll`, `cudart64_12.dll` and provider dependencies, not one arbitrarily renamed DLL. Keep the vendor package's internal layout. The ordinary RTX 5090 path does not require an Ampere compatibility patch.

## Audit policy and included components

The [NVIDIA RTX SDK license](https://github.com/NVIDIA/DLSS/blob/main/LICENSE.txt) has conditional object-code distribution grants, restrictions and attribution requirements. It is not permission to redistribute arbitrary modified or separately acquired models. The locally tested app links the NGX SDK core from SDK 310.7.0; its license is retained locally. That linked core is the additional binary-publication blocker. This is not a claim that optional model DLLs are GPL or vendor-endorsed. Existing experimental adapters remain explicitly experimental; no security checks were disabled for packaging.

The withheld local staging allowlist includes Veyra source-built EXE/shaders/QML/assets, dynamically linked Qt 6.8.3 components, the unchanged patched LGPL FFmpeg n9.0.1 libraries with dav1d/zlib, Microsoft redistributable CRT files and license texts. It excludes NR/FG/SR model DLLs, CUDA/VFX distributions, AMD NR workers/weights, beauty models, VB-CABLE installer, developer executables/PDBs, logs, recordings and personal preferences. Deinterlacing is disabled; the unused avfilter DLL is not shipped.

Qt component sources and the **exact patched FFmpeg corresponding-source archive** were collected locally for binary distribution, which is now withheld. Qt remains dynamically replaceable. FFmpeg's source archive contains its patch, configuration, dav1d/zlib sources and notices; no plain upstream FFmpeg substitution. See [Qt obligations](https://www.qt.io/development/open-source-lgpl-obligations), [FFmpeg distribution guidance](https://ffmpeg.org/legal.html), the included licenses and [build instructions](BUILD.md).

## Missing components

In the locally tested AI-enabled build without model files, the NR menu shows the existing “package is missing runtime components” reason and refuses unavailable looks without altering the current chain. General backend creation/evaluation errors remain visible. Availability checks are not inference tests. Selecting an unsupported preset is not evidence of generated output; use Originals until the required implementation is installed and active. Do not silence errors to make a backend appear functional.
