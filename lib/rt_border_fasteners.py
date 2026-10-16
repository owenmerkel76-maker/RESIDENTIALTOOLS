# -*- coding: utf-8 -*-
"""Supported picture-frame fastening; model geometry, not product approval."""
import math
import rt_geometry as geo

EPS=1.e-7
MODES=('Manual / not modeled','Grooved/routed long edges + clips','Square-edge + schematic face screws')
WOOD_MARGIN=.375/12.0  # Schematic screw-center clearance, not a product specification.


def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def point(u,n,t,q): return (u[0]*t+n[0]*q,u[1]*t+n[1]*q)


def outline(board):
    return board.get('polygon') or [(board['start'],board['low']),(board['end'],board['low']),
                                    (board['end'],board['high']),(board['start'],board['high'])]


def axes(board):
    u=board.get('axis_vector',(0,1) if board.get('axis')=='B' else (1,0))
    return u,(-u[1],u[0])


def member_width(member,s):
    return member.get('section_width_in',s['joist_width_in'])/12.0


def member_outline(member,s):
    a,b=member['a'],member['b']; d=sub(b,a); length=math.hypot(*d)
    n=(-d[1]/length,d[0]/length); half=member_width(member,s)/2
    return [(a[0]+n[0]*half,a[1]+n[1]*half),(a[0]-n[0]*half,a[1]-n[1]*half),
            (b[0]-n[0]*half,b[1]-n[1]*half),(b[0]+n[0]*half,b[1]+n[1]*half)]


def support_at(p,members,s):
    for member in members:
        a,b=member['a'],member['b']; d=sub(b,a); length=math.hypot(*d)
        u=(d[0]/length,d[1]/length); n=(-u[1],u[0]); delta=sub(p,a)
        if (WOOD_MARGIN-EPS<=dot(delta,u)<=length-WOOD_MARGIN+EPS and
                abs(dot(delta,n))<=member_width(member,s)/2-WOOD_MARGIN+EPS):
            return member
    return None


def add_backing(p,u,members,s,commit=True):
    """Bridge a clear bay between parallel framing; never overlap existing solids."""
    n=(-u[1],u[0]); t=dot(p,u); candidates=[]; bw=s['block_width_in']/12.0
    for member in members:
        a,b=member['a'],member['b']; d=sub(b,a); length=math.hypot(*d)
        if abs(dot((d[0]/length,d[1]/length),u))<1-EPS: continue
        lo,hi=sorted((dot(a,u),dot(b,u)))
        if lo-EPS<=t-bw/2 and t+bw/2<=hi+EPS:
            candidates.append((dot(a,n),member_width(member,s)))
    q=dot(p,n)
    left=[c+w/2 for c,w in candidates if c<q-EPS]
    right=[c-w/2 for c,w in candidates if c>q+EPS]
    if not left or not right: return None
    lo,hi=max(left),min(right)
    if not lo+WOOD_MARGIN-EPS<=q<=hi-WOOD_MARGIN+EPS or hi-lo<.5/12: return None
    item=dict(key='FASTENER_BACKING_'+str(len(members)+1),role='BORDER_BACKING',
              a=point(u,n,t,lo),b=point(u,n,t,hi),section_width_in=s['block_width_in'],
              section_depth_in=s['block_depth_in'],fastener_backing=True)
    rectangle=member_outline(item,s)
    clipped=geo.intersection_parts(rectangle,geo.frame(s)['polygon'])
    if abs(sum(abs(geo.area(part)) for part in clipped)-abs(geo.area(rectangle)))>EPS: return None
    for member in members:
        overlap=geo.intersect_convex(rectangle,member_outline(member,s))
        if overlap and abs(geo.area(overlap))>EPS: return None
    if commit: members.append(item)
    return item


def sample_stations(lo,hi,step):
    if hi<lo+EPS: return []
    values=[lo]+[i*step for i in range(int(math.ceil(lo/step)),int(math.floor(hi/step))+1)
                 if lo+EPS<i*step<hi-EPS]+[hi]
    # Do not request nearly coincident cross-blocks at a board end and grid station.
    clean=[values[0]]
    for value in values[1:]:
        if value-clean[-1]>.25-EPS: clean.append(value)
    if hi-clean[-1]>.25: clean.append(hi)
    return clean


def line_supports(u,q,lo,hi,members,s,allow_backing=False):
    """Actual framing intersections plus distributed positions over parallel support."""
    n=(-u[1],u[0]); positions=[]; step=s['border_fastener_spacing_in']/12.0
    for member in list(members):
        a,b=member['a'],member['b']; d=sub(b,a); den=dot(d,n)
        if abs(den)>EPS:
            fraction=(q-dot(a,n))/den
            if -EPS<=fraction<=1+EPS:
                p=(a[0]+fraction*d[0],a[1]+fraction*d[1]); t=dot(p,u)
                if lo-EPS<=t<=hi+EPS and support_at(p,[member],s): positions.append((t,member))
        elif abs(dot(a,n)-q)<=member_width(member,s)/2-WOOD_MARGIN+EPS:
            first,last=sorted((dot(a,u),dot(b,u)))
            for t in sample_stations(max(lo,first+WOOD_MARGIN),min(hi,last-WOOD_MARGIN),step):
                positions.append((t,member))
    missing=[]
    if allow_backing:
        for t in sample_stations(lo,hi,step):
            p=point(u,n,t,q)
            if any(abs(t-existing)<step*.45 for existing,member in positions): continue
            member=support_at(p,members,s) or (add_backing(p,u,members,s) if s['border_add_backing'] else None)
            if member: positions.append((t,member))
            else: missing.append(p)
    unique={}
    for t,member in positions: unique.setdefault(round(t,7),(t,member))
    return sorted(unique.values(),key=lambda item:item[0]),missing


def apply_profiles(boards,footprint,gap):
    """Route inner border edges explicitly; keep exposed perimeter faces square."""
    boundary=list(zip(footprint,footprint[1:]+footprint[:1]))
    for board in boards:
        if board['role']!='BORDER':
            continue
        if board.get('border_kind')=='breaker' or board.get('course',1)>1:
            board['edge_mode']='both'; board['routed_edge']=True; continue
        u,n=axes(board); shape=outline(board); candidates=[]
        for a,b in zip(shape,shape[1:]+shape[:1]):
            if abs(dot(sub(b,a),n))<EPS:
                mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
                candidates.append((min(geo.edge_distance(mid,p,q) for p,q in boundary),dot(mid,n)))
        if len(candidates)!=2: raise ValueError('Cannot identify border long edges for '+board['key'])
        outer=min(candidates)[1]; low=min(value[1] for value in candidates)
        board['edge_mode']='right' if abs(outer-low)<EPS else 'left'
        board['routed_edge']=True
    borders=[edge for board in boards if board['role']=='BORDER' for edge in long_edges(board)]
    for board in boards:
        if board['role']=='BORDER' or board.get('edge_mode') not in ('left','right'): continue
        route=False
        for edge in long_edges(dict(board,edge_mode='both')):
            for border in borders:
                if dot(edge['n'],border['n'])>-1+EPS or abs(dot(sub(border['a'],edge['a']),edge['n'])-gap)>EPS: continue
                u=edge['u']; lo=max(min(dot(p,u) for p in (edge['a'],edge['b'])),min(dot(p,u) for p in (border['a'],border['b'])))
                hi=min(max(dot(p,u) for p in (edge['a'],edge['b'])),max(dot(p,u) for p in (border['a'],border['b'])))
                if hi>lo+EPS: route=True
        if route:
            if board['width_in']<=.5+EPS: raise ValueError('Grooved border mode needs more than a 1/2-inch field rip for two schematic grooves.')
            board['edge_mode']='both'; board['routed_edge']=True


def long_edges(board):
    u,n=axes(board); shape=geo.polygon(outline(board)); lo=min(dot(p,n) for p in shape)
    result=[]
    for a,b in zip(shape,shape[1:]+shape[:1]):
        d=sub(b,a); length=math.hypot(*d)
        if abs(dot(d,n))>EPS: continue  # End grain / miter is not a groove.
        side='left' if abs(dot(a,n)-lo)<EPS else 'right'
        if board.get('edge_mode','square') not in ('both',side): continue
        result.append(dict(board=board,u=u,n=(d[1]/length,-d[0]/length),a=a,b=b))
    return result


def border_clips(boards,members,s):
    edges=[edge for board in boards for edge in long_edges(board)]
    for index,edge in enumerate(edges): edge['index']=index
    border_edges=[edge for edge in edges if edge['board']['role']=='BORDER']
    clips=[]; missing=[]; seen=set(); gap=s['gap_in']/12.0; setback=s['border_end_setback_in']/12.0
    for first in border_edges:
        for second in edges:
            a,b=first['board'],second['board']
            if a is b or (b['role']=='BORDER' and first['index']>=second['index']): continue
            if dot(first['n'],second['n'])>-1+EPS: continue
            if abs(dot(sub(second['a'],first['a']),first['n'])-gap)>EPS: continue
            u=first['u']; n=(-u[1],u[0])
            lo=max(min(dot(p,u) for p in (first['a'],first['b'])),min(dot(p,u) for p in (second['a'],second['b'])))+setback
            hi=min(max(dot(p,u) for p in (first['a'],first['b'])),max(dot(p,u) for p in (second['a'],second['b'])))-setback
            if hi<=lo: continue
            q=dot(first['a'],n)+dot(first['n'],n)*gap/2
            positions,absent=line_supports(u,q,lo,hi,members,s,True); missing.extend(absent)
            for t,member in positions:
                p=point(u,n,t,q); key=(round(p[0],7),round(p[1],7))
                if key in seen: continue
                seen.add(key)
                clips.append(dict(key='BORDER_CLIP_'+str(len(clips)+1),role='CLIP',x=p[0],y=p[1],
                                  rotation_deg=math.degrees(math.atan2(u[1],u[0])),clip_kind='border',
                                  board_keys=[a['key'],b['key']],support_key=member['key'],support_role=member['role']))
    return clips,missing


def regular_face_stations(board,members,s,lo,hi):
    """One shared rail pattern; touching framing plies supply one station."""
    u,n=axes(board); poly=outline(board); q=(min(dot(p,n) for p in poly)+max(dot(p,n) for p in poly))/2
    values=[]
    for member in members:
        if member['role'] not in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT'): continue
        a,b=member['a'],member['b']; d=sub(b,a); den=dot(d,n)
        if abs(den)<EPS: continue
        p=(a[0]+d[0]*(q-dot(a,n))/den,a[1]+d[1]*(q-dot(a,n))/den)
        t=dot(p,u)
        if lo-EPS<=t<=hi+EPS: values.append(t)
    groups=[]
    for t in sorted(set(round(v,8) for v in values)):
        if groups and t-groups[-1][-1]<=s['joist_width_in']/12+EPS: groups[-1].append(t)
        else: groups.append([t])
    if groups:
        mid=(lo+hi)/2
        return [min(group,key=lambda v:abs(v-mid)) for group in groups]
    step=s['border_fastener_spacing_in']/12.0
    return [i*step for i in range(int(math.ceil(lo/step)),int(math.floor(hi/step))+1)]


def adjust_face_backing(p,members,s,screws):
    """Share one clear-bay block between close rows, without moving screw targets."""
    for member in members:
        if not member.get('face_backing'): continue
        d=sub(member['b'],member['a']); length=math.hypot(*d); u=(d[0]/length,d[1]/length); n=(-u[1],u[0])
        along=dot(sub(p,member['a']),u)
        if not WOOD_MARGIN<=along<=length-WOOD_MARGIN: continue
        targets=[p]+[(item['x'],item['y']) for item in screws if item['support_key']==member['key']]
        half=member_width(member,s)/2-WOOD_MARGIN
        lo=max(dot(target,n)-half for target in targets); hi=min(dot(target,n)+half for target in targets)
        if hi<lo-EPS: continue
        center=dot(member['a'],n); shift=min(max(center,lo),hi)-center
        if abs(shift)>member_width(member,s): continue
        moved=dict(member,a=(member['a'][0]+n[0]*shift,member['a'][1]+n[1]*shift),
                   b=(member['b'][0]+n[0]*shift,member['b'][1]+n[1]*shift))
        poly=member_outline(moved,s)
        if any(abs(geo.area(geo.intersect_convex(poly,member_outline(other,s))))>EPS for other in members if other is not member): continue
        clipped=geo.intersection_parts(poly,geo.frame(s)['polygon'])
        if abs(sum(abs(geo.area(part)) for part in clipped)-abs(geo.area(poly)))>EPS: continue
        member.update(moved)
        return member
    return None


def face_screws(boards,members,s,include_borders=True):
    screws=[]; missing=[]; seen=set()
    for board in sorted(boards,key=lambda b:0 if b['role']=='BORDER' else 1):
        border=board['role']=='BORDER'
        if border and not include_borders: continue
        if not border and (not s['field_edge_face_screws'] or board.get('edge_mode','both')=='both'): continue
        setback=s['border_end_setback_in' if border else 'field_face_setback_in']/12.0
        u,n=axes(board); shape=outline(board); low,high=min(dot(p,n) for p in shape),max(dot(p,n) for p in shape)
        if high-low<=2*setback+EPS:
            if not border: continue  # Narrow rips need an explicitly reviewed fastening detail.
            raise ValueError('Face screw setback leaves no room on '+board['key'])
        rails=[low+setback,high-setback] if border else ([low+setback] if board['edge_mode']=='right' else
               [high-setback] if board['edge_mode']=='left' else [low+setback,high-setback])
        regular=regular_face_stations(board,members,s,min(dot(p,u) for p in shape),max(dot(p,u) for p in shape))
        for q in rails:
            safe=geo.polygon(shape)
            for a,b in zip(geo.polygon(shape),geo.polygon(shape)[1:]+geo.polygon(shape)[:1]):
                d=sub(b,a); length=math.hypot(*d)
                if not border and abs(dot(d,n))<EPS: continue
                inward=(-d[1]/length,d[0]/length)
                safe=geo.clip_half(safe,inward,dot(a,inward)+setback)
                if not safe: break
            if not safe: continue
            cross=geo.polygon([(dot(p,n),dot(p,u)) for p in safe])
            for lo,hi in geo.vertical_spans(cross,q):
                # End/miter stations are mandatory. Do not substitute a nearby
                # intersection or add the old independent per-rail grid.
                targets=[lo,hi]+[t for t in regular if lo+max(2*setback,.25)<t<hi-max(2*setback,.25)]
                if not border:
                    for i,end in enumerate((lo,hi)):
                        nearby=[t for t in regular if lo-EPS<=t<=hi+EPS and abs(t-end)<2*setback]
                        if nearby: targets[i]=min(nearby,key=lambda t:abs(t-end))
                for t in sorted(set(round(t,8) for t in targets)):
                    p=point(u,n,t,q)
                    if min(geo.edge_distance(p,a,b) for a,b in zip(shape,shape[1:]+shape[:1]))<setback-EPS: continue
                    key=(round(p[0],7),round(p[1],7))
                    if key in seen: continue
                    member=support_at(p,members,s)
                    if member is None and s['border_add_backing']:
                        member=adjust_face_backing(p,members,s,screws)
                    if member is None and s['border_add_backing']:
                        choices=[item for item in (add_backing(p,u,members,s,False),add_backing(p,n,members,s,False)) if item]
                        if choices:
                            member=min(choices,key=lambda m:math.hypot(*sub(m['b'],m['a'])))
                            member['face_backing']=True
                            members.append(member)
                    if member is None: missing.append(p); continue
                    seen.add(key)
                    screws.append(dict(key=('BORDER_SCREW_' if border else 'FIELD_EDGE_SCREW_')+str(len(screws)+1),role='FACE_FASTENER',x=p[0],y=p[1],
                                       board_key=board['key'],support_key=member['key'],support_role=member['role'],
                                       face_kind='border' if border else 'field_edge',station_kind='end' if any(abs(t-v)<1.e-7 for v in targets[:2]) else 'regular',schematic=True))
    return screws,missing


def finish(planned):
    s=planned['settings']; mode=s['border_fastening']
    if not s['boards_enabled']: return planned
    if mode==MODES[1] and any(b['role']=='BORDER' for b in planned['boards']):
        apply_profiles(planned['boards'],geo.frame(s)['polygon'],s['gap_in']/12.0)
    if not s['clips_enabled']: return planned
    planned['warnings']=[warning for warning in planned['warnings']
                         if mode==MODES[0] or not warning.startswith('Square-edge picture-frame boards require separate perimeter/face fasteners.')]
    from rt_layout import clip_crossings,beam_ply_items
    # Recompute after routing field edges, and again after added backing.
    if mode==MODES[1]:
        borders,missing=border_clips(planned['boards'],planned['members'],s)
        clips=clip_crossings(planned['boards'],planned['members'],planned['rows'])
        seen=set((round(c['x'],7),round(c['y'],7)) for c in clips)
        planned['clips']=clips+[c for c in borders if (round(c['x'],7),round(c['y'],7)) not in seen]
        planned['counts']['border_clips']=sum(c.get('clip_kind')=='border' for c in planned['clips'])
        note='Grooved/routed border mode changes modeled inner-edge grooves. Confirm approved routing, clip compatibility and end setbacks. End grain, miters and exposed perimeter starter fastening are not supplied by these clips.'
        if not borders:
            planned['warnings'].append('No adjoining parallel border grooves exist in this layout. End-to-side or diagonal field terminations cannot use these hidden clips; choose face screws or a separately reviewed starter/termination detail.')
    else:
        missing=[]
        # New backing can also support field gaps that were previously missed.
        planned['clips']=clip_crossings(planned['boards'],planned['members'],planned['rows'])
        note='Face screws use explicit miter/end stations and a shared rail pattern, with one station per touching framing group. Flat first/last field-board edges receive a face row when enabled. Setbacks and product fastening remain user-verified.'
    screws,absent=face_screws(planned['boards'],planned['members'],s,mode==MODES[2])
    missing.extend(absent); planned['face_fasteners']=screws
    if s['field_edge_face_screws'] and any(b['role']=='BOARD' and b.get('edge_mode','both')!='both' and
            b.get('width_in',s['board_width_in'])<=2*s['field_face_setback_in']+EPS for b in planned['boards']):
        planned['warnings'].append('A field-edge rip is too narrow for the selected face setback. Its face row is omitted; revise the row layout/setback or provide a reviewed fastening detail.')
    if screws:
        planned['counts']['face_fasteners']=len(screws)
        planned['counts']['field_edge_screws']=sum(item['face_kind']=='field_edge' for item in screws)
    # New screw backing may also carry field clips; retain separately planned
    # border clips when the hidden-border method is selected.
    borders=[c for c in planned['clips'] if c.get('clip_kind')=='border']
    planned['clips']=clip_crossings(planned['boards'],planned['members'],planned['rows'])+borders
    planned['unsupported_border_fasteners']=[dict(x=p[0],y=p[1]) for p in missing]
    planned['counts']['clips']=len(planned['clips']); planned['counts']['framing']=len(planned['members'])
    planned['warnings'].append(note)
    if missing: planned['warnings'].append('{0} requested fastening stations lack modeled backing clearance. They are marked in the preview and excluded from counts; add/revise support before relying on a complete fastening layout.'.format(len(missing)))
    total=(len(planned['boards'])+len(planned['members'])+len(planned['clips'])+len(planned['hardware'])+
           len(planned.get('face_fasteners',[]))+len(planned.get('posts',[]))+
           sum(len(beam_ply_items(beam)) for beam in planned.get('beams',[])))
    if total>15000: raise ValueError('Prototype limit is 15,000 generated elements per layout, including border fasteners.')
    return planned
