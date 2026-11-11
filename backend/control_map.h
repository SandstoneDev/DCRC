/* Guest-only PSP remapping. PSP button bit values are stable SDK constants. MIT. */
#pragma once
#include <stdint.h>
#include <string.h>
#define CONTROL_COUNT 12
#define CONTROL_DEFAULTS {1,2,3,4,5,6,7,0,8,9,10,11}
extern unsigned char hle_control_map[CONTROL_COUNT];
/* Unknown keys/values decline without changing the previous valid binding. */
static inline int control_map_setting(unsigned char *map,const char *key,const char *value) {
    static const char *const names[CONTROL_COUNT]={"cross","circle","square","triangle","l","r","start","select","up","down","left","right"};
    static const char *const actions[12]={"disabled","a","b","x","y","ltrigger","rtrigger","start","up","down","left","right"};
    int i,j;
    if(strncmp(key,"control_",8))return 0;
    for(i=0;i<CONTROL_COUNT;i++)if(!strcmp(key+8,names[i]))break;
    if(i==CONTROL_COUNT)return -1;
    for(j=0;j<12;j++)if(!strcmp(value,actions[j]))break;
    if(j==12)return -1;
    map[i]=(unsigned char)j;return 1;
}
static inline uint32_t control_map_apply(const unsigned char *map,uint32_t raw,unsigned char *lt,unsigned char *rt) {
    static const uint32_t physical[CONTROL_COUNT]={0x4000,0x2000,0x8000,0x1000,0x100,0x200,8,1,0x10,0x40,0x80,0x20};
    static const uint32_t digital[12]={0,4,2,0x400,0x200,0,0,8,0x10,0x20,0x40,0x80};
    uint32_t result=0;int i;*lt=*rt=0;
    for(i=0;i<CONTROL_COUNT;i++)if(raw&physical[i]){
        unsigned int action=map[i];
        if(action<12){result|=digital[action];if(action==5)*lt=255;if(action==6)*rt=255;}
    }
    return result;
}
