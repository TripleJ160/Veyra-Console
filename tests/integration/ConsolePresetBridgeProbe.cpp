// Actual bridge/serializer transactions without opening a source or GPU graph.
#include "veyra/ui/QmlPlayerBridge.h"
#include "veyra/engine/EngineController.h"
#include <QApplication>
#include <cstdio>
#include <filesystem>
#include <fstream>

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    if (argc != 2) return 2;
    const auto path = std::filesystem::path(argv[1]);
    if (!path.is_absolute()) return 2;
    int failed = 0;
    auto check = [&](bool ok, const char* name) { std::printf("%s %s\n", ok ? "PASS" : "FAIL", name); failed += !ok; };
    auto bytes = [](const auto& p) { std::ifstream in(p, std::ios::binary); return std::string(std::istreambuf_iterator<char>(in), {}); };
    const auto captureBefore = bytes(path / "capture-preferences.v1");
    for (int index = 0; index != 4; ++index) {
        QString selected;
        {
            veyra::engine::EngineController engine;
            veyra::ui::QmlPlayerBridge bridge(engine, path);
            bridge.setAudioSyncMode(1); bridge.setAudioOffsetMs(37);
            bridge.setVolume(0.37);
            bridge.setPreference("systemTitleBar", index % 2 == 0);
            bridge.setPreference("windowSize", "last");
            bridge.setDlssgLite(true);
            check(bridge.applyPresetIndex(index), "bridge applies viewing preset");
            selected = bridge.presets().at(index).toMap().value("name").toString();
            check(bridge.currentPresetName() == selected, "active label matches complete preset");
            check(!bridge.dlssgLite() && !bridge.vfgAutoRegulate(), "Lite and regulation disabled");
            check(bridge.audioOffsetMs() == 37 && bridge.audioSyncMode() == 1, "audio settings retained");
            check(bridge.preferences().value("volume").toDouble() == 0.37, "volume retained");
            bridge.setContentRate(index == 1 ? 0 : 1);
            check(bridge.currentPresetName() != selected, "advanced cadence becomes Custom");
            check(bridge.applyPresetIndex(index), "preset safely reapplied");
        }
        {
            veyra::engine::EngineController engine;
            veyra::ui::QmlPlayerBridge bridge(engine, path);
            check(bridge.currentPresetName() == selected, "last selected preset survives restart");
            check(bridge.preferences().value("systemTitleBar").toBool() == (index % 2 == 0), "caption preference survives restart");
            check(!bridge.dlssgLite(), "Lite remains off after restart");
            check(bridge.audioOffsetMs() == 37 && bridge.audioSyncMode() == 1, "audio survives restart");
            check(bridge.preferences().value("volume").toDouble() == 0.37, "volume survives restart");
            check(bridge.preferences().value("windowSize").toString() == "last", "geometry preference preserved");
        }
    }
    for (int look = 0; look < 7; ++look) {
        QString selected, viewing;
        {
            veyra::engine::EngineController engine;
            veyra::ui::QmlPlayerBridge bridge(engine, path);
            check(bridge.applyPresetIndex(2), "set PLAY before NR transaction");
            viewing = bridge.currentPresetName();
            check(bridge.setProtectionRegion(.1,.2,.3,.4,0), "explicit protection region set");
            bridge.setProtectionEnabled(true);
            const auto regions = bridge.protectionRegions();
            check(bridge.applyNrLookIndex(look), "NR look transaction accepted through real bridge");
            selected = bridge.nrLooks().at(look).toMap().value("name").toString();
            check(bridge.currentNrLookName() == selected && bridge.currentPresetName() == viewing, "independent look and viewing labels");
            check(bridge.protectionEnabled() && bridge.protectionRegions() == regions, "NR switching preserves protection enabled state and coordinates");
            check(bridge.audioOffsetMs() == 37 && bridge.audioSyncMode() == 1 && !bridge.dlssgLite(), "NR preserves audio and FG Lite");
            check(bridge.applyPresetIndex(3) && bridge.currentNrLookName() == selected, "viewing change preserves NR look");
            if (look) {
                const int n = bridge.nrLayers().at(0).toMap().value("index").toInt();
                check(bridge.setNrLayerParameter(n,"total",.37), "manual blend accepted");
                check(bridge.currentNrLookName() == "Custom", "manual blend displays Custom");
                check(bridge.applyNrLookIndex(look), "restore exact look");
            }
        }
        {
            veyra::engine::EngineController engine;
            veyra::ui::QmlPlayerBridge bridge(engine, path);
            check(bridge.currentNrLookName() == selected && bridge.protectionEnabled(), "NR look and protection persist across restart");
            check(bridge.currentPresetName() == bridge.presets().at(3).toMap().value("name"), "viewing selection also persists");
        }
    }
    for (int method=0; method<4; ++method) {
        {
            veyra::engine::EngineController engine;
            veyra::ui::QmlPlayerBridge bridge(engine,path);
            check(bridge.setAntiAliasParameter("method",method) && bridge.setAntiAliasParameter("enabled",1), "AA setter accepts selected method and enable");
            check(bridge.antiAliasEnabled() && bridge.antiAliasParams().value("method").toInt()==method,"AA UI mirrors active settings");
            check(!bridge.setAntiAliasParameter("method",4),"unsupported AA enum rejected");
        }
        {
            veyra::engine::EngineController engine;
            veyra::ui::QmlPlayerBridge bridge(engine,path);
            check(bridge.antiAliasEnabled() && bridge.antiAliasParams().value("method").toInt()==method,"AA serialization roundtrip");
        }
    }
    {
        veyra::engine::EngineController engine;
        veyra::ui::QmlPlayerBridge bridge(engine,path);
        bridge.setAntiAliasParameter("enabled",1);
        const auto position = [](const QVariantList& nodes, const QString& type) {
            for(int i=0;i<nodes.size();++i) if(nodes[i].toMap().value("type")==type) return i;
            return -1;
        };
        check(bridge.applyNrLookIndex(1),"NR on for processing-order check");
        const auto on=bridge.processingChain(false,false);
        check(position(on,"aa")>position(on,"nr") && position(on,"protection")>=0 && position(on,"aa")>position(on,"protection"),"UI processing order places AA after NR/protection");
        check(bridge.applyNrLookIndex(0),"NR off for processing-order check");
        const auto off=bridge.processingChain(false,false);
        check(position(off,"aa")<position(off,"sr"),"UI processing order places AA before SR without NR");
    }
    check(captureBefore == bytes(path / "capture-preferences.v1"), "capture identity format and color unchanged");
    return failed ? 1 : 0;
}
