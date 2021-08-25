// SPDX-License-Identifier: GPL-2.0-only
/*
 * Copyright (C) 2019-2020, Intel Corporation
 * Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
 */

#ifndef _WULT_TRACER_H_
#define _WULT_TRACER_H_

#include <linux/tracepoint.h>
#include <linux/trace_events.h>
#include "compat.h"
#include "cstates.h"

/* Name of the tracepoint we hook to. */
#define TRACEPOINT_NAME "cpu_idle"

/*
 * Name of the wult synthetic event which is used for sending measurement data
 * to user-space.
 */
#define WULT_TRACE_EVENT_NAME "wult_cpu_idle"

struct wult_info;

/*
 * Wult tracer information.
 */
struct wult_tracer_info {
	/* C-state information. */
	struct wult_cstates_info csinfo;
	/* Time before idle and after idle in TSC cycles or nanoseconds. */
	u64 tbi, tai;
	/* Interrupt time. */
	u64 tintr;
	/* Launch distance. */
	u64 ldist;
	/* The requested C-state index. */
	int req_cstate;
	/* SMI and NMI counters collected in 'before_idle()'. */
	u32 smi_bi, nmi_bi;
	/* SMI and NMI counters collected in the interrupt handler. */
	u32 smi_intr, nmi_intr;
	/* TSC values at the beginning and at the end of 'after_idle(). */
	u64 ai_tsc1, ai_tsc2;
	/* TSC values at the beginning and at the end of IRQ handler. */
	u64 intr_tsc1, intr_tsc2;
	/* 'true' if an event has been armed, but did not happen yet. */
	bool armed;
	/* 'true' if interrupts were disabled in 'after_idle()'. */
	bool irqs_disabled;
	/* 'true' if the armed event has happened. */
	bool event_happened;
	/* The tracepoint we hook to. */
	struct tracepoint *tp;
	/* The wult trace event file. */
	struct trace_event_file *event_file;
};

int wult_tracer_init(struct wult_info *wi);
void wult_tracer_exit(struct wult_info *wi);

int wult_tracer_enable(struct wult_info *wi);
void wult_tracer_disable(struct wult_info *wi);

int wult_tracer_arm_event(struct wult_info *wi, u64 *ldist);
int wult_tracer_send_data(struct wult_info *wi);

void wult_tracer_interrupt(struct wult_info *wi, u64 cyc);
#endif
