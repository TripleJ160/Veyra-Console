param(
    [Parameter(Mandatory)][string]$BuildDir,
    [Parameter(Mandatory)][string]$QtRoot,
    [Parameter(Mandatory)][string]$FfmpegRoot,
    [Parameter(Mandatory)][string]$DlssRoot,
    [Parameter(Mandatory)][string]$NvofRoot,
    [Parameter(Mandatory)][string]$CudaInclude,
    [Parameter(Mandatory)][string]$NvencRoot,
    [Parameter(Mandatory)][string]$FidelityFxRoot,
    [Parameter(Mandatory)][string]$XessRoot
)
$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path "$PSScriptRoot/../..").Path
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw 'Use an x64 Native Tools environment.' }
cmake -S $sourceRoot -B $BuildDir -G Ninja `
    -DCMAKE_BUILD_TYPE=Release -DVEYRA_DISPLAY_VERSION=2.1.5-console.1 `
    '-DCMAKE_CXX_FLAGS_RELEASE=/O2 /Ob2 /DNDEBUG /Zi' `
    '-DCMAKE_EXE_LINKER_FLAGS_RELEASE=/DEBUG:FULL /OPT:REF /OPT:ICF' `
    -DVEYRA_BUILD_QML_UI=ON -DVEYRA_ENABLE_D3D12_DEBUG=OFF `
    -DVEYRA_ENABLE_EXPERIMENTAL_DLSSNR=ON -DVEYRA_ENABLE_DLSS_SR=ON `
    -DVEYRA_ENABLE_DLSS_FG=ON -DVEYRA_ENABLE_NVOF=ON `
    -DVEYRA_ENABLE_REMOTEPLAY=OFF -DVEYRA_ENABLE_MOONLIGHT=OFF `
    -DVEYRA_ENABLE_XBOX=OFF -DVEYRA_ENABLE_DEINTERLACE=OFF `
    "-DCMAKE_PREFIX_PATH=$QtRoot" "-DVEYRA_FFMPEG_ROOT=$FfmpegRoot" `
    "-DVEYRA_DLSS_SDK_ROOT=$DlssRoot" "-DVEYRA_NVOF_SDK_ROOT=$NvofRoot" `
    "-DVEYRA_CUDA_DRIVER_INCLUDE_DIR=$CudaInclude" "-DVEYRA_NVENC_HEADERS_ROOT=$NvencRoot" `
    "-DVEYRA_FIDELITYFX2_ROOT=$FidelityFxRoot" "-DVEYRA_XESS_ROOT=$XessRoot" `
    -DVEYRA_LIBASS_ROOT= -DVEYRA_VB_CABLE_PACKAGE=
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
cmake --build $BuildDir --parallel 2 --target veyra_qml_ui veyra_preset_library_tests veyra_effect_chain_tests veyra_console_preset_probe veyra_qml_quick_tests
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
