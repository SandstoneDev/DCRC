#include "../../backend/debug_config.h"
#include <assert.h>
#include <string.h>
int main(void) {
    const char old[]="# player\r\naspect = wide\r\ncustom = KeepCase\r\naspect=4:3\n";
    DebugIniPair p[]={{"aspect","4:3"},{"fps_hud","on"}};
    char out[256];
    int n=debug_ini_update(old,strlen(old),p,2,out,sizeof out);
    assert(n>0 && (size_t)n==strlen(out));
    assert(strstr(out,"# player\r\n") && strstr(out,"custom = KeepCase\r\n"));
    assert(strstr(out,"aspect = 4:3\n") && !strstr(strstr(out,"aspect")+6,"aspect"));
    assert(strstr(out,"fps_hud = on\n"));
    assert(debug_ini_update(old,strlen(old),p,2,out,4)<0);
    DebugIniPair bad={"aspect","wide\nsecret = changed"};
    assert(debug_ini_update(old,strlen(old),&bad,1,out,sizeof out)<0);
    const char nul[]={'a','=',0,'b'};
    assert(debug_ini_update(nul,sizeof nul,p,2,out,sizeof out)<0);
    return 0;
}
