#pragma once
#include "veyra/Log.h"
#include "veyra/diagnostics/HostWaitTrace.h"
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <format>
#include <string>

namespace veyra::diagnostics {
// Wall time includes descheduling. No allocation or logging on normal frames.
class CpuStallTrace {
    using Clock = std::chrono::steady_clock;
public:
    // stage, when given, receives each mark (string literals) for a watchdog.
    explicit CpuStallTrace(const char* component, uint64_t frame = 0, double thresholdMs = 80.0,
                           std::atomic<const char*>* stage = nullptr)
        : component_(component), frame_(frame), thresholdMs_(thresholdMs), stage_(stage) {}
    void mark(const char* stage) {
        if (stage_) stage_->store(stage, std::memory_order_relaxed);
        if (!enabled_) return;
        if (traceQpc_) {
            const auto end = hostWaitNow();
            hostWaitRecord(component_, stage, traceQpc_, end, frame_);
            traceQpc_ = hostWaitNow(); // Exclude event emission from the next stage.
        }
        const auto now = Clock::now();
        if (count_ < samples_.size()) samples_[count_++] = {stage, ms(now - last_)};
        last_ = now;
    }
    ~CpuStallTrace() {
        if (!enabled_) return;
        if (traceQpc_) { hostWaitRecord(component_, "tail", traceQpc_, hostWaitNow(), frame_); traceQpc_ = 0; }
        const auto total = ms(Clock::now() - start_);
        if (total < thresholdMs_) return;
        mark("tail");
        std::string detail;
        for (size_t i = 0; i < count_; ++i)
            detail += std::format(" {}Ms={:.3f}", samples_[i].name, samples_[i].ms);
        log::info(component_, std::format("frame={} totalMs={:.3f}{}", frame_, total, detail));
    }
private:
    static double ms(Clock::duration d) { return std::chrono::duration<double, std::milli>(d).count(); }
    struct Sample { const char* name; double ms; };
    const char* component_;
    uint64_t frame_;
    double thresholdMs_;
    std::atomic<const char*>* stage_;
    const bool enabled_ = log::playbackDiagnostics();
    Clock::time_point start_ = enabled_ ? Clock::now() : Clock::time_point{}, last_ = start_;
    int64_t traceQpc_ = enabled_ ? hostWaitNow() : 0;
    std::array<Sample, 32> samples_{};
    size_t count_ = 0;
};
}
