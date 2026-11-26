/* GP26 only; native USB; no wireless driver, external output or Deck access. */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <inttypes.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "pico/bootrom.h"
#include "hardware/adc.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"
#include "protocol.h"

#define RATE 100000u
#define RING_SAMPLES 16384u
#define BLOCK_SAMPLES 2048u
#define MAX_SAMPLES (RATE*60u)
static uint16_t ring[RING_SAMPLES] __attribute__((aligned(32768)));
static uint16_t block[BLOCK_SAMPLES];
static int dma_channel;

static void packet(unsigned type,uint32_t seq,uint64_t index,const void *data,uint32_t bytes)
{
    struct ods_header h={.magic=ODS_MAGIC,.version=ODS_VERSION,.type=type,
        .sequence=seq,.bytes=bytes,.sample_index=index,.payload_crc=ods_crc32(data,bytes)};
    h.header_crc=ods_crc32(&h,offsetof(struct ods_header,header_crc));
    stdio_put_string((const char *)&h,sizeof(h),false,false);
    stdio_put_string(data,bytes,false,false);
}

static uint32_t produced(void)
{
    return UINT32_MAX-dma_channel_hw_addr(dma_channel)->transfer_count;
}

static uint32_t hardware_flags(void)
{
    uint32_t flags=0,fcs=adc_hw->fcs,cs=adc_hw->cs;
    if (fcs&ADC_FCS_OVER_BITS) flags|=ODS_FIFO_OVER;
    if (fcs&ADC_FCS_UNDER_BITS) flags|=ODS_FIFO_UNDER;
    if (cs&(ADC_CS_ERR_BITS|ADC_CS_ERR_STICKY_BITS)) flags|=ODS_ADC_ERROR;
    if (dma_channel_hw_addr(dma_channel)->ctrl_trig&DMA_CH0_CTRL_TRIG_AHB_ERROR_BITS) flags|=ODS_DMA_ERROR;
    return flags;
}

static void stop_capture(struct ods_end *end)
{
    adc_run(false);
    while (!(adc_hw->cs&ADC_CS_READY_BITS)) tight_loop_contents();
    end->stopped_us=time_us_64();
    end->produced=produced();
    end->fcs=adc_hw->fcs;
    end->cs=adc_hw->cs;
    end->dma_ctrl=dma_channel_hw_addr(dma_channel)->ctrl_trig;
    end->flags|=hardware_flags();
    dma_channel_abort(dma_channel);
    adc_fifo_drain();
    adc_fifo_setup(false,false,1,false,false);
}

static void capture(uint32_t requested)
{
    struct ods_end end={0};
    uint32_t seq=0;
    adc_run(false);
    adc_select_input(0);
    adc_set_round_robin(0);
    adc_fifo_drain();
    adc_set_clkdiv((float)(clock_get_hz(clk_adc)/RATE-1));
    adc_hw->cs|=ADC_CS_ERR_STICKY_BITS;
    adc_fifo_setup(true,true,1,true,false);
    adc_hw->fcs|=ADC_FCS_OVER_BITS|ADC_FCS_UNDER_BITS;
    dma_channel_config config=dma_channel_get_default_config(dma_channel);
    channel_config_set_transfer_data_size(&config,DMA_SIZE_16);
    channel_config_set_read_increment(&config,false);
    channel_config_set_write_increment(&config,true);
    channel_config_set_dreq(&config,DREQ_ADC);
    channel_config_set_ring(&config,true,15); /* 32 KiB wrap */
    dma_channel_configure(dma_channel,&config,ring,&adc_hw->fifo,UINT32_MAX,true);
    struct ods_begin begin={RATE,requested,26,BLOCK_SAMPLES,RING_SAMPLES,
        clock_get_hz(clk_adc),adc_hw->div,1};
    packet(ODS_BEGIN,0,0,&begin,sizeof(begin));
    end.started_us=time_us_64();
    adc_run(true);
    bool running=true;
    while (end.sent<requested) {
        if (!stdio_usb_connected()) { end.flags|=ODS_DISCONNECT; break; }
        if (getchar_timeout_us(0)=='!') { end.flags|=ODS_ABORT; break; }
        end.flags|=hardware_flags();
        if (end.flags) break;
        uint32_t available=produced()-end.sent;
        if (available>end.max_backlog) end.max_backlog=available;
        if (available>RING_SAMPLES) { end.flags|=ODS_RING_OVER; break; }
        uint32_t n=requested-end.sent;
        if (n>BLOCK_SAMPLES) n=BLOCK_SAMPLES;
        if (available<n) {
            if (time_us_64()-end.started_us>(uint64_t)requested*1000000/RATE+3000000u) {
                end.flags|=ODS_TIMEOUT; break;
            }
            tight_loop_contents();
            continue;
        }
        /* Blocks divide the ring, so this copy never crosses its wrap. Check
         * again afterward: an overwritten copy is rejected, never transmitted. */
        __compiler_memory_barrier();
        memcpy(block,&ring[end.sent&(RING_SAMPLES-1)],n*sizeof(uint16_t));
        __compiler_memory_barrier();
        available=produced()-end.sent;
        if (available>end.max_backlog) end.max_backlog=available;
        if (available>RING_SAMPLES) { end.flags|=ODS_RING_OVER; break; }
        for (unsigned i=0;i<n;i++) if (block[i]&0xf000u) end.flags|=ODS_ADC_ERROR;
        if (end.flags) break;
        if (end.sent+n==requested) { stop_capture(&end); running=false; }
        packet(ODS_DATA,seq++,end.sent,block,n*sizeof(uint16_t));
        end.sent+=n;
    }
    if (running) stop_capture(&end);
    if (stdio_usb_connected()) packet(ODS_END,seq,end.sent,&end,sizeof(end));
}

int main(void)
{
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb,false);
    adc_init();
    adc_gpio_init(26);
    adc_select_input(0);
    dma_channel=dma_claim_unused_channel(true);
    char line[80];
    unsigned used=0;
    while (true) {
        int c=getchar_timeout_us(100000);
        if (c<0) continue;
        if (c=='\r') continue;
        if (c!='\n') {
            if (used<sizeof(line)-1) line[used++]=(char)c;
            else used=0;
            continue;
        }
        line[used]=0; used=0;
        if (!strcmp(line,"INFO")) {
            printf("{\"firmware\":\"ods-optical-capture\",\"revision\":1,\"protocol\":1,\"gpio\":26,\"sample_rate\":%u,\"max_samples\":%u}\n",RATE,MAX_SAMPLES);
        } else if (!strcmp(line,"BOOT")) {
            stdio_flush(); reset_usb_boot(0,0);
        } else if (!strncmp(line,"CAPTURE ",8)) {
            char *tail;
            unsigned long n=strtoul(line+8,&tail,10);
            if (*tail || n<1 || n>MAX_SAMPLES) puts("ERROR invalid sample count");
            else capture((uint32_t)n);
        } else if (*line) puts("ERROR unknown command");
    }
}
