"""Summarize GPU event cadence; never equate software events with panel scanout."""
import statistics

NATIVE_NS = 1220 * 1956 * 1e9 / 143180000
MIN_NS = 1220 * 1957 * 1e9 / 143180000
MAX_NS = 1220 * 1989 * 1e9 / 143180000


def summarize(events):
    phases = {}
    for event in events:
        if event.get('event') == 'phase':
            phases[event['phase']] = {'requested_vrr': event['vrr_requested'],
                                      'expected_frames': event['frames'], 'flips': []}
        elif event.get('event') == 'flip':
            phases[event['phase']]['flips'].append(event)
    result = {}
    for phase, data in phases.items():
        frames = data['flips']
        periods, counts, late = [], {}, []
        for previous, current in zip(frames[3:], frames[4:]):
            step = (current['sequence'] - previous['sequence']) & 0xffffffff
            delta = current['event_ns'] - previous['event_ns']
            if not 1 <= step <= 16 or delta <= 0:
                raise ValueError('invalid event sequence or timestamp')
            periods.append(delta / step)
            counts[str(step)] = counts.get(str(step), 0) + 1
            late.append(max(0, current['submitted_ns'] - current['deadline_ns']) / 1000)
        summary = {'requested_vrr': data['requested_vrr'], 'frames': len(frames),
                   'complete': len(frames) == data['expected_frames'],
                   'vblank_step_counts': counts, 'intervals_analyzed': len(periods)}
        if periods:
            summary.update({
                'mean_vblank_period_us': statistics.mean(periods) / 1000,
                'vblank_period_us_range': [min(periods) / 1000, max(periods) / 1000],
                'within_2us_of_native_fraction': sum(abs(t - NATIVE_NS) <= 2000 for t in periods) / len(periods),
                'inside_candidate_window_with_2us_tolerance_fraction':
                    sum(MIN_NS - 2000 <= t <= MAX_NS + 2000 for t in periods) / len(periods),
                'submission_lateness_us_median': statistics.median(late),
                'submission_lateness_over_500us_count': sum(t > 500 for t in late),
            })
        result[str(phase)] = summary
    return {'schema': 1, 'phases': result,
            'restore_verified': any(e.get('event') == 'restore' and e.get('success') is True for e in events),
            'limits': ['GPU event timestamps and sequence counters only; not optical scanout',
                       'Dividing by vblank steps averages across missing flips',
                       'No automatic claim of working bridge or panel VRR']}
