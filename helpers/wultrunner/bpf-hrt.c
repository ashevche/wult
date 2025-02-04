// SPDX-License-Identifier: GPL-2.0
/*
 * Copyright(c) 2022 Intel Corporation.
 * Author: Tero Kristo <tero.kristo@linux.intel.com>
 */

#include <uapi/linux/bpf.h>
#include <uapi/linux/time.h>
#include <linux/version.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

#include "wultrunner.h"

#ifdef DEBUG
#define debug_printk(fmt, ...) bpf_printk("bpf_hrt DBG: " fmt, ##__VA_ARGS__)
#else
#define debug_printk(fmt, ...) do { } while (0)
#endif

#define warn_printk(fmt, ...) bpf_printk("bpf_hrt WRN: " fmt, ##__VA_ARGS__)

/*
 * Below is hardcoded, as including the corresponding linux header would
 * break BPF object building.
 */
#define PWR_EVENT_EXIT -1

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, 4096);
} events SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
	__uint(key_size, sizeof(int));
	__uint(value_size, sizeof(u32));
	__uint(max_entries, WULTRUNNER_NUM_PERF_COUNTERS);
} perf SEC(".maps");

struct timer_elem {
	struct bpf_timer t;
};

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, int);
	__type(value, struct timer_elem);
} timers SEC(".maps");

static int min_t;
static int max_t;
static struct bpf_event data;
static u64 ltime;
static u32 ldist;
static bool timer_armed;

static u64 perf_counters[WULTRUNNER_NUM_PERF_COUNTERS];

const u32 linux_version_code = LINUX_VERSION_CODE;

/*
 * These are used as configuration variables passed in by userspace.
 * volatile modifier is needed, as otherwise the compiler assumes these
 * to be constants and does not recognize the changes done by the tool;
 * effectively hardcoding the values as all zeroes in the compiled BPF
 * code.
 */
const volatile u32 cpu_num;

static u64 bpf_hrt_read_tsc(void)
{
	u64 count;
	s64 err;

	count = bpf_perf_event_read(&perf, MSR_TSC);
	err = (s64)count;

	/*
	 * Check if reading TSC has failed for some reason. This is not
	 * a fatal condition and the next read will typically succeed
	 * unless we are executing the read from bad context.
	 */
	if (err >= -512 && err < 0) {
		warn_printk("TSC read error: %d", err);
		count = 0;
	}

	return count;
}

static void bpf_hrt_ping_cpu(void)
{
	struct bpf_event *e;

	e = bpf_ringbuf_reserve(&events, 1, 0);
	if (!e) {
		warn_printk("ringbuf overflow, ping discarded");
		return;
	}

	e->type = HRT_EVENT_PING;

	bpf_ringbuf_submit(e, 0);
}

static void bpf_hrt_send_event(void)
{
	struct bpf_event *e;
	int i;

	/*
	 * Check that we have all required data in place, these
	 * may be populated in different order if we are running
	 * an idle state with interrupts enabled/disabled
	 */
	if (!data.tai || !data.tintr || !data.tbi ||
	    data.tai <= data.ltime || data.tbi >= data.ltime)
		return;

	e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
	if (!e) {
		/*
		 * A failure here is not fatal, current event will
		 * be discarded but next one will succeed if userspace
		 * has cleared up the buffer. Just in case, send a
		 * message to userspace about overflow situation.
		 */
		warn_printk("ringbuf overflow, event discarded");
		return;
	}

	__builtin_memcpy(e, &data, sizeof(*e));

	e->type = HRT_EVENT_DATA;

	/* Index 0 is TSC, skip it here */
	for (i = 1; i < WULTRUNNER_NUM_PERF_COUNTERS; i++)
		e->perf_counters[i] = perf_counters[i];

	bpf_ringbuf_submit(e, 0);

	data.tbi = 0;
	data.tai = 0;
	data.tintr = 0;
}

int bpf_hrt_kick_timer(void)
{
	int key = 0;
	struct bpf_timer *timer;
	int ret;
	int cpu_id = bpf_get_smp_processor_id();

	if (data.tbi || timer_armed)
		return 0;

	timer = bpf_map_lookup_elem(&timers, &key);
	if (!timer)
		/*
		 * This check will never fail, but must be in place to
		 * satisfy BPF verifier.
		 */
		return 0;

	ldist = bpf_get_prandom_u32();
	ldist = ldist % (max_t - min_t);
	ldist = ldist + min_t;

	debug_printk("kick_timer: ldist=%d, cpu=%d", ldist, cpu_id);

	ltime = bpf_ktime_get_boot_ns() + ldist;

	bpf_timer_start(timer, ldist, 0);

	timer_armed = true;

	return ret;
}

static void bpf_hrt_snapshot_perf_vars(bool exit)
{
	int i;
	u64 count, *ptr;
	int key;
	s64 err;

	if (exit)
		perf_counters[MSR_MPERF] =
			bpf_perf_event_read(&perf, MSR_MPERF) -
			perf_counters[MSR_MPERF];

	/* Skip TSC events 0..1 (TSC/MPERF) */
	for (i = 2; i < WULTRUNNER_NUM_PERF_COUNTERS; i++) {
		count = bpf_perf_event_read(&perf, i);
		err = (s64)count;

		/* Exit if no entry found */
		if (err < 0 && err >= -22)
			break;

		if (exit)
			perf_counters[i] = count - perf_counters[i];
		else
			perf_counters[i] = count;
	}

	if (!exit)
		perf_counters[MSR_MPERF] =
			bpf_perf_event_read(&perf, MSR_MPERF);
}

static int bpf_hrt_timer_cb(void *map, int *key, struct bpf_timer *timer)
{
	int cpu_id = bpf_get_smp_processor_id();

	debug_printk("timer_cb, cpu=%d", cpu_id);

	timer_armed = false;

	if (data.tbi) {
		data.tintr = bpf_ktime_get_boot_ns();
		data.intrts1 = data.tintr;
		data.intrts2 = data.tintr;
		data.ldist = ldist;
		data.ltime = ltime;
		/*
		 * TAI stamp missing means we are executing a POLL
		 * state waiting for a scheduling event to happen.
		 * Send a dummy ping message to userspace so that
		 * cpuidle knows to wake-up also, otherwise we only
		 * end up executing the interrupt handler.
		 */
		if (!data.tai)
			bpf_hrt_ping_cpu();
	}

	bpf_hrt_send_event();
	bpf_hrt_kick_timer();

	return 0;
}

SEC("syscall")
int bpf_hrt_start_timer(struct bpf_args *args)
{
	int key = 0;
	struct bpf_timer *timer;

	min_t = args->min_t;
	max_t = args->max_t;

	timer = bpf_map_lookup_elem(&timers, &key);
	if (!timer)
		return -2; /* ENOENT */

	bpf_timer_init(timer, &timers, CLOCK_MONOTONIC);

	bpf_timer_set_callback(timer, bpf_hrt_timer_cb);

	bpf_hrt_kick_timer();

	return 0;
}

SEC("tp_btf/cpu_idle")
int BPF_PROG(bpf_hrt_cpu_idle, unsigned int cstate, unsigned int cpu_id)
{
	int idx = cpu_id;
	u64 t;

	if (cpu_id != cpu_num)
		return 0;

	if (cstate == PWR_EVENT_EXIT) {
		t = bpf_ktime_get_boot_ns();

		if (data.tintr || t >= ltime) {
			data.tai = t;
			data.aits1 = data.tai;

			bpf_hrt_snapshot_perf_vars(true);

			data.aic = bpf_hrt_read_tsc();

			data.aits2 = bpf_ktime_get_boot_ns();
		} else {
			data.tbi = 0;
		}

		debug_printk("exit cpu_idle, state=%d, idle_time=%lu",
			     data.req_cstate, data.tai - data.tbi);

		bpf_hrt_send_event();
		bpf_hrt_kick_timer();
	} else {
		debug_printk("enter cpu_idle, state=%d", cstate);
		data.req_cstate = cstate;
		idx = cstate;

		t = bpf_ktime_get_boot_ns();

		data.bic = bpf_hrt_read_tsc();
		bpf_hrt_snapshot_perf_vars(false);

		data.tbi = bpf_ktime_get_boot_ns();
		if (data.tbi > ltime)
			data.tbi = 0;

		data.tai = 0;
	}

	return 0;
}

char _license[] SEC("license") = "GPL";
