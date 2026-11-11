#include "veyra/engine/RejectedPairPresentation.h"
#include "veyra/engine/LiveGpuScheduler.h"
#include "veyra/engine/LivePresentationTiming.h"
#include "veyra/engine/LivePresentationResetPolicy.h"
#include "veyra/engine/PresentationScheduler.h"
#include "veyra/engine/PreviewFrameReadiness.h"
#include "veyra/engine/FgRecoveryBudget.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

using namespace veyra;
using Scheduler=engine::LiveGpuScheduler;
using State=Scheduler::State;
using Timeline=engine::PresentationScheduler;
struct Observation {uint64_t source;int64_t pts,host;bool generated;};

// Deterministic CPU replay of the owner-thread loop's readiness -> deadline ->
// Present ordering. These are real production scheduler/readiness/timeline
// helpers. Resolve times, Present and GPU ownership completion are modeled;
// this is not a GPU/resource-barrier or screen-latency test.
struct Replay {
    Scheduler scheduler;
    std::vector<Observation> presented;
    std::vector<std::shared_ptr<pipeline::FrameLease>> completionWatch;
    uint64_t generation=1,consumerSequence=0;
    unsigned finished=0,expired=0,suppressed=0,resolveCalls=0;
    bool enqueue(pipeline::FrameBatch batch,Timeline timeline,
                 std::array<int64_t,pipeline::FrameBatch::Capacity> ready,
                 bool eligible=false,bool optIn=false,int64_t grace=100000) {
        if(engine::releaseRejectedCaptureReal(optIn,true,true,false,eligible?1:0,0,false,batch))
            timeline.resetPair(batch.identity.epoch,batch.b100ns,0,0,false);
        for(unsigned i=0;i<batch.count;++i)completionWatch.push_back(batch.frames[i].lease);
        const auto capturedGeneration=generation;
        return scheduler.push([this,batch=std::move(batch),timeline,ready,grace,capturedGeneration,next=0u](int64_t now) mutable {
            while(next<batch.count) {
                auto& frame=batch.frames[next];
                const bool generated=frame.kind==pipeline::FrameKind::Generated;
                const auto status=engine::previewFrameReadiness(frame,
                    !engine::generatedPresentationCurrent(capturedGeneration,generation),
                    generated&&timeline.expired(frame.pts100ns,now,grace),[&] {
                        ++resolveCalls;
                        if(now<ready[next])return false;
                        if(generated)frame.validity=pipeline::GenerationValidity::Valid;
                        return true;
                    });
                if(status==engine::PreviewFrameReadiness::Pending)return Scheduler::Step{State::Pending,now+2000};
                if(status!=engine::PreviewFrameReadiness::Ready) {
                    expired+=status==engine::PreviewFrameReadiness::Expired;
                    suppressed+=status==engine::PreviewFrameReadiness::Suppressed;
                    ++next;continue;
                }
                if(now<timeline.deadline(frame.pts100ns))return Scheduler::Step{State::Pending,timeline.deadline(frame.pts100ns)};
                frame.lease->consumerFence=++consumerSequence; // modeled consumer completion identity
                presented.push_back({frame.identity.sourceFrameId,frame.pts100ns,now,generated});
                ++next;
            }
            return Scheduler::Step{State::Complete};
        },[this]{++finished;});
    }
};

static pipeline::FrameBatch batch(uint64_t source,int64_t a,int64_t b,bool generated=false,uint64_t epoch=1) {
    pipeline::FrameBatch value;value.identity={epoch,4,source};value.batchId=source;value.a100ns=a;value.b100ns=b;
    if(generated) {
        pipeline::BatchFrame f;f.identity=value.identity;f.kind=pipeline::FrameKind::Generated;
        f.validity=pipeline::GenerationValidity::Pending;f.subframe=1;
        f.pts100ns=pipeline::FrameBatch::interpolate(a,b,1,2);f.lease=std::make_shared<pipeline::FrameLease>();value.append(f);
    }
    pipeline::BatchFrame f;f.identity=value.identity;f.pts100ns=b;f.lease=std::make_shared<pipeline::FrameLease>();value.append(f);
    return value;
}
static Timeline timeline(const pipeline::FrameBatch& value,int64_t realDue) {
    Timeline result;result.resetPair(value.identity.epoch,value.b100ns,realDue,0);return result;
}
static bool ordered(const std::vector<Observation>& values) {
    for(size_t i=1;i<values.size();++i)
        if(values[i].source<values[i-1].source||values[i].pts<=values[i-1].pts||values[i].host<values[i-1].host)return false;
    return true;
}

int wmain(int argc,wchar_t** argv) {
    unsigned checks=0,failed=0;
    auto check=[&](bool ok,const char* label){++checks;failed+=!ok;std::cout<<(ok?"PASS ":"FAIL ")<<label<<'\n';};
    struct Sample {const char* name;uint64_t source;int64_t a,b,arrivalA,arrival,ready,begin,late,elapsed,processStart;};
    // Exact host/PTS values from preserved live logs; lateMs is rounded to
    // 0.001 ms, so reconstructed deadlines/phase have +/-0.0005 ms precision.
    const Sample samples[]{
        {"VFG755",755,132068483,132735147,875884427585,875884439409,875884446731,875885213672,1260,1180,875884442243},
        {"DLSS1041",1041,187237112,187737110,876497715701,876497726322,876497749088,876498332865,2680,4740,876497729676}};
    std::vector<int64_t> reconstructedHolds;
    for(const auto& s:samples) {
        engine::LiveArrivalSmoother smoother;
        smoother.anchor(s.a,s.arrivalA,166667);
        const auto anchor=smoother.anchor(s.b,s.arrival,166667);
        const auto realDue=s.begin-s.late;
        const auto phase=realDue-anchor;
        reconstructedHolds.push_back(realDue-s.ready);
        check(anchor>s.arrival+400000,"one compressed-delivery outlier leaves smoothed anchor over40ms ahead");
        check(phase>110000&&phase<170000,"reconstructed phase remains ordinary11-17ms, not a100ms compute cost");
        Timeline admission;admission.resetPair(1,s.b,s.arrival,phase);
        engine::FgRecoveryBudget budget;budget.complete(2.763,true,false,s.arrival,2.6);
        const auto midpoint=pipeline::FrameBatch::interpolate(s.a,s.b,1,2);
        check(!budget.admit(s.processStart+s.elapsed,admission.deadline(midpoint),double(s.elapsed)/10000,.033),"callback-anchored admission rejects compressed-delivery pair");
        const auto value=batch(s.source,s.a,s.b);
        Replay baseline;baseline.enqueue(value,timeline(value,realDue),{s.ready},true,false);
        baseline.scheduler.advance(s.ready);
        check(baseline.presented.empty()&&baseline.scheduler.wakeAt()==realDue,"rejected ready real waits on future smoothed deadline in baseline");
        baseline.scheduler.advance(realDue);
        check(baseline.presented.size()==1&&baseline.presented[0].host-s.ready==realDue-s.ready,"CPU replay reproduces reconstructed rejected real hold");
        Replay candidate;candidate.enqueue(value,timeline(value,realDue),{s.ready},true,true);
        candidate.scheduler.advance(s.ready-1);
        check(candidate.presented.empty(),"opt-in rejected-real candidate still requires producer readiness");
        candidate.scheduler.advance(s.ready);
        check(candidate.presented.size()==1&&candidate.presented[0].host==s.ready,"isolated eligible head can submit at readiness under candidate policy");
    }
    {
        // Independent synthetic trigger: normal 12ms phase + 66.6664ms PTS
        // advance delivered1.1824ms after the previous callback. No log-derived
        // deadline is needed to generate a long hold.
        engine::LiveArrivalSmoother smoother;
        smoother.anchor(0,1000000,166667);
        const auto anchor=smoother.anchor(666664,1011824,166667);
        check(anchor+120000-1019146==762518,"independent burst input creates76.2518ms ready-to-deadline hold");
        const auto snapped=smoother.anchor(1333328,1022839,166667);
        check(snapped==1022839-engine::LiveArrivalSmoother::kLead100ns,"second same-side outlier snaps anchor to callback");
    }
    {
        // Include the predecessor's still-valid deadline: a real fallback must
        // not jump it. This bounds the counterfactual more tightly than the
        // isolated ready-to-deadline hold above.
        const auto a=batch(751,131735151,132068483),b=batch(755,132068483,132735147),c=batch(759,132735147,133401811);
        for(bool optIn:{false,true}) {
            Replay r;
            r.enqueue(a,timeline(a,875884545744),{875884436887},false,optIn);
            r.enqueue(b,timeline(b,875885212412),{875884446731},true,optIn);
            r.scheduler.advance(875884446731);
            check(r.presented.empty()&&r.scheduler.occupancy()==2,"newer ready rejected pair cannot overtake pending predecessor");
            r.scheduler.advance(875884546404);
            check(r.presented.size()==(optIn?2u:1u),"candidate only removes rejected pair own hold after predecessor presents");
            r.enqueue(c,timeline(c,875884568585),{875884554973},true,optIn);
            r.scheduler.advance(875884554973);
            check(optIn?r.presented.size()==3:r.presented.size()==1,"FIFO propagates old rejected hold to newer ready frame only in baseline");
            r.scheduler.advance(875885213672);
            check(r.presented.size()==3&&ordered(r.presented),"burst recovery preserves source,PTS,and submission order");
            check(r.finished==3&&r.scheduler.occupancy()==0,"both policies finalize three jobs exactly once");
        }
    }
    {
        auto value=batch(20,0,166667);
        auto eligible=[&](bool enabled,bool physical,bool graph,bool cached,unsigned skipped,unsigned evaluated,bool seed){return engine::releaseRejectedCaptureReal(enabled,physical,graph,cached,skipped,evaluated,seed,value);};
        check(eligible(true,true,true,false,1,0,false),"narrow predicate accepts explicit rejected real-only physical capture");
        check(!eligible(false,true,true,false,1,0,false)&&!eligible(true,false,true,false,1,0,false)&&!eligible(true,true,false,false,1,0,false)&&!eligible(true,true,true,true,1,0,false),"default off,file/screen/providerFG,and cached paths are excluded");
        check(!eligible(true,true,true,false,0,0,false)&&!eligible(true,true,true,false,1,1,false)&&!eligible(true,true,true,false,1,0,true),"disabled backend,warmup/reduced/rescue,and budget seeds are excluded");
        value=batch(21,166667,333334,true);
        check(!eligible(true,true,true,false,1,0,false),"multioutput and expired-pair fallback remain excluded");
    }
    {
        Replay r;auto value=batch(30,0,166667);
        std::weak_ptr<pipeline::FrameLease> weak=value.frames[0].lease;
        r.enqueue(std::move(value),Timeline{}, {100},true,true);
        r.scheduler.advance(99);check(!weak.expired()&&r.finished==0,"pending job and completion watcher retain real lease");
        r.scheduler.advance(100);
        check(!weak.expired()&&r.finished==1&&weak.lock()->consumerFence==1,"early Present assigns modeled consumer fence while completion watcher retains lease");
        r.completionWatch.clear();check(weak.expired(),"modeled lease retires only after independent completion-owner release");
    }
    {
        Replay r;const auto rejected=batch(40,0,166667),next=batch(41,166667,333334,true);
        r.enqueue(rejected,timeline(rejected,200000),{100},true,true);r.scheduler.advance(100);
        r.enqueue(next,timeline(next,333334),{200000,200000});r.scheduler.advance(250000);r.scheduler.advance(333334);
        check(r.presented.size()==3&&r.presented[1].generated&&ordered(r.presented),"following successful FG batch retains interpolation PTS and real order");
        check(r.expired==0&&r.finished==2,"candidate changes no FG decisions or recovery batch contents");
    }
    {
        Replay r;const auto value=batch(50,0,166667,true);
        r.enqueue(value,timeline(value,200000),{500000,100},false,true,0);
        r.scheduler.advance(150000);
        check(r.expired==1&&r.presented.empty()&&r.scheduler.wakeAt()==200000,"expired generated output still leaves real waiting: broader policy deliberately unchanged");
        r.scheduler.advance(520000);
        check(r.presented.size()==1&&r.presented[0].host==520000,"no scheduler execution until520000 cannot be fixed by a deadline policy");
        check(r.presented[0].host-100==519900&&200000-100==199900,"host execution gap is kept separate from planned hold");
    }
    {
        using Flags=pipeline::FrameFlagBits;
        check(!engine::presentationGenerationResetRequired(false,static_cast<pipeline::FrameFlags>(Flags::Drop)),"capture drop does not invalidate older leased pair presentation");
        check(engine::presentationGenerationResetRequired(true,0)&&engine::presentationDrainRequired(false,static_cast<pipeline::FrameFlags>(Flags::Resize)),"hard boundary still invalidates generation and resize drains");
        Replay r;auto value=batch(60,0,166667,true);
        r.enqueue(value,timeline(value,0),{999999,100});++r.generation;r.scheduler.advance(100);
        check(r.suppressed==1&&r.resolveCalls==1&&r.presented.size()==1&&!r.presented[0].generated,"obsolete generation skips its producer wait while original retains readiness");
        auto pending=batch(61,166667,333334);r.enqueue(pending,timeline(pending,1000000),{1000000},true,true);r.scheduler.cancel();r.scheduler.cancel();
        check(r.finished==2&&r.scheduler.occupancy()==0,"cancellation finalizes without re-presenting or duplicating release");
    }
    if(argc==3&&std::wstring(argv[1])==L"--json") {
        std::ofstream out{std::filesystem::path(argv[2])};
        out<<"{\n  \"kind\": \"deterministic_cpu_fixture_not_live_performance\",\n  \"checks\": "<<checks<<",\n  \"failed\": "<<failed
           <<",\n  \"reconstructed_vfg755_deadline_hold_100ns\": "<<reconstructedHolds[0]
           <<",\n  \"reconstructed_dlss1041_deadline_hold_100ns\": "<<reconstructedHolds[1]
           <<",\n  \"synthetic_burst_deadline_hold_100ns\": 762518,\n  \"gpu_and_scanout_validated\": false\n}\n";
        if(!out)return 2;
    }
    std::cout<<checks<<" checks, "<<failed<<" failures; deterministic CPU evidence only\n";
    return failed?1:0;
}
