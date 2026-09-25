#include <cstdlib>
#include "nfd.h"

extern "C" {

nfdresult_t NFD_Init(void) {
    return NFD_OKAY;
}

void NFD_Quit(void) {}

const char* NFD_GetError(void) {
    return "Use the Android system file picker for this operation.";
}

void NFD_ClearError(void) {}

void NFD_FreePathU8(nfdu8char_t* path) {
    std::free(path);
}

nfdresult_t NFD_OpenDialogU8(
        nfdu8char_t** outPath,
        const nfdu8filteritem_t*,
        nfdfiltersize_t,
        const nfdu8char_t*) {
    if (outPath != nullptr) *outPath = nullptr;
    return NFD_CANCEL;
}

nfdresult_t NFD_SaveDialogU8(
        nfdu8char_t** outPath,
        const nfdu8filteritem_t*,
        nfdfiltersize_t,
        const nfdu8char_t*,
        const nfdu8char_t*) {
    if (outPath != nullptr) *outPath = nullptr;
    return NFD_CANCEL;
}

nfdresult_t NFD_PickFolderU8(
        nfdu8char_t** outPath,
        const nfdu8char_t*) {
    if (outPath != nullptr) *outPath = nullptr;
    return NFD_CANCEL;
}

} // extern "C"
