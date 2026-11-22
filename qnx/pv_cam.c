/*
 * pv_cam.c — QNX camera -> Python bridge.
 *
 * OpenCV's webcam reader can't open cameras on QNX, but QNX's own camera API
 * (camapi, the same one the QNX AI workshop uses) can. This tiny program opens
 * a camera with camapi and streams frames on stdout; python/qnx_camera.py
 * starts it and turns the frames into OpenCV images.
 *
 * Build on the Pi:  make -C qnx          (or see qnx/Makefile)
 * List cameras:     ./pv_cam -l
 * Stream:           ./pv_cam -u 1 -r 640x480 > frames.bin   (python does this)
 *
 * Stream format, repeated per frame (little-endian):
 *   char[4] "PVF1" | uint16 fmt | uint16 0 | uint32 width | uint32 height
 *   then the pixels, tightly packed (row padding removed):
 *     fmt 1 = NV12    width*height*3/2 bytes
 *     fmt 2 = YUYV    width*height*2 bytes
 *     fmt 3 = RGB8888 width*height*4 bytes (B,G,R,A in memory)
 *
 * Only the newest frame is sent: if Python is busy, older frames are dropped
 * instead of queuing up (same "newest wins" idea as the workshop node).
 */
#include <camera/camera_api.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { FMT_NV12 = 1, FMT_YUYV = 2, FMT_RGB8888 = 3 };

static pthread_mutex_t g_mx = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_cv = PTHREAD_COND_INITIALIZER;
static uint8_t *g_frame = NULL;   /* newest packed frame */
static size_t g_cap = 0, g_len = 0;
static uint32_t g_w = 0, g_h = 0, g_fmt = 0;
static unsigned long g_seq = 0;

static const char *ftname(camera_frametype_t t) {
    switch (t) {
        case CAMERA_FRAMETYPE_NV12: return "NV12";
        case CAMERA_FRAMETYPE_YCBYCR: return "YUYV";
        case CAMERA_FRAMETYPE_RGB8888: return "RGB8888";
        case CAMERA_FRAMETYPE_CBYCRY: return "UYVY";
        case CAMERA_FRAMETYPE_GRAY8: return "GRAY8";
        default: return "other";
    }
}

/* Copy `rows` rows of `row_bytes` from a strided source into dst. */
static void pack(uint8_t *dst, const uint8_t *src, uint32_t rows, uint32_t row_bytes,
                 uint32_t stride) {
    for (uint32_t r = 0; r < rows; r++)
        memcpy(dst + (size_t)r * row_bytes, src + (size_t)r * stride, row_bytes);
}

static void on_frame(camera_handle_t h, camera_buffer_t *buf, void *arg) {
    (void)h;
    (void)arg;
    uint32_t w, ht, fmt;
    size_t need;
    if (buf->frametype == CAMERA_FRAMETYPE_NV12) {
        w = buf->framedesc.nv12.width;
        ht = buf->framedesc.nv12.height;
        fmt = FMT_NV12;
        need = (size_t)w * ht * 3 / 2;
    } else if (buf->frametype == CAMERA_FRAMETYPE_YCBYCR) {
        w = buf->framedesc.ycbycr.width;
        ht = buf->framedesc.ycbycr.height;
        fmt = FMT_YUYV;
        need = (size_t)w * ht * 2;
    } else if (buf->frametype == CAMERA_FRAMETYPE_RGB8888) {
        w = buf->framedesc.rgb8888.width;
        ht = buf->framedesc.rgb8888.height;
        fmt = FMT_RGB8888;
        need = (size_t)w * ht * 4;
    } else {
        static int warned = 0;
        if (!warned++) fprintf(stderr, "pv_cam: unsupported frame type %d\n", (int)buf->frametype);
        return;
    }

    pthread_mutex_lock(&g_mx);
    if (g_cap < need) {
        uint8_t *p = realloc(g_frame, need);
        if (!p) {
            pthread_mutex_unlock(&g_mx);
            return;
        }
        g_frame = p;
        g_cap = need;
    }
    if (fmt == FMT_NV12) {
        const camera_frame_nv12_t *d = &buf->framedesc.nv12;
        pack(g_frame, buf->framebuf, ht, w, d->stride);
        pack(g_frame + (size_t)w * ht, buf->framebuf + d->uv_offset, ht / 2, w,
             (uint32_t)d->uv_stride);
    } else if (fmt == FMT_YUYV) {
        pack(g_frame, buf->framebuf, ht, w * 2, buf->framedesc.ycbycr.stride);
    } else {
        pack(g_frame, buf->framebuf, ht, w * 4, buf->framedesc.rgb8888.stride);
    }
    g_len = need;
    g_w = w;
    g_h = ht;
    g_fmt = fmt;
    g_seq++;
    pthread_cond_signal(&g_cv);
    pthread_mutex_unlock(&g_mx);
}

static int list_units(void) {
    camera_unit_t units[16];
    unsigned int n = 0;
    if (camera_get_supported_cameras(16, &n, units) != CAMERA_EOK || n == 0) {
        fprintf(stderr, "pv_cam: no cameras found (is the sensor service running?)\n");
        return 1;
    }
    for (unsigned int i = 0; i < n; i++) {
        camera_handle_t h = CAMERA_HANDLE_INVALID;
        int err = camera_open(units[i], CAMERA_MODE_RO, &h);
        if (err != CAMERA_EOK) {
            printf("unit %d: cannot open (%s)\n", (int)units[i], strerror(err));
            continue;
        }
        camera_frametype_t ft[16];
        uint32_t nft = 0;
        camera_get_supported_vf_frame_types(h, 16, &nft, ft);
        camera_res_t res[32];
        uint32_t nres = 0;
        camera_get_supported_vf_resolutions(h, 32, &nres, res);
        printf("unit %d: formats", (int)units[i]);
        for (uint32_t k = 0; k < nft; k++) printf(" %s", ftname(ft[k]));
        printf(" | sizes");
        for (uint32_t k = 0; k < nres && k < 12; k++) printf(" %ux%u", res[k].width, res[k].height);
        printf("\n");
        camera_close(h);
    }
    return 0;
}

static void usage(void) {
    fprintf(stderr,
            "usage: pv_cam -l               list cameras\n"
            "       pv_cam [-u unit] [-r WxH] stream frames to stdout\n");
}

int main(int argc, char **argv) {
    int unit = -1, want_w = 640, want_h = 480, opt;
    while ((opt = getopt(argc, argv, "lu:r:h")) != -1) {
        if (opt == 'l') return list_units();
        if (opt == 'u') unit = atoi(optarg);
        else if (opt == 'r') {
            if (sscanf(optarg, "%dx%d", &want_w, &want_h) != 2) { usage(); return 2; }
        } else { usage(); return 2; }
    }
    signal(SIGPIPE, SIG_IGN); /* Python went away -> fwrite fails -> we exit */

    camera_unit_t units[16];
    unsigned int n = 0;
    if (camera_get_supported_cameras(16, &n, units) != CAMERA_EOK || n == 0) {
        fprintf(stderr, "pv_cam: no cameras found\n");
        return 1;
    }

    camera_handle_t h = CAMERA_HANDLE_INVALID;
    for (unsigned int i = 0; i < n; i++) {
        if (unit >= 0 && (int)units[i] != unit) continue;
        if (camera_open(units[i], CAMERA_MODE_RO, &h) != CAMERA_EOK) continue;

        camera_frametype_t ft[16];
        uint32_t nft = 0;
        camera_get_supported_vf_frame_types(h, 16, &nft, ft);
        camera_frametype_t chosen = CAMERA_FRAMETYPE_UNSPECIFIED;
        for (uint32_t k = 0; k < nft; k++) {  /* NV12 > YUYV > RGB8888 */
            if (ft[k] == CAMERA_FRAMETYPE_NV12) { chosen = ft[k]; break; }
            if (ft[k] == CAMERA_FRAMETYPE_YCBYCR) chosen = ft[k];
            if (ft[k] == CAMERA_FRAMETYPE_RGB8888 && chosen == CAMERA_FRAMETYPE_UNSPECIFIED) chosen = ft[k];
        }
        if (chosen == CAMERA_FRAMETYPE_UNSPECIFIED) {
            camera_close(h);
            h = CAMERA_HANDLE_INVALID;
            continue;
        }
        camera_set_vf_property(h, CAMERA_IMGPROP_FORMAT, chosen);
        camera_set_vf_property(h, CAMERA_IMGPROP_CREATEWINDOW, 0);

        /* Closest offered size to the request (fewest pixels away). */
        camera_res_t res[32];
        uint32_t nres = 0;
        if (camera_get_supported_vf_resolutions(h, 32, &nres, res) == CAMERA_EOK && nres > 0) {
            uint32_t best = 0;
            long target = (long)want_w * want_h, bd = -1;
            for (uint32_t k = 0; k < nres; k++) {
                long d = labs((long)res[k].width * res[k].height - target);
                if (bd < 0 || d < bd) bd = d, best = k;
            }
            camera_set_vf_property(h, CAMERA_IMGPROP_WIDTH, res[best].width,
                                   CAMERA_IMGPROP_HEIGHT, res[best].height);
        }
        int err = camera_start_viewfinder(h, on_frame, NULL, NULL);
        if (err != CAMERA_EOK) {
            fprintf(stderr, "pv_cam: unit %d start failed (%s)\n", (int)units[i], strerror(err));
            camera_close(h);
            h = CAMERA_HANDLE_INVALID;
            continue;
        }
        unsigned int w = 0, ht = 0;
        camera_get_vf_property(h, CAMERA_IMGPROP_WIDTH, &w, CAMERA_IMGPROP_HEIGHT, &ht);
        fprintf(stderr, "pv_cam: streaming unit %d %ux%u %s\n", (int)units[i], w, ht, ftname(chosen));
        break;
    }
    if (h == CAMERA_HANDLE_INVALID) {
        fprintf(stderr, "pv_cam: could not start any camera%s\n", unit >= 0 ? " with that unit" : "");
        return 1;
    }

    uint8_t *out = NULL;
    size_t out_cap = 0;
    unsigned long last = 0;
    for (;;) {
        pthread_mutex_lock(&g_mx);
        while (g_seq == last) pthread_cond_wait(&g_cv, &g_mx);
        last = g_seq;
        if (out_cap < g_len) {
            out = realloc(out, g_len);
            out_cap = g_len;
        }
        memcpy(out, g_frame, g_len);
        size_t len = g_len;
        uint32_t hdr[4];
        memcpy(&hdr[0], "PVF1", 4);
        hdr[1] = g_fmt;  /* uint16 fmt + uint16 0, little-endian */
        hdr[2] = g_w;
        hdr[3] = g_h;
        pthread_mutex_unlock(&g_mx);

        if (fwrite(hdr, sizeof hdr, 1, stdout) != 1 || fwrite(out, len, 1, stdout) != 1 ||
            fflush(stdout) != 0)
            break; /* reader closed the pipe */
    }
    camera_stop_viewfinder(h);
    camera_close(h);
    return 0;
}
