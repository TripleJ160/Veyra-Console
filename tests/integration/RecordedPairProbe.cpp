// Bounded offline quality probe using the production graph. PNG readback and
// serialization deliberately happen after the graph's timestamp queries finish.
// This is not a live presenter or a sustained-throughput benchmark.
// usage: <runtime-dir> <endpoint-list.txt> <new-output-dir> <vfg|dlss|dlss-lite>
// Endpoint list: relative-PNG-filename PTS-milliseconds, one per line (2..16).
#include "veyra/pipeline/EnhanceGraph.h"
#include "veyra/gfx/D3D12DeviceContext.h"
#include "veyra/gfx/CommandSlotRing.h"
#include "veyra/sink/ImageExportSink.h"
#include "veyra/Log.h"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <format>
#include <iomanip>
#include <iostream>
#include <vector>
extern "C" {
#include <libavutil/frame.h>
#include <libavutil/pixfmt.h>
}
using namespace veyra;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
double elapsed(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
struct Input {sink::RgbaImage image;double pts;};
int wmain(int argc,wchar_t** argv){
    if(argc!=5){std::cerr<<"usage: runtime endpoint-list new-output-dir vfg|dlss|dlss-lite\n";return 2;}
    const fs::path runtime=fs::absolute(argv[1]),listPath=fs::absolute(argv[2]),dir=fs::absolute(argv[3]);
    const std::wstring mode=argv[4];const bool vfg=mode==L"vfg",lite=mode==L"dlss-lite";
    if(!vfg&&!lite&&mode!=L"dlss")return 2;
    if(fs::exists(dir)||!fs::is_directory(runtime)){std::cerr<<"output must be new and runtime must exist\n";return 2;}
    fs::create_directories(dir);
    if(FAILED(CoInitializeEx(nullptr,COINIT_MULTITHREADED)))return 2;
    Logger::instance().openFile((dir/L"graph.log").wstring());
    std::ifstream endpoints(listPath);std::vector<Input> inputs;std::string name;double pts;
    while(endpoints>>name>>pts){
        Input input{{},pts};
        if(inputs.size()>=16||!sink::loadImage((listPath.parent_path()/fs::u8path(name)).wstring(),input.image)||
           (!inputs.empty()&&(pts<=inputs.back().pts||input.image.width!=inputs[0].image.width||input.image.height!=inputs[0].image.height)))return 2;
        inputs.push_back(std::move(input));
    }
    if(!endpoints.eof()||inputs.size()<2)return 2;
    const auto start=Clock::now();
    gfx::D3D12DeviceContext ctx;gfx::CommandSlotRing ring;Status st=Status::Ok;
    gfx::DeviceContextDesc dd;dd.requiredVendorId=0x10de;dd.enableDebugLayer=false;
    if(!ctx.initialize(dd,st)||!ring.initialize(ctx.device(),ctx.directQueue(),ctx.fence(),ctx.fenceEvent(),6,st))return 3;
    pipeline::EnhanceGraph graph(ctx,ring);pipeline::EnhanceGraphDesc gd;
    gd.sourceWidth=gd.workWidth=gd.flowWidth=inputs[0].image.width;
    gd.sourceHeight=gd.workHeight=gd.flowHeight=inputs[0].image.height;
    gd.rgbInput=true;gd.enableNr=false;gd.enableSr=false;gd.enableFg=true;gd.fgMultiplier=2;
    gd.frameGenerationBackend=vfg?engine::FrameGenerationBackend::Vfg:engine::FrameGenerationBackend::Dlss;
    gd.vfgQuality=1;gd.vfgAutoRegulate=false;gd.vfgFastFallback=false;gd.vfgAsyncSubmission=false;
    gd.dlssgLite=lite;gd.fgMotion=engine::MotionSource::Automatic;
    gd.flowQuality=engine::FlowQuality::Balanced;gd.opticalFlowBackend=engine::OpticalFlowBackend::Nvidia;
    gd.validateMotion=true;gd.fgMotionRefine=true;gd.runtimeAbsPath=runtime.wstring();
    if(!graph.initialize(gd)||!graph.createViews())return 3;
    graph.recordGpuTimings();
    std::ofstream summary(dir/L"configuration.txt");
    summary<<"mode="<<fs::path(mode).string()<<"\nwidth="<<gd.workWidth<<"\nheight="<<gd.workHeight
        <<"\nmultiplier=2\nvfgQuality=1\nvfgAutoRegulate=0\nvfgFastFallback=0\nvfgAsyncSubmission=0"
          "\nfgMotion=Automatic\nflowQuality=Balanced\nopticalFlowBackend=Nvidia\nvalidateMotion=1\nfgMotionRefine=1"
          "\nNR=0\nSR=0\ninput=RGBA8-full-sRGB\ndepth=product-estimated-or-constant\ndebugLayer=0\n"
        <<"flowWidth="<<graph.flowWidth()<<"\ndlssgLiteState="<<graph.dlssgLiteState()
        <<"\ninitializationWallMs="<<elapsed(start)<<"\nadapterLuid="<<ctx.adapter().luid
        <<"\nadapterDeviceId="<<ctx.adapter().deviceId<<"\n";summary.flush();
    if(lite&&graph.dlssgLiteState()!=1){std::cerr<<"requested Lite runtime was not activated\n";return 3;}
    // Record the actual loaded module paths; the runner hashes these after exit.
    std::ofstream modules(dir/L"loaded-modules.tsv");
    for(const auto* dll:{L"nvngx_dlssg.dll",L"nvngx_dlss.dll",L"NVVideoEffects.dll",L"nvVFXVideoFrameGeneration.dll",L"NVCVImage.dll",L"nvofapi64.dll",L"nvcuda.dll"}){
        if(auto handle=GetModuleHandleW(dll)){wchar_t path[32768]{};GetModuleFileNameW(handle,path,32768);
            const auto utf8=fs::path(path).u8string();modules<<fs::path(dll).string()<<'\t'<<std::string(utf8.begin(),utf8.end())<<'\n';}}
    modules.flush();
    AVFrame* frame=av_frame_alloc();if(!frame)return 3;
    frame->width=int(gd.workWidth);frame->height=int(gd.workHeight);frame->format=AV_PIX_FMT_RGBA;
    frame->color_range=AVCOL_RANGE_JPEG;frame->color_trc=AVCOL_TRC_IEC61966_2_1;frame->colorspace=AVCOL_SPC_RGB;
    if(av_frame_get_buffer(frame,32)<0){av_frame_free(&frame);return 3;}
    std::ofstream frames(dir/L"frames.csv"),timings(dir/L"gpu-timings.csv");
    frames<<"endpointIndex,ptsMs,processAndCompletionWallMs,readbackAndPngWallMs,totalFrameWallMs,generatedCandidates,generatedValid,realRoundtripRgbMae,realRoundtripRgbMax\n";
    timings<<"sourceFrameId,stage,state,milliseconds,begin,end,frequency\n";
    frames<<std::setprecision(12);timings<<std::setprecision(12);
    bool ok=true;unsigned validTotal=0;
    for(size_t k=0;k<inputs.size()&&ok;++k){
        const auto frameStart=Clock::now();const auto& input=inputs[k];
        for(uint32_t y=0;y<gd.workHeight;++y)std::memcpy(frame->data[0]+size_t(y)*frame->linesize[0],input.image.pixels.data()+size_t(y)*gd.workWidth*4,size_t(gd.workWidth)*4);
        pipeline::EnhanceGraph::FrameOutputs out;
        ok=graph.process(frame,input.pts,k==0,out,k+1)&&ring.waitIdle()&&graph.resolveGeneration(out);
        const double processMs=elapsed(frameStart);
        // Queries were recorded asynchronously by the product graph. Diagnostic
        // synchronization here is outside their measured begin/end timestamps.
        for(const auto& timing:graph.takeGpuTimings())for(size_t s=0;s<timing.gpu.size();++s){
            const auto& sample=timing.gpu[s];if(sample.state==diagnostics::SampleState::NotExecuted)continue;
            timings<<timing.identity.sourceFrameId<<','<<s<<','<<int(sample.state)<<',';
            if(sample.milliseconds)timings<<*sample.milliseconds;
            timings<<','<<sample.begin<<','<<sample.end<<','<<sample.frequency<<'\n';}
        timings.flush();if(!ok)break;
        const auto ioStart=Clock::now();sink::RgbaImage real;
        ok=sink::readRgba8(ctx,ring,graph.videoFrameResource(out.videoSlot),real)&&sink::saveImage((dir/std::format("real-{:02}.png",k+1)).wstring(),real);
        uint64_t error=0;unsigned maximum=0,valid=0,candidates=0;
        if(ok&&real.pixels.size()==input.image.pixels.size()){
            for(size_t p=0;p<real.pixels.size();++p)if(p%4!=3){const unsigned e=unsigned(std::abs(int(real.pixels[p])-int(input.image.pixels[p])));error+=e;maximum=std::max(maximum,e);}
        }else ok=false;
        for(unsigned n=0;n<out.batch.count&&ok;++n){const auto& item=out.batch.frames[n];
            if(item.kind!=pipeline::FrameKind::Generated)continue;++candidates;
            if(item.validity!=pipeline::GenerationValidity::Valid){std::cerr<<"invalid generated pair="<<k<<" validity="<<int(item.validity)<<'\n';continue;}
            sink::RgbaImage generated;ok=sink::readRgba8(ctx,ring,graph.generatedFrameResource(item.lease->slot),generated)&&sink::saveImage((dir/std::format("pair-{:02}.png",k)).wstring(),generated);
            if(ok){++valid;++validTotal;}}
        frames<<k<<','<<input.pts<<','<<processMs<<','<<elapsed(ioStart)<<','<<elapsed(frameStart)<<','<<candidates<<','<<valid<<','<<double(error)/(size_t(gd.workWidth)*gd.workHeight*3)<<','<<maximum<<'\n';frames.flush();
        if(k>0&&valid!=1)ok=false;
    }
    av_frame_free(&frame);ring.waitIdle();graph.shutdown();
    summary<<"validPairs="<<validTotal<<"\nsuccess="<<(ok&&validTotal==inputs.size()-1)<<"\n";
    Logger::instance().flush();CoUninitialize();
    return ok&&validTotal==inputs.size()-1?0:4;
}
