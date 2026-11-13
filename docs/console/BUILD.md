# Reproduce the Windows build

This is a Windows x64 C++20 / D3D12 / Qt Quick application. Use the release tag `v2.1.5-console.2` and its manifest's exact source commit. The public branch preserves upstream v2.1.5 history; machine-specific research scripts/profiles are not prerequisites.

**Source preview:** no Windows binary is publicly distributed. Local build success does not clear redistribution of the linked proprietary NGX core; see [RUNTIMES.md](RUNTIMES.md).

## Inputs

| Input | Version used | Legitimate acquisition/configuration |
|---|---|---|
| MSVC | VS 2022, toolset 14.44.35207 | Visual Studio Desktop development with C++; x64 Native Tools prompt |
| Windows SDK | 10.0.26100.0 | Visual Studio Installer Windows SDK workload |
| CMake / Ninja | 4.3.1 / 1.12.1 | Official CMake/Ninja or Visual Studio distribution |
| Qt | 6.8.3 MSVC2022 x64 | Qt online installer/archive; qtbase, qtdeclarative, qtsvg |
| FFmpeg | n9.0.1, Veyra slices256 + dav1d + zlib build | Corresponding-source release asset; build configuration/patches retained inside |
| DLSS SDK | 310.7.0 | NVIDIA/DLSS official tag/archive; headers and matching core .lib |
| Optical Flow SDK | 5.0.7 | NVIDIA developer download; account/license may be required |
| CUDA headers | 12.9 (`CUDA_VERSION 12090`) | Official NVIDIA CUDA Toolkit; point to its include directory |
| NVENC headers | nv-codec-headers 13.0 | FFmpeg/nv-codec-headers official source |
| FidelityFX | SDK 2.3.0 | GPUOpen official release; Kits/FidelityFX directory |
| XeSS | SDK 3.0.2 | Intel official release |

Do not download an arbitrary runtime bundle as a replacement for development headers/libraries. Optional runtime DLLs are separate from build inputs. NR/FG source is inherited; no claim of genuine console engine motion/depth is made.

Run `scripts/console/build.ps1` from an **x64 Native Tools Command Prompt**, passing dependency paths. Example in PowerShell (replace paths with your installation):

```powershell
./scripts/console/build.ps1 -BuildDir ./build/console `
  -QtRoot D:/deps/Qt/6.8.3/msvc2022_64 `
  -FfmpegRoot D:/deps/ffmpeg/installed `
  -DlssRoot D:/deps/DLSS_SDK_310.7.0 `
  -NvofRoot D:/deps/Optical_Flow_SDK_5.0.7 `
  -CudaInclude D:/deps/CUDA/include `
  -NvencRoot D:/deps/nv-codec-headers-13.0 `
  -FidelityFxRoot D:/deps/FidelityFX-SDK-2.3.0/Kits/FidelityFX `
  -XessRoot D:/deps/xess-3.0.2
```

Release uses `/O2 /Ob2 /DNDEBUG`, parallel 2, D3D12 debug layer off. NR/DLSS SR/FG/NVOF enabled at compile time; Remote Play, Moonlight, Xbox, deinterlacing and libass disabled in this binary. It does not include AMD SDK 1.1.4 optical flow. Debug symbols may be generated locally but are not published. No model/DLL upgrade is implicit.

The primary target is `veyra_qml_ui`. Focused checks: `veyra_preset_library_tests`, `veyra_effect_chain_tests`, `veyra_console_preset_probe`, `veyra_qml_quick_tests`, `veyra_capture_format_selection_tests`, `veyra_capture_color_tests`, `veyra_presentation_worker_tests`. Each test uses an isolated writable data directory and timeout ≤300 seconds. GPU tests require the optional runtimes under test; missing-component tests deliberately do not provide them.

For packaging, deploy Qt with its matching `windeployqt`, preserve the build's `qml/Veyra`, shaders and application assets, include the exact FFmpeg DLLs/notices and corresponding source. Do not copy an entire private runtime directory. The local staging inventory is not authorization to distribute its executable. `Open Veyra Console.cmd` launches beside the executable with diagnostic/fallback experiments off. The release is not dependent on Python, research paths or a source checkout.

Qt is dynamically linked; replacing its ABI-compatible DLLs or rebuilding against modified Qt is possible. For Qt sources use the [official 6.8.3 submodule archive](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/) (qtbase/qtdeclarative/qtsvg). FFmpeg patches and build scripts are under `scripts/ffmpeg`. The local matching archive identity is recorded in the build manifest. Any future binary release must supply corresponding sources. FFmpeg configuration/build records include upstream historical build paths for provenance; those paths are not runtime requirements. No promise of byte-for-byte reproducibility across different compiler installations; the manifest binds the locally tested binary hashes to its exact source revision and toolchain.
