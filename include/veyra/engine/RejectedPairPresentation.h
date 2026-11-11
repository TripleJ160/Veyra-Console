#pragma once
#include "veyra/pipeline/FrameBatch.h"

namespace veyra::engine {
// Opt-in presentation-only experiment. A rejected graph-FG call must have
// produced exactly one real output and evaluated no generation. A disabled
// backend, evaluated history warmup, reduced group, VFG faster-model rescue, or
// presenter-owned FG is not evidence of this case.
//
// Callers may replace only this job's presentation timeline with an unpaced
// one. Producer readiness, FIFO order, consumer fences, graph/history updates,
// output-rate caps and completion-watcher ownership remain mandatory.
// A warmup rejected before any evaluation can qualify; its graph/history reset
// has already occurred and is not undone by ready-driven presentation.
inline bool releaseRejectedCaptureReal(bool enabled,bool physicalCapture,
                                      bool graphFg,bool cachedInput,
                                      unsigned skippedBeforeEval,unsigned evaluated,
                                      bool budgetSeed,const pipeline::FrameBatch& batch) {
    return enabled && physicalCapture && graphFg && !cachedInput
        && skippedBeforeEval>0 && evaluated==0 && !budgetSeed
        && batch.count==1
        && batch.frames[0].kind==pipeline::FrameKind::Real
        && batch.frames[0].identity==batch.identity
        && batch.frames[0].pts100ns==batch.b100ns;
}
}
