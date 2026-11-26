"""Compare source-following and fixed-60-Hz hypotheses without fitting VRR data."""
from .optical_alignment import fit_clock,residual

NATIVE_US=1220*1956/143180000*1e6


def expected_flips():
    result=[(-1,i,120<=i<240) for i in range(360)]
    for phase,count in ((0,360),(1,720),(2,360)):
        result.extend((phase,i,bool(i%2)) for i in range(1,count+1))
    return result


def expected_edges(flips):
    expected=expected_flips()
    if len(flips)!=len(expected) or [f['ordinal'] for f in flips]!=list(range(1800)):
        raise ValueError('Incomplete optical A/B sequence')
    if [(f['phase'],f['frame'],f['marker_lit']) for f in flips]!=expected:
        raise ValueError('Unexpected optical A/B stimulus')
    for a,b in zip(flips,flips[1:]):
        step=(b['sequence']-a['sequence'])&0xffffffff
        dt_us=(b['event_ns']-a['event_ns'])/1000
        if dt_us<=0 or not 1<=step<0x80000000:
            raise ValueError('Invalid source event/sequence progression')
        if a['phase']==b['phase']:
            if step>3:raise ValueError('Unexpected within-phase source hold')
        else:
            # Atomic VRR-property commits can hold the old content for several
            # vblanks. Keep the entire hold and check its clock consistency;
            # it is not a missing optical sample or an ordinary paced flip.
            maximum_us=1220*1989/143180000*1e6
            if not NATIVE_US-2<=dt_us/step<=maximum_us+2:
                raise ValueError('Phase-boundary sequence/time inconsistency')
    base=flips[0]['event_ns']
    return [{'ordinal':b['ordinal'],'phase':b['phase'],'frame':b['frame'],
             'state':int(b['marker_lit']),'source_us':(b['event_ns']-base)/1000,
             'sequence':b['sequence']}
            for a,b in zip(flips,flips[1:]) if a['marker_lit']!=b['marker_lit']]


def compare(flips,observed):
    expected=expected_edges(flips)
    if len(observed)!=1442 or len(expected)!=1442:
        raise ValueError('Expected 1442 qualified edges; extra/missing edges need manual diagnosis')
    if any(a['state']!=b['state'] for a,b in zip(expected,observed)):
        raise ValueError('Optical polarity sequence mismatch')
    if any(b['time_us']<=a['time_us'] for a,b in zip(observed,observed[1:])):
        raise ValueError('Nonmonotonic optical sequence')
    if abs(observed[1]['time_us']-observed[0]['time_us']-(expected[1]['source_us']-expected[0]['source_us']))>2000:
        raise ValueError('Preamble timing mismatch')
    pairs=[dict(a,**b) for a,b in zip(expected,observed)]
    training=[p for p in pairs if p['phase']==0]
    model=fit_clock(training)
    if abs(model['scale_error_ppm'])>1000 or max(abs(residual(p,model)) for p in training)>2000:
        raise ValueError('Initial fixed control failed alignment')
    # Constant-refresh countermodel: keep the initial control's clock and
    # phase fixed, then measure distance to that unbroken native-period grid.
    period=model['scale']*NATIVE_US
    anchor=training[0]['source_us']
    origin=model['offset_us']+model['scale']*anchor
    for p in pairs:
        p['source_residual_us']=residual(p,model)
        adjusted=p['time_us']-model['rising_relative_to_falling_us']*p['state']
        p['fixed_native_grid_residual_us']=(adjusted-origin+period/2)%period-period/2
    holds=[{'from_phase':a['phase'],'to_phase':b['phase'],
            'source_interval_us':(b['event_ns']-a['event_ns'])/1000,
            'vblank_steps':(b['sequence']-a['sequence'])&0xffffffff}
           for a,b in zip(flips,flips[1:]) if a['phase']!=b['phase']]
    return {'model':model,'training_phase':0,'fixed_grid_period_us':period,'pairs':pairs,
            'phase_boundary_holds':holds,
            'limitations':[
                'No fit uses the VRR-requested or final fixed phases.',
                'The fixed countermodel is an uninterrupted native-60-Hz grid, not every possible buffered or fixed-rate behavior.',
                'A short single-location content-update recording does not prove panel refresh behavior or a safe operating range.',
                'Polarity response and electrical noise can change with content cadence; no automatic VRR verdict.'
            ]}
