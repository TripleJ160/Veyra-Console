# Veyra Console 2.1.5-console.2 — centered desktop window

A focused **source-only** release for viewing console video beside other desktop applications.

## What changed

- **Ctrl+Alt+C** fits a centered 16:9 normal window into the current monitor's work area, leaving the desktop sides free on an ultrawide display.
- The top dock and Settings → Startup and window expose the same action. Startup size **Centered 16:9 video** persists through the existing preferences.
- Frameless edge/corner resizing now hands geometry to Windows instead of allowing cinema mode's width/height binding to fight the drag. Snapped/FancyZones rectangles keep their ownership.
- Centering works from windowed, maximized and fullscreen states, includes native title-bar margins, and retains the title-bar preference. F11 and Windows maximize keep their existing meanings.

Window placement does not change capture dimensions, processing resolution, NR, AA, FG, audio or display refresh. A visible taskbar/title bar consumes some image height. There is no image-quality, controller-latency or stall-resolution claim.

## Validation

The exact public source implementation built in optimized Windows Release and passed the native Main.qml/bridge window regression with both caption styles, including automatic centered startup, corner resize, work-area fit, fullscreen restoration and centering from maximize. A separate private build of the same window change passed Qt scale factors 1.0/1.5/2.0, 25 focused QtQuick component checks and a bounded recorded-footage playback smoke. The public build test had no optional vendor models installed; it exercised window geometry, not AI inference.

The initial 200% test requested a window taller than the scaled desktop; Windows clamped it. The corrected fixture requests a legal size. The earlier full Quick suite was interrupted without a result while using an incomplete test plugin path; the corrected focused component run passed. These are retained local test limitations, not hidden product passes. Mixed-monitor DPI transitions and every FancyZones version were not exhaustively retested.

## Distribution and build

**There is no public Windows executable in this release.** The previously documented combined NGX/GPL distribution question remains unresolved. The runnable private application is delivered separately to its owner. No proprietary runtimes/models, personal profiles, recordings or desktop screenshots are in the uploaded assets.

This update is based on the previous public Console .1 source plus the focused window change; it does not publish the separate private ANR/Responsive research branches. Existing Console viewing presets, NR looks and AA behavior remain as documented.

Use [build instructions](https://github.com/TripleJ160/Veyra-Console/blob/main/docs/console/BUILD.md), [window instructions](https://github.com/TripleJ160/Veyra-Console/blob/main/docs/console/CENTERED_WINDOW.md), and [runtime/distribution status](https://github.com/TripleJ160/Veyra-Console/blob/main/docs/console/RUNTIMES.md). The matching patched FFmpeg source remains at the immutable [Console .1 source asset](https://github.com/TripleJ160/Veyra-Console/releases/download/v2.1.5-console.1/FFmpeg-9.0.1-slices256-dav1d-zlib-source.zip); its SHA256 is `49db22049f072bd5448faa664aa736074dccfe6e72b4a933f673d8ae954b0bb6`.

Previous releases/tags remain available for source rollback. For local app rollback, close the new folder and open the preserved prior folder. No driver or display-mode change is needed.
