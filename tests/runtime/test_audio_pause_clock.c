#include "../../backend/audio_pause_clock.h"
#include <assert.h>
int main(void){
    uint64_t before=audio_unpaused_wait(100,0);
    uint64_t during=audio_unpaused_wait(10000100,10000000);
    uint64_t after=audio_unpaused_wait(10000150,10000000);
    assert(before==100&&during==100&&after==150);
    assert(before<=during&&during<=after);
    assert(audio_unpaused_wait(1,2)==0);return 0;
}
