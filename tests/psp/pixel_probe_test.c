#include "../../backend/psp/pixel_probe.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    const float p[6]={0,0,4,0,0,4},reverse[6]={0,4,4,0,0,0},bad[6]={0,0,1,1,2,2};
    float w[3]={-1,-1,-1};
    assert(pixel_probe_weights(1,1,p,w)&&w[0]==.5f&&w[1]==.25f&&w[2]==.25f);
    assert(pixel_probe_weights(1,1,reverse,w)&&w[0]==.25f&&w[1]==.25f&&w[2]==.5f);
    assert(!pixel_probe_weights(3,3,p,w));assert(!pixel_probe_weights(1,1,bad,w));
    assert(!pixel_probe_weights(NAN,0,p,w));assert(!pixel_probe_weights(0,INFINITY,p,w));
    assert(pixel_probe_weights(0,0,p,w)&&w[0]==1);assert(pixel_probe_weights(2,2,p,w)&&w[0]==0);
    puts("pixel probe barycentrics PASS");return 0;
}
