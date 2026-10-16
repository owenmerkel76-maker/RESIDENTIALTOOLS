# -*- coding: utf-8 -*-
"""Connector-specific hand nail takeoff and individually modeled schematic nails.

Counts/specifications come from identified US product schedules. Native CAD hole
centers are preferred; a clearly flagged schematic grid is used if the CAD does
not expose the required holes. Neither representation establishes capacity.
"""
import math
import re
import rt_connector_geometry as g

LUS_SOURCE='https://www.strongtie.com/resources/product-installers-guide/lus-installation'
COUNT_SOURCE='https://www.strongtie.com/products/fastening-systems/technical-notes/sd-connector-screw-approved-connectors'
SHORT_SOURCE='https://www.strongtie.com/facemounthangers_engineeredwoodconnectors/hgus_hanger/p/hgus'
ANGLE_SOURCE='https://forms.iapmo.org/ues_reports/reports/er_0112.pdf'
TIE_SOURCE='https://www.strongtie.com/resources/product-installers-guide/h25a-installation'
TIE_SHORT_SOURCE='https://app.strongtie.com/rws'
FINISHES=('Unspecified - review','Hot-dip galvanized - verify compatibility','Stainless steel - verify grade/compatibility')
HEADER_MODES=('Single 2x header - reduced-load option','Full-length common nails - verify header thickness')


def model_name(name):
    text=name.upper()
    multiple=re.search(r'(LUS(?:24|26|28|210))[-_](\d+)(?![A-Z0-9])',text)
    if multiple and multiple.group(0).replace('_','-')!='LUS210-2':return None
    found=re.search(r'(?:^|[^A-Z0-9])(LUS210[-_]2|LUS210|LUS28|LUS26|LUS24|L90|L70|H2[._]?5A)(?:Z|HDG|SS)?(?:[^A-Z0-9]|$)',text)
    if not found:return None
    token=found.group(1)
    return 'H2.5A' if token.startswith('H2') else token.replace('_','-')


def schedule(name,s):
    model=model_name(name)
    if not model:return None
    rows=[]; notes=[]
    def row(group,count,diameter,length,source):
        rows.append(dict(application=group,count=count,diameter_in=diameter,length_in=length,source_url=source))
    if model.startswith('LUS'):
        counts={'LUS24':(4,2),'LUS26':(4,4),'LUS28':(6,4),'LUS210':(8,4),'LUS210-2':(8,6)}
        a,b=counts[model]; double=model.endswith('-2'); dia,length=(.162,3.5) if double else (.148,3)
        if s.get('hanger_nail_header',HEADER_MODES[0])==HEADER_MODES[0]:
            row('header face',a,.148,1.5,SHORT_SOURCE);row('joist double-shear',b,.148,3,SHORT_SOURCE)
            notes.append('Single-2x header nail option reduces published capacity; no allowable load is calculated. Verify the exact selected hanger and application.')
        else:row('header face',a,dia,length,LUS_SOURCE);row('joist double-shear',b,dia,length,LUS_SOURCE)
    elif model in ('L70','L90'):
        count=4 if model=='L70' else 5
        row('corner leg A',count,.148,1.5,ANGLE_SOURCE);row('corner leg B',count,.148,1.5,ANGLE_SOURCE)
        notes.append('ER-112 Table 7 requires review of wider-leg orientation, member thickness and load direction; these are quantities, not a connection approval.')
    elif model=='H2.5A':
        length=float(s.get('tie_nail_length_in',1.5))
        source=TIE_SOURCE if length==2.5 else TIE_SHORT_SOURCE
        row('joist tie tab',5,.131,length,source);row('beam tie tab',5,.131,length,source)
        if length==1.5:notes.append('H2.5A short-nail alternative has different published loads; verify the selected application and required uplift.')
    return dict(model=model,groups=rows,notes=notes,checked_on='2026-10-15',count_source=COUNT_SOURCE)


def required(items,s):
    total=0
    for item in items:
        spec=schedule(s.get('hardware_model_names',{}).get(item['role'],''),s)
        if spec:total+=sum(row['count'] for row in spec['groups'])
    return total


def regular(lo,hi,count):
    if hi<lo:lo=hi=(lo+hi)/2
    return [(lo+hi)/2] if count==1 else [lo+(hi-lo)*i/(count-1) for i in range(count)]


def rail_positions(rail,lo,hi,count):
    """Distribute a schematic pattern only along measured solid face intervals."""
    clearance=.08/12
    try:
        intervals=[]
        for pair in rail['intervals']:
            a,b=float(pair[0]),float(pair[1])
            if math.isnan(a) or math.isnan(b) or math.isinf(a) or math.isinf(b) or b<a:
                raise ValueError('Invalid face interval.')
            intervals.append((a,b))
        merged=[]
        for a,b in sorted(intervals):
            if merged and a<=merged[-1][1]+1.e-9:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
            else:merged.append((a,b))
        valid=[]
        for a,b in merged:
            a,b=max(a,lo)+clearance,min(b,hi)-clearance
            if b>a+1.e-9:valid.append((a,b))
        total=sum(b-a for a,b in valid)
        if total<1.e-9 or count<1:raise ValueError('No clear face interval.')
        result=[]
        for distance in regular(0,total,count):
            for a,b in valid:
                length=b-a
                if distance<=length+1.e-9:
                    result.append(a+min(distance,length));break
                distance-=length
            else:result.append(valid[-1][1])
        return result
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):
        raise ValueError('No safe measured mounting-face interval for schematic hurricane tie nails; review this family.')


def fallback(profile,group,count):
    bounds=profile['bounds']; margin=.5/12
    if group=='header face':
        half=profile['details']['clear_width_in']/24
        xs=[(bounds[0][0]-half)/2,(bounds[0][1]+half)/2]
        return [((xs[i%2],bounds[1][0],z),(0,-1,0)) for i,z in enumerate(
            [z for z in regular(max(bounds[2][0],0)+margin,bounds[2][1]-margin,count//2) for unused in (0,1)])]
    if group=='joist double-shear':
        half=profile['details']['clear_width_in']/24
        # Stagger the two sides vertically: opposing fallback nails must not
        # occupy the same 45-degree path through the joist center.
        result=[]
        for i,z in enumerate(regular(.6/12,bounds[2][1]-.6/12,count)):
            sign=-1 if i%2==0 else 1
            result.append(((sign*(half+.04/12),min(bounds[1][1]-.3/12,1.0/12),z),g.unit((-sign,-1,0))))
        return result
    first=group in ('corner leg A','joist tie tab'); normal=(1,0,0) if first else (0,1,0)
    side=1 if first else 0; plane=0 if first else 1
    lo,hi=bounds[2][0]+margin,bounds[2][1]-margin
    if profile['kind']=='tie':
        upper=group=='joist tie tab'; sign=profile['details']['upper_sign']*(1 if upper else -1)
        if sign>0:lo=max(lo,.35/12)
        else:hi=min(hi,-.35/12)
        if 'schematic_nail_rails' in profile['details']:
            rail=profile['details']['schematic_nail_rails'].get(group)
            if rail is None:raise ValueError('No measured mounting-face rail for schematic hurricane tie nails: '+group)
            try:
                contact,across=float(rail['plane']),float(rail['across'])
                if any(math.isnan(v) or math.isinf(v) for v in (contact,across)):
                    raise ValueError('Invalid face rail.')
            except (KeyError,TypeError,ValueError,OverflowError):
                raise ValueError('Invalid measured mounting-face rail for schematic hurricane tie nails: '+group)
            return [(tuple(contact if j==plane else across if j==side else z for j in range(3)),g.mul(normal,-1))
                    for z in rail_positions(rail,lo,hi,count)]
    across=(bounds[side][0]+bounds[side][1])/2
    return [(tuple(bounds[plane][0] if j==plane else across if j==side else z for j in range(3)),g.mul(normal,-1))
            for z in regular(lo,hi,count)]


def hole_positions(profile,group,count,diameter=0):
    candidates=[]
    for hole in profile.get('holes',[]):
        if hole.get('diameter_in',diameter)<diameter-.01:continue
        p,n=hole['center'],hole['normal']; direction=None
        if group=='header face' and abs(n[1])>.9 and abs(p[1])<.15/12:
            if abs(p[0])>profile['details']['clear_width_in']/24:direction=(0,-1,0)
        elif group=='joist double-shear' and abs(n[0])>.6 and p[1]>.15/12 and p[2]>.3/12:
            if abs(abs(p[0])-profile['details']['clear_width_in']/24)<.3/12:direction=g.unit((-1 if p[0]>0 else 1,-1,0))
        elif group in ('corner leg A','joist tie tab') and abs(n[0])>.9:
            if group!='joist tie tab' or p[2]*profile['details']['upper_sign']>0:direction=(-1,0,0)
        elif group in ('corner leg B','beam tie tab') and abs(n[1])>.9:
            if group!='beam tie tab' or p[2]*profile['details']['upper_sign']<0:direction=(0,-1,0)
        if direction is None:continue
        # Front/back CAD surfaces describe one through-hole.
        if any(g.size(g.sub(p,old[0]))<.13/12 for old in candidates):continue
        candidates.append((p,direction))
    return candidates if len(candidates)==count else None


def nail_items(profile,fit,item,name,s):
    spec=schedule(name,s)
    if spec is None:return [],['No verified nail schedule for '+name+'; connector nails are omitted, not estimated.']
    result=[];notes=list(spec['notes']);fallback_groups=[]
    for group in spec['groups']:
        points=hole_positions(profile,group['application'],group['count'],group['diameter_in']); measured=points is not None
        if not measured:points=fallback(profile,group['application'],group['count']);fallback_groups.append(group['application'])
        for p,direction in points:
            world=g.add(fit['datum'],g.rotate(p,((1,0,0),(0,1,0),(0,0,1)),fit['target']))
            axis=g.rotate(direction,((1,0,0),(0,1,0),(0,0,1)),fit['target'])
            product='{0:g} x {1:g} in hand connector nail | {2}'.format(group['diameter_in'],group['length_in'],s.get('hardware_nail_finish',FINISHES[0]))
            result.append(dict(key=item['key']+'_NAIL_'+str(len(result)+1),role='HARDWARE_NAIL',
                connector_key=item['key'],connector_model=spec['model'],application=group['application'],product=product,
                diameter_in=group['diameter_in'],nail_length_in=group['length_in'],head=world,direction=axis,
                source_url=group['source_url'],schematic=True,measured_hole=measured,
                finish=s.get('hardware_nail_finish',FINISHES[0])))
    if fallback_groups:notes.append(spec['model']+' CAD holes were unavailable/ambiguous for '+', '.join(fallback_groups)+'. Nails use a schematic mounting-face pattern; verify hole alignment in Revit.')
    return result,notes
