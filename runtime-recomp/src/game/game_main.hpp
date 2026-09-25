#pragma once

// Platform-neutral DKR-R launcher entrypoint.
//
// Desktop builds expose this through main()/WinMain(). Android links the same
// function into libmain.so and calls it from its native activity/SDL entry
// layer, avoiding a second implementation of launcher/runtime orchestration.
int DkrMain(int argc, char** argv);
