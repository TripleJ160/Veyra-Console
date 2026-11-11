#pragma once
#include <cstdint>

namespace veyra::diagnostics {
// Task-specific ETW diagnostic. No logger, heap allocation, or GPU wait in a span.
// Initialize before worker threads; destroy after they have joined.
class HostWaitSession {
public:
    HostWaitSession() noexcept;
    ~HostWaitSession();
    HostWaitSession(const HostWaitSession&) = delete;
    HostWaitSession& operator=(const HostWaitSession&) = delete;
    unsigned long status() const noexcept { return status_; }
private:
    unsigned long status_ = 0;
    bool registered_ = false;
};
bool hostWaitEnabled() noexcept;
int64_t hostWaitNow() noexcept; // Raw QPC, zero when opt-in is off.
void hostWaitRecord(const char* area, const char* operation, int64_t start, int64_t end,
                    uint64_t loop = 0, int64_t result = 0) noexcept;
struct HostWaitIdentity { uint64_t source = 0, epoch = 0, revision = 0; };
class HostWaitContext {
public:
    explicit HostWaitContext(HostWaitIdentity identity) noexcept;
    ~HostWaitContext();
    HostWaitContext(const HostWaitContext&) = delete;
    HostWaitContext& operator=(const HostWaitContext&) = delete;
private:
    HostWaitIdentity previous_;
};
class HostWaitSpan {
public:
    HostWaitSpan(const char* area, const char* operation) noexcept
        : area_(area), operation_(operation), start_(hostWaitNow()) {}
    ~HostWaitSpan() { finish(); }
    HostWaitSpan(const HostWaitSpan&) = delete;
    HostWaitSpan& operator=(const HostWaitSpan&) = delete;
    void finish(int64_t result = 0) noexcept {
        if (start_) { hostWaitRecord(area_, operation_, start_, hostWaitNow(), 0, result); start_ = 0; }
    }
private:
    const char* area_;
    const char* operation_;
    int64_t start_;
};
}
