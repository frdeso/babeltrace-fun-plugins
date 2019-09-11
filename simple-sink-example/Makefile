CFLAGS = -g3 -O0 -Werror -Wall
CC ?= gcc
LDFLAGS=-lbabeltrace2

.PHONY: all
all: simple-sink-example

simple-sink-example: simple-sink-example.c
	$(CC) -o $@ $< $(CFLAGS) $(LDFLAGS)

.PHONY: clean run
clean:
	rm -f simple-sink-example

run: simple-sink-example
	dmesg | ./simple-sink-example

