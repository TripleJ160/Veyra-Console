// Inject only into a private Main.qml stage, following pro-video-geometry-test.py.
// This checks the real shell's geometry policy, not physical FancyZones gestures.
// Record the executable's provenance separately; zoning requires an actual drag.
import QtQuick
import QtQuick.Window

Item {
    id: probe
    property var appWindow: Window.window
    property int step: -1
    property int ticks: 0
    property real zoneWidth: 1600
    property real zoneHeight: 840
    property var cases: []

    function require(value, message) {
        if (!value) throw new Error(message)
    }
    function record(name) {
        const r = appWindow.videoRect()
        const row = {name:name, page:appWindow.page,
            layoutManaged:appWindow.layoutManagedGeometry, systemTitleBar:appWindow.systemTitleBar,
            window:{x:appWindow.x,y:appWindow.y,w:appWindow.width,h:appWindow.height},
            viewport:{x:r.x,y:r.y,w:r.width,h:r.height},
            aspect:appWindow.filmAspect, fullscreen:appWindow.fullscreen,
            maximized:appWindow.maximized}
        cases.push(row)
        console.log("LAYOUT_GEOMETRY " + JSON.stringify(row))
        return r
    }
    function checkZone(name) {
        const r = record(name)
        require(appWindow.width === zoneWidth && appWindow.height === zoneHeight,
                name + ": layout rectangle was overwritten")
        if (appWindow.page === "min")
            require(r.x === 0 && r.y === 0 && r.width === zoneWidth && r.height === zoneHeight,
                    name + ": viewport does not use the allocated rectangle")
    }
    Timer {
        interval: 150; repeat: true; running: true
        onTriggered: {
            try {
                if (++probe.ticks < 5) return
                probe.ticks = 0
                switch (++probe.step) {
                case 0:
                    veyra.setPreference("reducedMotion", true)
                    probe.appWindow.page = "min"
                    probe.appWindow.layoutManagedGeometry = false
                    probe.appWindow.width = 1280
                    if (probe.appWindow.systemTitleBar) probe.appWindow.height = 720
                    probe.appWindow.fitToFilm(16 / 9)
                    break
                case 1:
                    probe.record("ordinary-cinema")
                    probe.require(probe.appWindow.height === Math.round(probe.appWindow.pictureHeight),
                                  "ordinary cinema no longer follows film aspect")
                    probe.appWindow.layoutManagedGeometry = true
                    probe.appWindow.width = probe.zoneWidth
                    probe.appWindow.height = probe.zoneHeight
                    break
                case 2:
                    probe.checkZone("layout-rectangle")
                    probe.appWindow.fitToFilm(4 / 3)
                    break
                case 3:
                    probe.checkZone("source-aspect-change")
                    probe.appWindow.page = "pro"
                    break
                case 4:
                    probe.checkZone("professional-page")
                    probe.appWindow.page = "min"
                    break
                case 5:
                    probe.checkZone("cinema-return")
                    probe.appWindow.toggleFullscreen()
                    break
                case 6:
                    probe.record("fullscreen")
                    probe.require(probe.appWindow.fullscreen, "fullscreen did not engage")
                    probe.appWindow.toggleFullscreen()
                    break
                case 7:
                    probe.checkZone("fullscreen-return")
                    probe.appWindow.toggleMaximized()
                    break
                case 8:
                    probe.record("maximized")
                    probe.require(probe.appWindow.maximized, "maximize did not engage")
                    probe.appWindow.toggleMaximized()
                    break
                case 9:
                    probe.checkZone("maximize-return")
                    probe.appWindow.layoutManagedGeometry = false
                    probe.appWindow.fitToFilm(16 / 9)
                    break
                case 10:
                    probe.record("ordinary-return")
                    probe.require(probe.appWindow.height === (probe.appWindow.systemTitleBar
                                  ? probe.zoneHeight : Math.round(probe.appWindow.pictureHeight)),
                                  "normal geometry policy did not return")
                    console.log("LAYOUT_GEOMETRY_DONE " + JSON.stringify({passed:true,cases:probe.cases.length}))
                    Qt.quit()
                    break
                }
            } catch (e) {
                console.error("LAYOUT_GEOMETRY_FAIL " + e.message)
                Qt.exit(3)
            }
        }
    }
}
