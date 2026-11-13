# Centered video window — Console .2

Use **Ctrl+Alt+C**, the top dock's Center 16:9 window action, or Settings → Startup and window → Fit and center. Startup size **Centered 16:9 video** persists through the existing preference store.

The action returns to a normal cinema window and fits its 16:9 client area into the current monitor's available geometry. Native title-bar/frame margins are included; the taskbar remains usable. The side areas belong to the desktop, so other applications remain accessible. It is not a display mode, resolution or processing-quality change. F11/fullscreen and ordinary Windows maximize retain their meanings. FancyZones keeps ownership of snapped geometry. Manual edge/corner resize hands geometry to Windows rather than allowing the cinema width binding to overwrite height.

Local regression used the actual Main.qml and real bridge in isolated profiles, without opening a capture card. It reproduced the old frameless corner-resize issue, then verified manual resize, centering from windowed/maximized mode, full-height work-area fit, 16:9 client extent and fullscreen round-trip restoration with both caption styles. Additional runs exercise Qt scale factors 1.0, 1.5 and 2.0. This is UI geometry evidence, not a latency or physical display-cadence benchmark. Actual video uses the existing native presentation/Fit path.

On the tested 5120×1440 desktop at 100% scaling, available work area was 5120×1392: borderless client 2475×1392 at x=1322; native-title-bar client 2420×1361, outer frame 2420×1392 centered at x=1350. These are observed local values, not universal defaults. Qt performs placement in device-independent coordinates. Independent mixed-monitor DPI transitions and every third-party window-manager version are not certified by these checks.

A focused source build and packaged playback smoke accompany the local delivery. The public release remains source-only for the distribution reason in [RUNTIMES.md](RUNTIMES.md). The private package retains the current runtimes, effects, audio and profiles. To roll back, close the new folder and open the preserved previous folder. No driver/display settings change is required.
