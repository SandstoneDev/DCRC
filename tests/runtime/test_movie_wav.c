/* Synthetic RIFF/PCM/IMA fixtures only. Own code, MIT. */
#include "../../backend/movie_wav.h"
#include <stdio.h>
#include <string.h>
static unsigned checks,fails;
#define CK(x) do{checks++;if(!(x)){fails++;fprintf(stderr,"line%d %s\n",__LINE__,#x);}}while(0)
static uint8_t file[1024];static unsigned size;static int fail_read;
static void w16(unsigned a,unsigned v){file[a]=(uint8_t)v;file[a+1]=(uint8_t)(v>>8);}
static void w32(unsigned a,unsigned v){w16(a,v);w16(a+2,v>>16);}
static int64_t read_at(void *p,uint64_t off,void *dst,uint32_t n){(void)p;if(fail_read||off>size||n>size-off)return -1;memcpy(dst,file+off,n);return n;}
static void pcm(unsigned ch){
 memset(file,0,sizeof file);memcpy(file,"RIFF",4);memcpy(file+8,"WAVEfmt ",8);w32(16,16);
 w16(20,1);w16(22,ch);w32(24,44100);w32(28,44100*ch*2);w16(32,ch*2);w16(34,16);
 memcpy(file+36,"data",4);w32(40,ch*6);size=44+ch*6;w32(4,size-8);
 for(unsigned i=0;i<ch*3;i++)w16(44+2*i,(unsigned)(int16_t)(100+i*7));
}
static void ima(unsigned ch,unsigned fact){
 memset(file,0,sizeof file);memcpy(file,"RIFF",4);memcpy(file+8,"WAVEfmt ",8);w32(16,20);
 w16(20,0x11);w16(22,ch);w32(24,44100);w16(32,8*ch);w16(34,4);w16(36,2);w16(38,9);
 memcpy(file+40,"fact",4);w32(44,4);w32(48,fact);memcpy(file+52,"data",4);w32(56,8*ch);size=60+8*ch;w32(4,size-8);
 for(unsigned c=0;c<ch;c++){w16(60+4*c,(unsigned)(int16_t)(c?-1000:1000));for(unsigned j=0;j<4;j++)file[60+4*ch+4*c+j]=(uint8_t)(c?0x99:0x11);}
}
int main(void){MovieWav w;uint8_t stage[64];int16_t out[64];
 for(unsigned ch=1;ch<=2;ch++){
  pcm(ch);CK(movie_wav_open(&w,read_at,NULL,size,stage,sizeof stage)==0);CK(w.rate==44100&&w.total_frames==3);
  CK(movie_wav_read(&w,out,2)==2);CK(out[0]==100&&out[1]==(ch==2?107:100));
  CK(movie_wav_read(&w,out+4,8)==1);CK(out[4]==(ch==2?128:114));CK(movie_wav_read(&w,out,8)==0);
  ima(ch,9);CK(movie_wav_open(&w,read_at,NULL,size,stage,sizeof stage)==0);CK(w.total_frames==9);
  CK(movie_wav_read(&w,out,4)==4);CK(movie_wav_read(&w,out+8,8)==5);
  for(unsigned i=0;i<9;i++){CK(out[2*i]==1000+(int)i*2);CK(out[2*i+1]==(ch==2?-1000-(int)i*2:1000+(int)i*2));}
  CK(movie_wav_read(&w,out,1)==0);
  ima(ch,5);CK(movie_wav_open(&w,read_at,NULL,size,stage,sizeof stage)==0);CK(movie_wav_read(&w,out,12)==5);
 }
 pcm(2);CK(movie_wav_open(&w,read_at,NULL,size,NULL,64)<0);CK(movie_wav_open(&w,NULL,NULL,size,stage,64)<0);
 CK(movie_wav_open(&w,read_at,NULL,size,stage,3)<0);CK(movie_wav_open(&w,read_at,NULL,11,stage,64)<0);
 CK(movie_wav_open(&w,read_at,NULL,size-1,stage,64)<0);
 file[0]='X';CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);pcm(2);w32(16,UINT32_MAX);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 pcm(2);w16(22,3);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 pcm(2);w16(34,8);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 pcm(2);w16(32,3);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 pcm(2);w32(24,0);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 ima(2,9);w16(38,8);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 ima(2,99);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 pcm(2);w32(40,0);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)<0);
 pcm(2);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)==0);fail_read=1;CK(movie_wav_read(&w,out,2)<0);fail_read=0;
 pcm(1);CK(movie_wav_open(&w,read_at,NULL,size,stage,64)==0);CK(movie_wav_read(&w,out,0)==0&&w.frames_done==0);CK(movie_wav_read(&w,NULL,2)<0);
 printf("movie_wav %u checks %u failures\n",checks,fails);return fails?1:0;}
