# Build the camera bridge on the QNX Pi:   make -C qnx
# Camera headers come from the qnx-sf-base-dev package; if it isn't installed
# system-wide, they are bundled in ../include (copied from that package).
CC ?= cc
CFLAGS ?= -O2 -Wall -Wno-pragma-pack
INC := -I../include

pv_cam: pv_cam.c
	$(CC) $(CFLAGS) $(INC) -o $@ $< -lcamapi

clean:
	rm -f pv_cam
