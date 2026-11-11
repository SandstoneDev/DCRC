/* Bounded SMSB/SMSD event scheduling. Own implementation, MIT.
 * Format facts checked against user-local sound banks and the owner's prior
 * driver-format research and dc-manatee docs/notes/sequence_format.md (format
 * facts only; no implementation copied). No game data, guest pointers or IO.
 * Time is Q14 driver ticks; one driver tick is4ms, advanced by the audio core.
 */
#pragma once
#include <stdint.h>
#include <string.h>

#define SND_SEQ_PORTS 6
#define SND_SEQ_PENDING 48
#define SND_SEQ_BUDGET 512
#define SND_SEQ_SCALE 16384
typedef void (*snd_seq_emit)(void *,unsigned,unsigned,unsigned,unsigned);
typedef struct {
    uint32_t bank, bank_size, base, end, pos, timebase, unit;
    uint32_t call_ret, loop_pos;
    int64_t wait, gate_extra, delta_extra;
    uint8_t active, fault, call_left, loop_left;
} snd_sequence;
typedef struct { int64_t left; uint8_t on,port,ch,key; } snd_seq_note;
typedef struct { snd_sequence port[SND_SEQ_PORTS]; snd_seq_note note[SND_SEQ_PENDING]; } snd_sequencer;

static uint32_t snd_seq_u32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static int snd_seq_take(snd_sequence *s,const uint8_t *ram,uint32_t *pos,unsigned n,uint32_t *v) {
    if(*pos>s->end || n>s->end-*pos)return 0;
    *v=0;
    while(n--){*v=(*v<<8)|ram[(*pos)++];}
    return 1;
}
static void snd_seq_stop(snd_sequencer *q,unsigned p,snd_seq_emit emit,void *opaque) {
    if(p>=SND_SEQ_PORTS)return;
    for(unsigned i=0;i<SND_SEQ_PENDING;i++)if(q->note[i].on&&q->note[i].port==p){
        if(emit)emit(opaque,p,0x80|q->note[i].ch,q->note[i].key,0);
        q->note[i].on=0;
    }
    q->port[p].active=0;q->port[p].call_left=0;q->port[p].loop_pos=0;
}
static int snd_seq_start(snd_sequencer *q,unsigned p,const uint8_t *ram,uint32_t ram_size,
                         uint32_t bank,uint32_t bank_size,uint32_t song,snd_seq_emit emit,void *opaque) {
    if(p>=SND_SEQ_PORTS)return 0;
    snd_seq_stop(q,p,emit,opaque);
    snd_sequence *s=&q->port[p];memset(s,0,sizeof *s);
    s->fault=1;
    if(bank>ram_size || bank_size>ram_size-bank || bank_size<24)return 0;
    const uint8_t *b=ram+bank;
    if(snd_seq_u32(b)!=0x42534d53u || b[4]!=1)return 0;
    uint32_t size=snd_seq_u32(b+8),count=snd_seq_u32(b+12);
    if(size<24 || size>bank_size || count>(size-16)/4 || song>=count ||
       snd_seq_u32(b+size-4)!=0x42444e45u)return 0;
    uint32_t off=snd_seq_u32(b+16+song*4);
    uint32_t end=song+1<count?snd_seq_u32(b+20+song*4):size-4;
    if(off<16+count*4 || off>end || end>size-4 || end-off<12 ||
       snd_seq_u32(b+off)!=0x44534d53u)return 0;
    uint32_t timebase=snd_seq_u32(b+off+4),beat=snd_seq_u32(b+off+8);
    uint64_t unit=(uint64_t)timebase*beat>>4;
    if(!unit || unit>0x7fffffffu)return 0;
    s->bank=bank;s->bank_size=size;s->base=bank+off;s->end=bank+end;
    s->pos=s->base+12;s->timebase=timebase;s->unit=(uint32_t)unit;
    s->active=1;s->fault=0;return 1;
}
static void snd_seq_fail(snd_sequencer *q,unsigned p,snd_seq_emit emit,void *opaque) {
    snd_seq_stop(q,p,emit,opaque);q->port[p].fault=1;
}
static int snd_seq_busy(const snd_sequencer *q) {
    for(unsigned p=0;p<SND_SEQ_PORTS;p++)if(q->port[p].active)return 1;
    for(unsigned i=0;i<SND_SEQ_PENDING;i++)if(q->note[i].on)return 1;
    return 0;
}
static void snd_seq_tick(snd_sequencer *q,const uint8_t *ram,snd_seq_emit emit,void *opaque) {
    for(unsigned i=0;i<SND_SEQ_PENDING;i++)if(q->note[i].on){
        snd_seq_note *n=&q->note[i];n->left-=SND_SEQ_SCALE;
        if(n->left<=0){emit(opaque,n->port,0x80|n->ch,n->key,0);n->on=0;}
    }
    for(unsigned p=0;p<SND_SEQ_PORTS;p++){
        snd_sequence *s=&q->port[p];if(!s->active)continue;
        s->wait-=SND_SEQ_SCALE;
        unsigned budget=0;
        while(s->active && s->wait<=0){
        parse:
            if(++budget>SND_SEQ_BUDGET){snd_seq_fail(q,p,emit,opaque);break;}
            uint32_t c,a,b,d=0,gate=0,pos=s->pos;int counted=1;
            if(pos==s->end){s->active=0;break;}
            if(!snd_seq_take(s,ram,&pos,1,&c))goto malformed;
            if(c<0x80){
                if(!snd_seq_take(s,ram,&pos,1,&a)||a>127 ||
                   !snd_seq_take(s,ram,&pos,1,&b)||b>127 ||
                   !snd_seq_take(s,ram,&pos,1+(c>>5),&gate)||
                   !snd_seq_take(s,ram,&pos,1+((c>>4)&1),&d))goto malformed;
                unsigned i;
                for(i=0;i<SND_SEQ_PENDING;i++)if(!q->note[i].on)break;
                if(i==SND_SEQ_PENDING)goto malformed;
                int64_t duration=(int64_t)gate*s->unit;
                if(duration>INT64_MAX/2-s->gate_extra)goto malformed;
                duration+=s->gate_extra;
                q->note[i]=(snd_seq_note){duration+s->wait,1,(uint8_t)p,(uint8_t)(c&15),(uint8_t)a};
                s->gate_extra=0;emit(opaque,p,0x90|(c&15),a,b);
            }else if(c==0x83){s->active=0;s->pos=pos;break;
            }else if(c==0x84){
                if(!snd_seq_take(s,ram,&pos,2,&a)||!snd_seq_take(s,ram,&pos,1,&d))goto malformed;
                uint64_t unit=(uint64_t)s->timebase*a>>4;
                if(!unit||unit>0x7fffffffu)goto malformed;
                s->unit=(uint32_t)unit;
            }else if(c==0x81){
                if(s->call_left||!snd_seq_take(s,ram,&pos,2,&a)||!snd_seq_take(s,ram,&pos,1,&b))goto malformed;
                if(a<12 || a>=s->end-s->base)goto malformed;
                s->call_ret=pos;s->call_left=(uint8_t)b;s->pos=s->base+a;
                goto parse;
            }else if(c==0x82){
                if(!s->loop_pos){s->loop_pos=pos;
                    if(!snd_seq_take(s,ram,&pos,1,&a))goto malformed;
                    s->loop_left=(uint8_t)((a&127)?a&127:128);
                }else if(!s->loop_left){s->loop_pos=0;
                    if(!snd_seq_take(s,ram,&pos,1,&a))goto malformed;
                }else{pos=s->loop_pos;
                    if(!snd_seq_take(s,ram,&pos,1,&a))goto malformed;
                    if(s->loop_left!=128)s->loop_left--;
                }
                if(!snd_seq_take(s,ram,&pos,1+((a>>7)&1),&d))goto malformed;
            }else if(c>=0x88&&c<=0x8f){
                static const unsigned g[4]={512,2048,4096,8192},t[4]={256,512,2048,4096};
                int64_t *extra=c<0x8c?&s->gate_extra:&s->delta_extra;
                int64_t add=(int64_t)s->unit*(c<0x8c?g[c&3]:t[c&3]);
                if(*extra>INT64_MAX/2-add)goto malformed;
                *extra+=add;
                counted=0;
            }else if(c>=0xa0&&c<0xe0){
                if(!snd_seq_take(s,ram,&pos,1,&a))goto malformed;
                b=0;
                if(c<0xc0 && (!snd_seq_take(s,ram,&pos,1,&b)||b>127))goto malformed;
                if(!snd_seq_take(s,ram,&pos,1+((a>>7)&1),&d))goto malformed;
                emit(opaque,p,c,a&127,b);
            }else if(c>=0xe0&&c<0xf0){
                if(!snd_seq_take(s,ram,&pos,1,&a)||a>127||!snd_seq_take(s,ram,&pos,1,&d))goto malformed;
                emit(opaque,p,c,0,a);
            }else counted=0; /* documented no-ops80,85..87,9n,Fn */
            s->pos=pos;
            if(counted&&s->call_left){s->call_left--;if(!s->call_left)s->pos=s->call_ret;}
            if(d){
                int64_t duration=(int64_t)d*s->unit+s->delta_extra;
                if(duration>INT64_MAX/2)goto malformed;
                s->wait+=duration;s->delta_extra=0;
            }
            continue;
        malformed:
            snd_seq_fail(q,p,emit,opaque);break;
        }
    }
}
