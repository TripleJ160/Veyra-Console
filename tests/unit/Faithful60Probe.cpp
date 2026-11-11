// CPU-only investigation. Synthetic picture IDs and assumed 3 ms readiness;
// not a backend, capture, GPU-performance or physical-display benchmark.
#define NOMINMAX
#include "veyra/engine/ContentDedup.h"
#include "veyra/engine/LivePairLatency.h"
#include "veyra/engine/LivePresentationTiming.h"
#include "veyra/engine/PresentationScheduler.h"
#include "veyra/engine/PresentationSettings.h"
#include "veyra/pipeline/FrameBatch.h"
#include "veyra/pipeline/PictureCompare.h"
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>
#include <filesystem>

int main(int argc,char** argv) {
    using namespace veyra::engine;
    using namespace veyra::pipeline;
    if(argc!=2)return 2;
    const std::filesystem::path root(argv[1]);
    std::filesystem::create_directories(root);
    std::ofstream rows(root/"lineage.csv"), summary(root/"summary.csv");
    rows<<"scenario,transport_index,host_callback_100ns,sample_pts_100ns,picture_a,picture_b,kind,subframe,multiplier,content_pts_100ns,present_model_100ns,b_callback_age_ms\n";
    summary<<"scenario,transport,kept,held,repeat_dropped,real_candidates,generated_candidates,changing_generated_candidates,shadow_dedup_estimate_fps,steady_interval_min_ms,steady_interval_max_ms,steady_b_age_min_ms,steady_b_age_max_ms\n";
    int failed=0;
    auto check=[&](bool ok,const char* label){std::printf("%s %s\n",ok?"PASS":"FAIL",label);failed+=!ok;};
    auto run=[&](const char* name,int rate,bool deduplicate,unsigned multiplier,bool transition=false){
        ContentDedup dedup; LivePairLatency phase; LiveArrivalSmoother arrival; PresentationScheduler scheduler;
        constexpr int64_t transport=166667, hostBase=100000000;
        const int count=transition?2400:600;
        int kept=0,real=0,generated=0,changing=0;bool ordered=true,contentOrdered=true,withinSample=true,allChanges=true;
        int64_t previousPts=-1,previousPresent=-1;uint64_t previousId=0,lastInput=UINT64_MAX;
        double minInterval=1e9,maxInterval=0,minAge=1e9,maxAge=-1e9;
        for(int i=0;i<count;++i){
            const int section=i/600;
            const int hz=transition?(section==0?30:section==1?60:section==2?40:30):rate;
            const uint64_t id=transition?uint64_t(section)*10000+uint64_t((i%600)*hz/60):uint64_t(i*hz/60);
            const int64_t sample=int64_t(i)*transport+1000,callback=hostBase+sample;
            auto d=dedup.observe(&id,sample,transport,i==0);
            if(!deduplicate){d.keep=true;d.contentPts=sample;d.interval=transport;}
            if(id!=lastInput&&!d.keep)allChanges=false;
            lastInput=id;
            if(!d.keep)continue;
            ++kept; withinSample&=d.contentPts<=sample;
            if(previousPts>=0)contentOrdered&=d.contentPts>previousPts;
            const auto anchor=deduplicate?arrival.contentAnchor(d.contentPts,sample,callback,transport):arrival.anchor(d.contentPts,callback,transport);
            const int64_t interval=previousPts>=0?d.contentPts-previousPts:transport;
            const auto delay=phase.select(callback,interval,interval,multiplier,deduplicate?transport/2:0);
            scheduler.resetPair(1,d.contentPts,anchor,delay);
            int64_t required=0;
            auto emit=[&](unsigned j,bool gen){
                const int64_t pts=gen?FrameBatch::interpolate(previousPts,d.contentPts,j,multiplier):d.contentPts;
                const int64_t ready=callback+(multiplier>1?30000:5000);
                const int64_t present=multiplier>1&&previousPts>=0?std::max(ready,scheduler.deadline(pts)):ready;
                if(previousPresent>=0)ordered&=present>previousPresent;
                const double age=double(present-callback)/10000;
                if(i>=180&&!transition){
                    minInterval=std::min(minInterval,double(present-previousPresent)/10000);
                    maxInterval=std::max(maxInterval,double(present-previousPresent)/10000);
                    minAge=std::min(minAge,age);maxAge=std::max(maxAge,age);
                }
                rows<<name<<','<<i<<','<<callback<<','<<sample<<','<<(previousPts>=0?previousId:id)<<','<<id<<','<<(gen?"generated":"real")<<','<<j<<','<<multiplier<<','<<pts<<','<<present<<','<<age<<'\n';
                previousPresent=present;required=std::max(required,ready-anchor+d.contentPts-pts);
                if(gen){++generated;changing+=id!=previousId;}else ++real;
            };
            if(previousPts>=0)for(unsigned j=1;j<multiplier;++j)emit(j,true);
            emit(0,false);
            if(multiplier>1&&previousPts>=0)phase.observe(callback,required);
            previousPts=d.contentPts;previousId=id;
        }
        summary<<name<<','<<count<<','<<kept<<','<<dedup.stats().held<<','<<(deduplicate?dedup.stats().repeats:0)<<','<<real<<','<<generated<<','<<changing<<','<<dedup.contentFps()<<','<<(transition?0:minInterval)<<','<<(transition?0:maxInterval)<<','<<(transition?0:minAge)<<','<<(transition?0:maxAge)<<'\n';
        check(allChanges,(std::string(name)+": no distinct synthetic picture discarded").c_str());
        check(withinSample,(std::string(name)+": content PTS no later than sample").c_str());
        check(contentOrdered,(std::string(name)+": monotonic content PTS including rate transitions").c_str());
        // Transition readiness is a model, without production queue rejection/reset handling.
        // Test timestamp order separately there; do not assert physical pacing from this model.
        if(!transition)check(ordered,(std::string(name)+": ordered content and modeled presentations").c_str());
        check(real==kept&&generated==(kept-1)*int(multiplier-1),(std::string(name)+": one original plus requested interpolants per retained pair").c_str());
        if(deduplicate&&!transition)check(kept==rate*10,(std::string(name)+": expected retained pictures").c_str());
    };
    run("bypass_30_in_60",30,false,1);
    run("bypass_60_in_60",60,false,1);
    run("play_30_in_60_x2",30,false,2);
    run("auto_30_in_60_x2",30,true,2);
    run("auto_30_in_60_x4",30,true,4);
    run("auto_60_in_60_x2",60,true,2);
    run("auto_30_60_40_30_x2",30,true,2,true);
    {
        // Production rate-cap helper has no frame-kind input. On an ideal
        // 120-candidate grid, either parity can win a 60-slot cap.
        for(int first=0;first<2;++first){
            PresentationCadence cap;int retainedReal=0,retainedGenerated=0;
            for(int i=first;i<120;++i){
                const int64_t now=1000000+i*83333LL;
                if(cap.rateSkipsCandidate(now,now,83333,166666))continue;
                cap.rateSubmitted(now,166666);
                if(i%2)++retainedGenerated;else ++retainedReal;
            }
            check(first?retainedGenerated==60&&retainedReal==0:retainedReal==60&&retainedGenerated==0,
                  first?"60 cap phase can keep generated candidates only":"60 cap phase can keep originals only");
        }
    }
    {
        ContentDedup d;int kept=0;uint64_t id=1;int64_t last=-1;
        bool monotonic=true;
        for(int i=0;i<600;++i){auto r=d.observe(&id,i*166667LL+1000,166667,i==0);if(r.keep){monotonic&=r.contentPts>last;last=r.contentPts;++kept;}}
        check(monotonic,"static hold PTS ordered");
        check(d.stats().held>250&&kept>250,"static screen retains holds: kept rate is not unique-picture rate");
    }
    {
        ContentDedup d;uint64_t id=1;
        d.observe(&id,1000,166667,true);
        check(!d.observe(&id,167667,166667,false).keep,"duplicate inside a continuous epoch is rejected");
        auto reset=d.observe(&id,1000,166667,true);
        check(reset.keep&&reset.contentPts==1000&&reset.interval==0,"boundary starts a fresh source epoch without stale content PTS");
        check(d.observe(nullptr,167667,166667,false).keep,"unknown picture identity keeps the source sample");
        auto gap=d.observe(&id,10000000,166667,false);
        check(gap.keep&&gap.interval==0,"long delivery gap resets dedup timing");
    }
    {
        // Actual 1440p NV12 component count, including chroma; no GPU or file codec.
        std::vector<uint8_t> pixels(2560*1440*3/2,60);
        PicturePlane p{pixels.data(),2560,2560,2160};PictureReference ref;
        auto a=ref.observe(&p,1,PictureComponents::Bytes);
        for(int i=0;i<28;++i)pixels[i]=68;
        auto b=ref.observe(&p,1,PictureComponents::Bytes);
        check(b.repeat&&b.id==a.id,"1440 NV12: 28 isolated changed components may be suppressed");
        pixels[28]=68;auto c=ref.observe(&p,1,PictureComponents::Bytes);
        check(!c.repeat&&c.id!=a.id,"1440 NV12: 29 changed components exceed tolerance");
        std::fill(pixels.begin(),pixels.end(),60);PictureReference fade;
        fade.observe(&p,1,PictureComponents::Bytes);
        std::fill(pixels.begin(),pixels.end(),63);
        check(fade.observe(&p,1,PictureComponents::Bytes).repeat,"whole-picture three-level change is inside noise band");
        std::fill(pixels.begin(),pixels.end(),64);
        check(!fade.observe(&p,1,PictureComponents::Bytes).repeat,"comparison to last new picture accumulates slow change");
    }
    if(!rows||!summary)return 3;
    std::printf("RESULT failed=%d; synthetic CPU contracts only; readiness assumed, no GPU/display claims\n",failed);
    return failed?1:0;
}
