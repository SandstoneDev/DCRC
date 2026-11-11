/* Synthetic own SMSB/SMPB only: no game bytes. */
#include "snd_sequence.h"
static unsigned unit_events,unit_on,unit_off,unit_program;
static void unit_emit(void *opaque,unsigned port,unsigned st,unsigned d1,unsigned d2) {
    (void)opaque;(void)d1;(void)d2;assert(port<SND_SEQ_PORTS);unit_events++;
    if((st&0xf0)==0x90)unit_on++;
    if((st&0xf0)==0x80)unit_off++;
    if((st&0xf0)==0xc0)unit_program++;
}
static void put32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i)); }
static unsigned synthetic_bank(uint8_t *ram,const uint8_t *events,unsigned n) {
    unsigned size=32+n+4;memset(ram,0,512);
    put32(ram,0x42534d53);put32(ram+4,1);put32(ram+8,size);put32(ram+12,1);put32(ram+16,20);
    put32(ram+20,0x44534d53);put32(ram+24,136);put32(ram+28,800);
    memcpy(ram+32,events,n);put32(ram+size-4,0x42444e45);return size;
}
static void parser_checks(void) {
    uint8_t ram[512];snd_sequencer q={0};unsigned size;
    const uint8_t note[]={0x00,60,127,8,8,0x83};
    size=synthetic_bank(ram,note,sizeof note);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));
    snd_seq_tick(&q,ram,unit_emit,0);assert(unit_on==1&&unit_off==0);
    for(unsigned i=0;i<10;i++)snd_seq_tick(&q,ram,unit_emit,0);
    assert(unit_off==1&&!snd_seq_busy(&q));
    /* Invalid bounds and invalid arithmetic cannot read outside the bank. */
    assert(!snd_seq_start(&q,0,ram,sizeof ram,500,size,0,unit_emit,0));
    assert(!snd_seq_start(&q,6,ram,sizeof ram,0,size,0,unit_emit,0));
    assert(!snd_seq_start(&q,0,ram,sizeof ram,0,size,1,unit_emit,0));
    put32(ram+16,0xfffffff0);assert(!snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));
    const uint8_t truncated[]={0x70,60};size=synthetic_bank(ram,truncated,sizeof truncated);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(q.port[0].fault&&!q.port[0].active);
    const uint8_t zero_tempo[]={0x84,0,0,0};size=synthetic_bank(ram,zero_tempo,sizeof zero_tempo);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(q.port[0].fault);
    const uint8_t forever[]={0x82,0,0,0x82,0,0};size=synthetic_bank(ram,forever,sizeof forever);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(q.port[0].fault);
    const uint8_t loop[]={0x82,1,0,0xc0,3,0,0x82,0,0,0x83};size=synthetic_bank(ram,loop,sizeof loop);unit_program=0;
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(!q.port[0].fault&&unit_program==2);
    const uint8_t call[]={0x81,0,17,1,0x83,0xc0,4,0};size=synthetic_bank(ram,call,sizeof call);unit_program=0;
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(!q.port[0].fault&&unit_program==1);
    const uint8_t badcall[]={0x81,0xff,0xff,1};size=synthetic_bank(ram,badcall,sizeof badcall);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(q.port[0].fault);
    const uint8_t noops[]={0x80,0x85,0x86,0x87,0x90,0x9f,0xf0,0xff,0x83};size=synthetic_bank(ram,noops,sizeof noops);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(!q.port[0].fault&&!q.port[0].active);
    const uint8_t prefixed_call[]={0x81,0,17,1,0x83,0x85,0x88,0xc0,4,0};size=synthetic_bank(ram,prefixed_call,sizeof prefixed_call);unit_program=0;
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(!q.port[0].fault&&unit_program==1);
    /* Stop/replacement only release notes owned by the selected sequence port. */
    size=synthetic_bank(ram,note,sizeof note);unit_on=unit_off=0;
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));assert(snd_seq_start(&q,1,ram,sizeof ram,0,size,0,unit_emit,0));
    snd_seq_tick(&q,ram,unit_emit,0);assert(unit_on==2);snd_seq_stop(&q,0,unit_emit,0);assert(unit_off==1&&q.port[1].active);
    assert(snd_seq_start(&q,1,ram,sizeof ram,0,size,0,unit_emit,0));assert(unit_off==2);
    /* A full32-bit gate and repeated extension must never overflow signed time. */
    const uint8_t overflow[]={0x8b,0x60,60,127,255,255,255,255,1,0x83};
    size=synthetic_bank(ram,overflow,sizeof overflow);put32(ram+24,0x7fffffff);put32(ram+28,16);
    assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));snd_seq_tick(&q,ram,unit_emit,0);assert(q.port[0].fault);
    unsigned rng=0x124359u;
    for(unsigned trial=0;trial<10000;trial++){
        uint8_t bytes[96];unsigned length=1+trial%sizeof bytes;
        for(unsigned i=0;i<length;i++){rng=rng*1664525u+1013904223u;bytes[i]=(uint8_t)(rng>>24);}
        size=synthetic_bank(ram,bytes,length);memset(&q,0,sizeof q);
        assert(snd_seq_start(&q,0,ram,sizeof ram,0,size,0,unit_emit,0));
        for(unsigned tick=0;tick<12;tick++)snd_seq_tick(&q,ram,unit_emit,0);
    }
}
static void make_seq_fixture(void) {
    const uint32_t base=0x100, B=base+0x100, Q=base+0xa00;
    memset(guest,0,sizeof guest);
    guest32(base,0x544c4d53);guest32(base+8,2);
    guest32(base+32,0x42504d53);guest32(base+36,0);guest32(base+40,0x10000);guest32(base+44,0x800);guest32(base+48,0x100);guest32(base+52,0x800);
    guest32(base+64,0x42534d53);guest32(base+68,0);guest32(base+72,0x20000);guest32(base+76,0x1000);guest32(base+80,0xa00);guest32(base+84,64);
    guest32(B,0x42504d53);guest32(B+16,0x20);guest32(B+20,1);guest32(B+0x20,0x40);guest32(B+0x40,0x60);guest32(B+0x60,1);guest32(B+0x64,0x80);
    guest32(B+0x80,0x02000200);
    guest32(B+0x84,0x01000000);guest32(B+0x88,0x001f001f);guest32(B+0x90,0x0f100000);
    guest[B+0x80+36]=0;guest[B+0x80+37]=127;guest[B+0x80+38]=60;
    for(int i=0;i<256;i++){int16_t v=(int16_t)((i&8)?12000:-12000);guest[B+0x200+2*i]=(uint8_t)v;guest[B+0x201+2*i]=(uint8_t)(v>>8);}
    guest32(Q,0x42534d53);guest32(Q+4,1);guest32(Q+8,64);guest32(Q+12,1);guest32(Q+16,20);
    guest32(Q+20,0x44534d53);guest32(Q+24,136);guest32(Q+28,800);
    const uint8_t events[]={0xb0,32,0,0,0xc0,0,0,0xb0,7,127,0,0x00,60,127,32,32,0x83};
    memcpy(guest+Q+32,events,sizeof events);guest32(Q+60,0x42444e45);
    sh4_ctx c={0};c.r[4]=0;sdk_8c6434e0(&c);uint32_t h=hle_rd32(0);assert(h);
    c.r[4]=h;c.r[5]=base;c.r[6]=0;sdk_8c643624(&c);c.r[4]=h;sdk_8c643970(&c);assert(c.r[0]==0);
    c.r[4]=h;sdk_8c6435bc(&c);
}
static void direct_note(void) {
    snd_host_cmd(SND_CMD_MIDI,0,0xb0,32,0,0);snd_host_cmd(SND_CMD_MIDI,0,0xc0,0,0,0);
    snd_host_cmd(SND_CMD_MIDI,0,0xb0,7,127,0);snd_host_cmd(SND_CMD_MIDI,0,0x90,60,127,0);
}
static void direct_isolation(void) {
    int16_t reference[1470],result[1470];
    snd_host_init();make_seq_fixture();direct_note();
    for(unsigned i=0;i<3;i++)snd_core_render(core,reference,735);
    snd_host_init();make_seq_fixture();direct_note();
    sh4_ctx c={0};c.r[4]=0x5d000102;sdk_8c643b08(&c);
    snd_core_render(core,result,735); /* sequence really began on its own port */
    c.r[4]=0x5d000102;c.r[5]=(uint32_t)-128;c.r[6]=0;sdk_8c643d88(&c);
    snd_host_cmd(SND_CMD_MIDI,2,0xb0,10,0,0); /* sequence-port pan */
    c.r[4]=0x5d000102;sdk_8c643e08(&c);
    c.r[4]=0x5d000120;c.r[5]=0;c.r[6]=0;sdk_8c643b08(&c);assert(c.r[0]==0xffffffffu);
    c.r[4]=0x5d000120;sdk_8c643e08(&c); /* invalid handles must not alias port0 */
    c.r[4]=0x5d000100;c.r[5]=(uint32_t)-128;sdk_8c643d88(&c); /* direct-port API remains unchanged */
    for(unsigned i=0;i<2;i++)snd_core_render(core,result,735);
    assert(!memcmp(reference,result,sizeof result));
}
static void sequence_clock_checks(void) {
    int16_t first[2000],chunked[2000];sh4_ctx c={0};
    snd_host_init();make_seq_fixture();c.r[4]=0x5d000102;sdk_8c643b08(&c);
    snd_core_render(core,first,176);for(unsigned i=0;i<352;i++)assert(first[i]==0);
    snd_core_render(core,first,1);assert(first[0]==0&&first[1]==0);
    snd_core_render(core,first,1);assert(first[0]!=0||first[1]!=0);
    snd_host_init();make_seq_fixture();c.r[4]=0x5d000102;c.r[5]=0;c.r[6]=0;sdk_8c643b08(&c);
    snd_core_render(core,first,1000);
    snd_host_init();make_seq_fixture();c.r[4]=0x5d000102;c.r[5]=0;c.r[6]=0;sdk_8c643b08(&c);
    unsigned done=0;while(done<1000){unsigned n=1000-done;if(n>37)n=37;snd_core_render(core,chunked+2*done,n);done+=n;}
    assert(!memcmp(first,chunked,sizeof first));
    /* Exactly250 driver ticks fit44100 samples, even while no sequence runs. */
    snd_host_init();make_seq_fixture();for(unsigned i=0;i<60;i++)snd_core_render(core,first,735);
    c.r[4]=0x5d000102;c.r[5]=0;c.r[6]=0;sdk_8c643b08(&c);
    snd_core_render(core,first,177);for(unsigned i=0;i<354;i++)assert(first[i]==0);
    snd_core_render(core,first,1);assert(first[0]!=0||first[1]!=0);
}
int main(void) {
#ifdef DIRECT_ONLY
    snd_host_init();make_seq_fixture();
    snd_host_cmd(SND_CMD_MIDI,0,0xb0,32,0,0);snd_host_cmd(SND_CMD_MIDI,0,0xc0,0,0,0);
    snd_host_cmd(SND_CMD_MIDI,0,0xb0,7,127,0);snd_host_cmd(SND_CMD_MIDI,0,0x90,60,127,0);
    uint64_t hash=1469598103934665603ull;int16_t pcm[1470];
    for(unsigned b=0;b<40;b++){
        if(b==20)snd_host_cmd(SND_CMD_MIDI,0,0x80,60,0,0);
        snd_core_render(core,pcm,735);
        for(unsigned i=0;i<1470;i++){hash^=(uint16_t)pcm[i];hash*=1099511628211ull;}
    }
    printf("DIRECT_PCM %016llx\n",(unsigned long long)hash);return 0;
#else
    parser_checks();
    direct_isolation();
    sequence_clock_checks();
    snd_host_init();make_seq_fixture();
    sh4_ctx c={0};c.r[4]=0x5d000102;c.r[5]=0;c.r[6]=0;c.r[7]=0;sdk_8c643b08(&c);
    int16_t out[2*735];int heard=0;
    for(int block=0;block<6;block++){snd_core_render(core,out,735);for(unsigned i=0;i<1470;i++)heard|=out[i]!=0;}
    if(!heard){fprintf(stderr,"FAIL sequence outputs audible PCM\n");return 1;}
    c.r[4]=0x5d000102;sdk_8c643e08(&c);
    for(int block=0;block<3;block++)snd_core_render(core,out,735);
    for(unsigned i=0;i<1470;i++)assert(out[i]==0);
    /* A sequence bank rewrite invalidates active parser and gated notes. */
    c.r[4]=0x5d000102;c.r[5]=0;c.r[6]=0;sdk_8c643b08(&c);snd_core_render(core,out,735);
    snd_host_cmd(SND_CMD_BANK_CHANGED,0,0,0,0x20000,64);
    for(int b=0;b<3;b++)snd_core_render(core,out,735);
    for(unsigned i=0;i<1470;i++)assert(out[i]==0);
    puts("PASS synthetic parser bounds/timing/call/loop/isolation plus actual SD->SMSB->core PCM and stop");return 0;
#endif
}
