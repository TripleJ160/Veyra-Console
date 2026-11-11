// Local delivery helper. Reads the user's capture preference file without
// changing it; uses the product serializers and URL builder for private copies.
#include "veyra/engine/PresetLibrary.h"
#include "apps/veyra/ui/CapturePreferenceStore.h"
#include <fstream>
#include <iostream>
#include <memory>

int wmain(int argc,wchar_t** argv){
    if(argc!=6)return 2; // PLAY|VFG|FAITHFUL60|ORIGINALS, bypass chain, capture profile, format key file, destination
    using namespace veyra;
    const bool vfg=std::wstring_view(argv[1])==L"VFG";
    const bool faithful=std::wstring_view(argv[1])==L"FAITHFUL60";
    const bool originals=std::wstring_view(argv[1])==L"ORIGINALS";
    if(!vfg&&!faithful&&!originals&&std::wstring_view(argv[1])!=L"PLAY")return 2;
    const std::filesystem::path dest(argv[5]);std::filesystem::create_directories(dest);
    auto session=std::make_unique<engine::ChainSession>(engine::ChainSession::initial(engine::EnhancementSettings{}));
    if(!engine::ChainSessionStore(argv[2]).load(*session)||!session->valid()||session->active!=engine::ChainMode::List)return 3;
    auto s=std::make_unique<engine::EnhancementSettings>();session->configurations[0].apply(*s);
    if(s->nr||s->sr||s->antiAlias.enabled||s->videoHdr.enabled||s->multiplier!=1)return 4;
    s->multiplier=originals?1:2;s->frameGenerationBackend=vfg?engine::FrameGenerationBackend::Vfg:engine::FrameGenerationBackend::Dlss;
    s->content=faithful?engine::ContentRate::Auto:engine::ContentRate::Transport;
    s->fgMotion=engine::MotionSource::OpticalFlow;s->opticalFlowBackend=engine::OpticalFlowBackend::Nvidia;
    s->dlssgLite=false;s->vfgAutoRegulate=false;s->vfgQuality=1;
    s->audioSync=engine::AudioSyncMode::Automatic;s->audioOffsetMs=0;
    // Seed the same canonical built-in used by the in-app selector, rather than
    // a visually equivalent legacy chain that would correctly read as Custom.
    engine::PresetLibrary viewing(dest/L"unused-library");
    viewing.addViewingBuiltins();
    engine::PresetLibrary::apply(viewing.entries()[originals?0:faithful?1:vfg?3:2],*s);
    if(!s->validate().empty())return 5;
    session->configurations[0]=engine::ChainConfiguration::capture(engine::toChain(*s),*s,-1,-1);
    engine::ChainSessionStore store(dest/L"chain-session.v1");if(!store.save(*session)){std::wcerr<<store.error()<<L'\n';return 6;}
    auto loaded=std::make_unique<engine::ChainSession>(engine::ChainSession::initial(engine::EnhancementSettings{}));
    if(!store.load(*loaded)||!(*loaded==*session))return 7;
    auto capture=ui::CapturePreferenceStore(argv[3]).load();
    std::ifstream keyFile(argv[4]);std::string key;std::getline(keyFile,key);
    if(key.empty()||capture.videoPath.empty()||capture.audioMode<0||capture.audioPath.empty())return 8;
    capture.formatKey=std::wstring(key.begin(),key.end());capture.requestedFps=0;
    capture.colorOverride=capture.colorForDevice(capture.videoPath);
    if(!ui::CapturePreferenceStore(dest).save(capture))return 9;
    source::CaptureDevice video,audio;video.path=capture.videoPath;audio.path=capture.audioPath;
    const auto uri=source::CaptureCardSource::makeCapturePath(0,video,16,capture.audioMode,&audio,capture.colorOverride,0,capture.formatKey);
    if(!uri.starts_with(L"capture2:"))return 10;
    std::ofstream file(dest/L"capture-url.txt",std::ios::binary);for(auto c:uri){if(c>127)return 11;file.put(char(c));}file<<'\n';file.close();
    std::cout<<"{\"roundtrip\":true,\"multiplier\":"<<s->multiplier<<",\"contentRate\":"<<int(s->content)<<",\"lite\":false,\"sr\":false,\"nr\":false,\"flowQuality\":"<<int(s->flow)
        <<",\"motion\":"<<int(s->fgMotion)<<",\"audioMode\":"<<capture.audioMode<<",\"colorOverride\":"<<capture.colorOverride<<"}\n";
    return 0;
}
