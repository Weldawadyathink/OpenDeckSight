"""Fixed-pattern optical alignment with one clock scale and polarity offset.

No dropped-edge recovery, per-frame time warping or interval outlier removal.
The known two-second preamble fixes the sequence, including slower/faster phases.
"""
import statistics


def qualify_edges(observed, quiet_us=100):
    """Qualify a transition only after no further crossing for quiet_us.

    Use the last crossing's time, without adding the qualification delay.
    Preserve every raw crossing and the full settling-time span. This cannot
    distinguish emission ringing from electrical noise and is deliberately
    unsuitable for diagnosing light pulses shorter than quiet_us.
    """
    if not 0 < quiet_us <= 1000: raise ValueError('Invalid qualification time')
    if not observed: return [], []
    groups=[]
    for edge in observed:
        if groups and edge['time_us']<=groups[-1][-1]['time_us']:
            raise ValueError('Nonmonotonic optical edges')
        if groups and edge['time_us']-groups[-1][-1]['time_us']<quiet_us:
            groups[-1].append(edge)
        else: groups.append([edge])
    state=1-observed[0]['state']
    qualified=[];details=[]
    for group in groups:
        changed=group[-1]['state']!=state
        span=group[-1]['time_us']-group[0]['time_us']
        details.append({'crossings':group, 'net_transition':changed, 'span_us':span})
        if changed:
            qualified.append(dict(group[-1],settling_span_us=span,
                                  first_crossing_us=group[0]['time_us'],raw_crossings=len(group)))
            state=group[-1]['state']
    return qualified,details


def marker(frame):
    if frame < 120: return 0
    if frame < 240: return 1
    if frame < 360: return 0
    if frame < 480: return ((frame-360)//2) % 2
    if frame < 960: return (frame-480) % 2
    return 0


def source_edges(flips):
    if [f['frame'] for f in flips] != list(range(1080)):
        raise ValueError('Incomplete fixed stimulus')
    if any(f['marker_lit'] != bool(marker(f['frame'])) for f in flips):
        raise ValueError('Unexpected optical stimulus')
    base = flips[0]['event_ns']
    return [{'frame':b['frame'], 'state':int(b['marker_lit']),
             'source_us':(b['event_ns']-base)/1000}
            for a,b in zip(flips,flips[1:]) if a['marker_lit'] != b['marker_lit']]


def fit_clock(pairs):
    """Least squares y = offset + scale*x + rising_bias*state.

    Center within each polarity to solve the shared slope, then recover
    intercepts. This avoids a numerical dependency and large timestamp offsets.
    """
    groups = [[p for p in pairs if p['state']==state] for state in (0,1)]
    if any(len(g)<2 for g in groups): raise ValueError('Insufficient edge polarities')
    means = [(statistics.mean(p['source_us'] for p in g),
              statistics.mean(p['time_us'] for p in g)) for g in groups]
    numerator = denominator = 0.0
    for g,(mx,my) in zip(groups,means):
        numerator += sum((p['source_us']-mx)*(p['time_us']-my) for p in g)
        denominator += sum((p['source_us']-mx)**2 for p in g)
    if denominator <= 0: raise ValueError('No timing span')
    scale = numerator / denominator
    intercepts = [my-scale*mx for mx,my in means]
    return {'offset_us':intercepts[0], 'scale':scale,
            'scale_error_ppm':(scale-1)*1e6,
            'rising_relative_to_falling_us':intercepts[1]-intercepts[0]}


def residual(pair, model):
    predicted = (model['offset_us'] + model['scale']*pair['source_us'] +
                 model['rising_relative_to_falling_us']*pair['state'])
    return pair['time_us']-predicted


def align(expected, observed, tolerance_us=2000):
    """Require a unique, contiguous full sequence; retain all outside edges.

    The first half of the every-frame segment calibrates the model. The
    second half, preamble and slower segment do not influence that fit.
    2 ms is an association guard, not the claimed measurement precision.
    """
    if not 0 < tolerance_us < 8000: raise ValueError('Invalid association tolerance')
    if any(b['time_us']<=a['time_us'] for a,b in zip(observed,observed[1:])):
        raise ValueError('Nonmonotonic optical edges')
    if len(expected)!=542: raise ValueError('Unexpected source edge count')
    matches=[]
    preamble_us=expected[1]['source_us']-expected[0]['source_us']
    for start in range(len(observed)-len(expected)+1):
        if abs(observed[start+1]['time_us']-observed[start]['time_us']-preamble_us)>10000:
            continue
        selected=observed[start:start+len(expected)]
        if any(a['state']!=b['state'] for a,b in zip(expected,selected)): continue
        pairs=[dict(a,**b) for a,b in zip(expected,selected)]
        training=[p for p in pairs if 480<=p['frame']<720]
        model=fit_clock(training)
        if abs(model['scale_error_ppm'])>1000: continue
        errors=[residual(p,model) for p in pairs]
        if max(abs(e) for e in errors)>tolerance_us: continue
        matches.append((start,pairs,model,errors))
    if len(matches)!=1:
        raise ValueError('Expected one complete optical sequence; found '+str(len(matches)))
    start,pairs,model,errors=matches[0]
    for p,error in zip(pairs,errors): p['residual_us']=error
    return {'model':model, 'pairs':pairs, 'first_observed_index':start,
            'outside_edges':observed[:start]+observed[start+len(expected):],
            'training_frame_range':[480,720], 'association_tolerance_us':tolerance_us}
