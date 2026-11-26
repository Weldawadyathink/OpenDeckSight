#ifndef ODS_OPTICAL_PROTOCOL_H
#define ODS_OPTICAL_PROTOCOL_H
#include <stdint.h>
#include <stddef.h>

#define ODS_MAGIC 0x4353444fu /* ODSC, little endian */
#define ODS_VERSION 1u
enum { ODS_BEGIN=1, ODS_DATA=2, ODS_END=3 };
enum {
    ODS_FIFO_OVER=1, ODS_FIFO_UNDER=2, ODS_ADC_ERROR=4, ODS_DMA_ERROR=8,
    ODS_RING_OVER=16, ODS_DISCONNECT=32, ODS_ABORT=64, ODS_TIMEOUT=128
};
struct __attribute__((packed)) ods_header {
    uint32_t magic;
    uint16_t version, type;
    uint32_t sequence, bytes;
    uint64_t sample_index;
    uint32_t payload_crc, header_crc;
};
struct __attribute__((packed)) ods_begin {
    uint32_t rate, requested, gpio, block_samples, ring_samples;
    uint32_t adc_clock, adc_div, firmware_revision;
};
struct __attribute__((packed)) ods_end {
    uint32_t flags, sent, produced, fcs, cs, dma_ctrl, max_backlog;
    uint64_t started_us, stopped_us;
};
_Static_assert(sizeof(struct ods_header)==32,"header layout");
_Static_assert(sizeof(struct ods_begin)==32,"begin layout");
_Static_assert(sizeof(struct ods_end)==44,"end layout");

static uint32_t ods_crc32(const void *data,size_t length)
{
    const uint8_t *p=data;
    uint32_t crc=0xffffffffu;
    while (length--) {
        crc^=*p++;
        for (unsigned bit=0;bit<8;bit++)
            crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
    }
    return crc^0xffffffffu;
}
#endif
