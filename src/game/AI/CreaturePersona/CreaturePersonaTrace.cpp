#include "CreaturePersonaTrace.h"
#include "Creature.h"
#include "ObjectGuid.h"
#include <cstdarg>
#include <cstdio>
#include <mutex>
#include <sstream>
#include <unordered_set>
#ifdef _WIN32
#include <direct.h>
#else
#include <sys/stat.h>
#endif

namespace CreaturePersonaTrace
{
namespace
{
std::mutex g_mu;
std::unordered_set<uint32> g_entries;

std::string FilePath(Creature const* c)
{
    return "logs/persona/" + std::to_string(c->GetEntry()) + "_" +
           std::to_string(c->GetGUIDLow()) + ".log";
}
} // namespace

bool IsEntry(uint32 entry)
{
    std::lock_guard<std::mutex> g(g_mu);
    return g_entries.count(entry) != 0;
}

void SetEntry(uint32 entry, bool enable)
{
    std::lock_guard<std::mutex> g(g_mu);
    if (enable)
        g_entries.insert(entry);
    else
        g_entries.erase(entry);
}

void Clear()
{
    std::lock_guard<std::mutex> g(g_mu);
    g_entries.clear();
}

std::string Status()
{
    std::lock_guard<std::mutex> g(g_mu);
    if (g_entries.empty())
        return "persona trace: off";
    std::ostringstream os;
    os << "persona trace entries:";
    for (uint32 e : g_entries)
        os << " " << e;
    return os.str();
}

void Log(Creature const* c, char const* fmt, ...)
{
    if (!c)
        return;
    {
        std::lock_guard<std::mutex> g(g_mu);
        if (!g_entries.count(c->GetEntry()))
            return;
    }

    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

#ifdef _WIN32
    _mkdir("logs");
    _mkdir("logs/persona");
#else
    mkdir("logs", 0755);
    mkdir("logs/persona", 0755);
#endif

    FILE* f = fopen(FilePath(c).c_str(), "a");
    if (!f)
        return;

    time_t now = time(nullptr);
    tm t;
#ifdef _WIN32
    localtime_s(&t, &now);
#else
    localtime_r(&now, &t);
#endif
    fprintf(f, "%02d:%02d:%02d %s\n", t.tm_hour, t.tm_min, t.tm_sec, buf);
    fclose(f);
}
} // namespace CreaturePersonaTrace
