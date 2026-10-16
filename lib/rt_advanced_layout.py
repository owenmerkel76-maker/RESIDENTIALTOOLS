# -*- coding: utf-8 -*-
"""Stock-limited convex deck/angle/border prototype; all geometry remains explicit."""
import math
import rt_geometry as geo
from rt_layout import EPS, add_staggered_blocking, board_rows, stations, joint_stations, hanger_groups, boards_by_row, beam_ply_items, set_beam_splices, clip_crossings, corner_connections, tie_member_sides


def inside(point, poly):
    return geo.point_inside(point,poly)


def clear_span(poly,x,width):
    spans=clear_spans(poly,x,width)
    return spans[0] if len(spans)==1 else None


def clear_spans(poly,x,width):
    samples=[x-width/2,x+width/2]
    samples.extend(p[0] for p in poly if x-width/2<p[0]<x+width/2)
    result=geo.vertical_spans(poly,samples[0])
    for sample in samples[1:]:
        current=geo.vertical_spans(poly,sample)
        result=[(max(a,c),min(b,d)) for a,b in result for c,d in current if min(b,d)-max(a,c)>.5/12]
    return result


def plan(s):
    if abs(s['board_angle_deg'])>EPS and not s.get('joists_follow_angle'):
        return fixed_framing(s)
    return rotated_plan(s)


def breaker_centers_for(field,s):
    """Offsets use the framing board-axis coordinate, not a bounding rectangle fill."""
    if not s['seam_border'] or not s['boards_enabled']: return []
    low,high=min(p[0] for p in field),max(p[0] for p in field)
    text=s.get('breaker_positions_ft','')
    if text:
        try: centers=sorted(float(value.strip()) for value in text.split(','))
        except (ValueError,OverflowError):
            raise ValueError('Enter breaker centers as comma-separated feet, such as 10 or 10,20.')
    else:
        segments=int(math.ceil((high-low)/s['stock_ft']))
        centers=[low+(high-low)*i/segments for i in range(1,segments)]
    margin=s['board_width_in']/24+1.5*s['joist_width_in']/12+s['butt_gap_in']/12
    for i,x in enumerate(centers):
        if math.isnan(x) or math.isinf(x) or not low+margin<x<high-margin:
            raise ValueError('Breaker centers must lie inside the decking field with room for edge/backing members.')
        if i and x-centers[i-1]<2*margin:
            raise ValueError('Breaker backing groups overlap; separate the selected centers.')
        if not clear_spans(field,x,s['board_width_in']/12):
            raise ValueError('A breaker center does not cross a usable full-width decking region.')
    return centers


def breaker_boards(field,centers,s):
    boards,seams=[],[]; half=s['board_width_in']/24
    low,high=min(p[1] for p in field),max(p[1] for p in field)
    for index,x in enumerate(centers):
        outlines=geo.intersection_parts([(x-half,low),(x+half,low),(x+half,high),(x-half,high)],field)
        for region,outline in enumerate(outlines):
            start,end=min(p[1] for p in outline),max(p[1] for p in outline)
            pieces=int(math.ceil((end-start)/s['stock_ft']))
            cuts=[start+(end-start)*i/pieces for i in range(pieces+1)]
            for piece,(a,b) in enumerate(zip(cuts,cuts[1:])):
                a+=s['butt_gap_in']/24 if piece else 0
                b-=s['butt_gap_in']/24 if piece<pieces-1 else 0
                for part,shape in enumerate(geo.intersection_parts([(x-half,a),(x+half,a),(x+half,b),(x-half,b)],outline)):
                    boards.append(dict(key='BREAKER_{0}_{1}_{2}_{3}'.format(index+1,region+1,piece+1,part+1),
                                       role='BORDER',border_kind='breaker',polygon=shape,width_in=s['board_width_in'],
                                       length_ft=max(p[1] for p in shape)-min(p[1] for p in shape),
                                       axis='B',edge_mode='square',breaker_center_ft=x))
            for y in cuts[1:-1]:
                seams.append(dict(a=(x-half,y),b=(x+half,y),breaker=True))
    return boards,seams


def rotated_plan(s):
    f=geo.frame(s); poly=f['polygon']; run,span=f['run'],f['span']
    try:
        geo.convex(poly); is_convex=True
    except ValueError:
        is_convex=False
    jw=s['joist_width_in']/12.0
    courses=s['border_courses'] if s['picture_frame'] and s['boards_enabled'] else 0
    inset=courses*(s['board_width_in']+s['gap_in'])/12.0
    field=geo.inset(poly,inset) if inset else poly
    if min(max(p[0] for p in field)-min(p[0] for p in field),
           max(p[1] for p in field)-min(p[1] for p in field))<1:
        raise ValueError('Border courses leave less than one foot of decking field.')
    boards,seams,rows,joints=[],[],[],set()
    breaker_centers=breaker_centers_for(field,s)
    breaker_parts,breaker_seams=breaker_boards(field,breaker_centers,s)
    boards.extend(breaker_parts)
    base=stations(run,jw,s['spacing_in']/12.0)
    if s['boards_enabled']:
        y0,y1=min(p[1] for p in field),max(p[1] for p in field)
        rows=[(a+y0,b+y0,mode) for a,b,mode in board_rows(y1-y0,s['board_width_in'],s['gap_in'],s['board_row_layout'])]
        for row,(low,high,mode) in enumerate(rows):
            strips=geo.intersection_parts([(0,low),(run,low),(run,high),(0,high)],field)
            for x in breaker_centers:
                half=(s['board_width_in']+2*s['butt_gap_in'])/24.0
                strips=[part for strip in strips for a,b in ((0,x-half),(x+half,run))
                        for part in geo.intersection_parts([(a,low),(b,low),(b,high),(a,high)],strip)]
            for region,strip in enumerate(strips):
                start,end=min(p[0] for p in strip),max(p[0] for p in strip)
                phase=2*s['spacing_in']/12 if s['stagger'] and row%2 else 0
                cuts=[] if s.get('_ignore_field_seams') else joint_stations(start,end,base,s['stock_ft'],phase)
                joints.update(cuts)
                limits=[start]+cuts+[end]
                for piece,(a,b) in enumerate(zip(limits,limits[1:])):
                    a+=s['butt_gap_in']/24 if piece else 0
                    b-=s['butt_gap_in']/24 if piece<len(limits)-2 else 0
                    outlines=geo.intersection_parts([(a,low),(b,low),(b,high),(a,high)],strip)
                    for part,outline in enumerate(outlines):
                        if outline and b-a>.5/12:
                            boards.append(dict(key='BOARD_{0}_{1}_{2}_{3}'.format(row+1,region+1,piece+1,part+1),role='BOARD',
                                               row=row,start=a,end=b,low=low,high=high,polygon=outline,
                                               width_in=(high-low)*12,length_ft=b-a,edge_mode=mode))
        if courses:
            border_grid=[x for x in base if not any(abs(x-center)<s['board_width_in']/24+1.5*jw+EPS
                                                  for center in breaker_centers)]
            borders,seams=geo.border_pieces(poly,s['board_width_in']/12,s['gap_in']/12,
                                           courses,s['stock_ft'],s['butt_gap_in']/12,s['stagger'],border_grid)
            boards.extend(borders)
    seams.extend(breaker_seams)
    required=[]
    if s.get('_ignore_field_seams'):
        joints=set(s.get('_forced_joint_centers',[]))
    rectangle=all(abs(poly[(i+1)%len(poly)][0]-p[0])<EPS or
                  abs(poly[(i+1)%len(poly)][1]-p[1])<EPS for i,p in enumerate(poly))
    # Border seams parallel to field boards get full-span paired joists rather
    # than short unsupported pieces across the rim.
    if rectangle:
        for seam in seams:
            if abs(seam['a'][0]-seam['b'][0])<EPS:
                joints.add(round(seam['a'][0],8))
    for x in sorted(joints):
        required.extend([(x-jw/2,'JOINT_SUPPORT'),(x+jw/2,'JOINT_SUPPORT')])
    # One central joist carries the breaker; touching pairs carry its edges
    # and adjacent field-board ends. No unsupported field butt seam remains.
    for x in breaker_centers:
        required.append((x,'JOIST'))
        for edge in (x-s['board_width_in']/24.0,x+s['board_width_in']/24.0):
            required.extend([(edge-jw/2,'JOINT_SUPPORT'),(edge+jw/2,'JOINT_SUPPORT')])
            joints.add(edge)
    # On a rectangle aligned with boards, straddle the inner border/field seam.
    if courses and rectangle:
        edge=inset-s['gap_in']/24
        if s['double_border_joists']:
            for x in (edge,run-edge):
                required.extend([(x-jw/2,'BORDER_SUPPORT'),(x+jw/2,'BORDER_SUPPORT')])
        else:
            for x in (inset,run-inset):
                required.append((x+jw/2 if x<run/2 else x-jw/2,'BORDER_SUPPORT'))
    supports=[(x,'JOIST') for x in base if not any(abs(x-y)<jw-EPS for y,role in required)] + required
    supports.sort(); clean=[]
    for x,role in supports:
        if clean and x-clean[-1][0]<jw-EPS:
            raise ValueError('Required support members overlap; revise dimensions, spacing or board seams.')
        clean.append((x,role))
    # Inserting a custom support group can displace a regular station. Fill
    # the resulting wider bay instead of exceeding the chosen O.C. spacing.
    filled=[]; maximum=s['spacing_in']/12.0
    for i,item in enumerate(clean):
        if i:
            left=clean[i-1][0]; distance=item[0]-left
            bays=max(1,int(math.ceil((distance-EPS)/maximum)))
            if distance/bays<jw-EPS:
                raise ValueError('Selected spacing/section cannot fit the breaker support layout without overlap.')
            filled.extend((left+distance*k/bays,'JOIST') for k in range(1,bays))
        filled.append(item)
    clean=filled
    members=[]
    framing_poly=geo.inset(poly,jw) if s['rims'] else poly
    if s['framing_enabled']:
        for i,(x,role) in enumerate(clean):
            for region,bounds in enumerate(clear_spans(framing_poly,x,jw)):
                members.append(dict(key='JOIST_{0:03d}_{1}'.format(i+1,region+1),role=role,a=(x,bounds[0]),b=(x,bounds[1])))
        # Keep each touching joint-support assembly at a common clear span.
        for joint in joints:
            pair=[m for m in members if m['role']=='JOINT_SUPPORT' and abs(abs(m['a'][0]-joint)-jw/2)<EPS]
            if len(pair)==2:
                lo,hi=max(m['a'][1] for m in pair),min(m['b'][1] for m in pair)
                for m in pair: m['a']=(m['a'][0],lo); m['b']=(m['b'][0],hi)
        if s['rims']:
            members.extend(geo.perimeter_members(poly,jw,members))
        joists=[m for m in members if m['role']!='RIM']
        if rectangle or breaker_seams:
            # Long border sides parallel to joists need paired cross-blocks.
            # Each block stops at adjacent member faces, avoiding intersections.
            backing=set(); bw=s['block_width_in']/12.0
            cross_poly=geo.polygon([(y,x) for x,y in framing_poly][::-1])
            for seam in seams:
                if not rectangle and not seam.get('breaker'): continue
                if abs(seam['a'][1]-seam['b'][1])>EPS: continue
                lo,hi=sorted((seam['a'][0],seam['b'][0])); center=seam['a'][1]
                for y in (center-bw/2,center+bw/2):
                    xs=sorted(set(m['a'][0] for m in members if abs(m['a'][0]-m['b'][0])<EPS and
                                  min(m['a'][1],m['b'][1])-EPS<=y-bw/2 and
                                  max(m['a'][1],m['b'][1])+EPS>=y+bw/2))
                    clear=clear_spans(cross_poly,y,bw)
                    for left,right in zip(xs,xs[1:]):
                        a,b=left+jw/2,right-jw/2
                        if b-a>.5/12 and a<hi and b>lo and any(low-EPS<=a and b<=high+EPS for low,high in clear):
                            key=(round(a,8),round(b,8),round(y,8))
                            if key not in backing:
                                backing.add(key)
                                members.append(dict(key='BORDER_BACKING_{0}'.format(len(backing)),role='BORDER_BACKING',
                                                    a=(a,y),b=(b,y),section_width_in=s['block_width_in'],
                                                    section_depth_in=s['block_depth_in']))
    joists=[m for m in members if m['role'] in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT')]
    beams,posts=[] ,[]
    if s['supports_enabled']:
        rotated=[(y,x) for x,y in poly]; rotated.reverse()  # Keep CCW after swapping axes.
        common_low=max(m['a'][1] for m in joists) if joists else 0
        common_high=min(m['b'][1] for m in joists) if joists else span
        if not is_convex and common_high-common_low<=s['beam_near_setback_ft']+s['beam_far_setback_ft']:
            raise ValueError('This outline has separate framing support zones; use separate managed support layouts or disable automatic beams.')
        beam_positions=(s['beam_near_setback_ft'],span-s['beam_far_setback_ft']) if is_convex else (
            common_low+s['beam_near_setback_ft'],common_high-s['beam_far_setback_ft'])
        for i,y in enumerate(beam_positions):
            bounds=clear_span(rotated,y,max(s['beam_width_in']*s['beam_plies'],s['post_depth_in'])/12.0)
            if bounds is None or y<jw+s['beam_width_in']*s['beam_plies']/24 or y>span-jw-s['beam_width_in']*s['beam_plies']/24:
                raise ValueError('Beam setbacks do not fit this footprint; move beams inside the joist area.')
            lo,hi=bounds
            beams.append(dict(key='BEAM_{0}'.format(i+1),role='BEAM',a=(lo,y),b=(hi,y),
                              section_width_in=s['beam_width_in']*s['beam_plies'],section_depth_in=s['beam_depth_in'],z_offset_in=-s['joist_depth_in'],
                              ply_count=s['beam_plies'],ply_width_in=s['beam_width_in']))
            a,b=lo+s['post_end_setback_ft'],hi-s['post_end_setback_ft']
            if a-lo<s['post_width_in']/24 or b-a<s['post_width_in']/12:
                raise ValueError('Post setbacks cannot fit two posts under this beam.')
            count=max(1,int(math.ceil((b-a)/s['post_spacing_ft'])))
            if (b-a)/count<s['post_width_in']/12:
                raise ValueError('Posts would overlap.')
            for j in range(count+1):
                posts.append(dict(key='POST_{0}_{1}'.format(i+1,j+1),role='POST',beam_key=beams[-1]['key'],
                                  x=a+(b-a)*j/count,y=y,top_offset_in=-s['joist_depth_in']-s['beam_depth_in'],
                                  height_ft=s['post_height_ft'],width_in=s['post_width_in'],depth_in=s['post_depth_in']))
        if beams[1]['a'][1]-beams[0]['a'][1]<max(s['beam_width_in']*s['beam_plies'],s['post_depth_in'])/12:
            raise ValueError('Beams/posts overlap; revise setbacks.')
        if any(not all(m['a'][1]+EPS<beam['a'][1]<m['b'][1]-EPS for beam in beams) for m in joists):
            raise ValueError('Some joists do not span both beams on this angled footprint. Revise beam setbacks or use separately designed support zones.')
    add_staggered_blocking(members, beams, s, framing_poly)
    set_beam_splices(beams,posts,s['beam_stock_ft'])
    clips=[]
    if s['clips_enabled']:
        clips=clip_crossings(boards,members,rows)
    hardware,skipped=[],[]
    corners=corner_connections(poly,s) if s['corner_strap_symbol_uid'] else []
    for group in hanger_groups(members,s['joist_width_in']):
        if len(group)>2 and (s['hanger_symbol_uid'] or s['double_hanger_symbol_uid']):
            raise ValueError('Touching groups larger than two need a multi-ply hanger workflow.')
        double=len(group)==2
        if not s['double_hanger_symbol_uid' if double else 'hanger_symbol_uid']:
            continue
        for end,point in enumerate((group[0]['a'],group[0]['b'])):
            x=sum(m['a'][0] for m in group)/len(group); y=point[1]
            if any(math.hypot(x-corner['vertex'][0],y-corner['vertex'][1])<2*jw for corner in corners):
                skipped.append(dict(member_keys=[m['key'] for m in group],end=end,reason='Selected corner bracket'))
                continue
            role='DOUBLE_HANGER' if double else 'HANGER'
            hardware.append(dict(key=role+'_'+group[0]['key']+'_'+str(end),role=role,x=x,y=y,end=end,
                                 direction=(0,1 if end==0 else -1),
                                 member_keys=[m['key'] for m in group],ply_count=len(group),width_in=len(group)*s['joist_width_in'],
                                 depth_in=s['joist_depth_in'],z_offset_in=s['hanger_offset_in']-
                                 s['joist_depth_in']))
    if s['hurricane_symbol_uid']:
        for end,beam in enumerate(beams):
            tie_sides=tie_member_sides(joists,beam,s['joist_width_in'])
            for member in joists:
                if tie_sides[member['key']] is None:continue
                hardware.append(dict(key='TIE_'+beam['key']+'_'+member['key'],role='HURRICANE_STRAP',
                                     x=member['a'][0],y=beam['a'][1],end=end,beam_key=beam['key'],
                                     beam_outward=(0,-1 if end==0 else 1),joist_width_in=s['joist_width_in'],
                                     joist_across=(1,0),joist_side=tie_sides[member['key']],
                                     beam_width_in=s['beam_width_in']*s['beam_plies'],
                                     joist_key=member['key'],z_offset_in=-s['joist_depth_in']))
    hardware.extend(corners)
    warnings=['Convex/angled layout prototype: verify clipped board ends, perimeter framing, miter joints, seam backing and connector orientation in Revit. Footings and structural sizing are not included.']
    if any(m.get('corner_join')=='skew_review' for m in members):
        warnings.append('Non-orthogonal rim corners still require a native cut/join detail; the square butt-joint correction applies to orthogonal corners only.')
    if s['corner_strap_symbol_uid'] and len(corners)<len(poly):
        warnings.append('Corner angles are placed only at convex 90-degree rim connections. Return and skew corners need a separately reviewed detail; their hangers are retained.')
    if breaker_centers:
        warnings.append('Square-edge breaker boards have a center joist and paired end supports. Border/starter face fasteners are not included in clip counts.')
    elif s['seam_border'] and s['boards_enabled']:
        warnings.append('No automatic breaker selected in the framing direction. Enter a breaker center in feet to add one explicitly.')
    if not is_convex:
        warnings.append('Stepped/concave footprint: framing spans are clipped to the actual outline. Beam setbacks use the common joist bearing span; verify resulting cantilevers and return-corner supports.')
    if courses and s['double_border_joists'] and not rectangle:
        warnings.append('Touching border pairs currently require edges aligned with the decking axis; skewed border backing needs review.')
    if seams and not rectangle:
        warnings.append('Skewed border seam backing requires a separately designed support detail; only stock-limited boards are generated at those seams.')
    if any(len(g)==2 for g in hanger_groups(members,s['joist_width_in'])) and s['hanger_symbol_uid'] and not s['double_hanger_symbol_uid']:
        warnings.append('Touching double joists have no selected double hanger; singles are not substituted.')
    if s['hurricane_symbol_uid'] and not beams:
        warnings.append('No enabled beam supports: no hurricane ties are placed.')
    if beams and s['beam_width_in']*s['beam_plies']>s['post_depth_in']+EPS:
        warnings.append('Built-up beam width exceeds post depth. Review bearing/post-cap detail; post caps are not modeled.')
    if any(len(beam['cut_stations_ft'])>2 for beam in beams):
        warnings.append('Beam plies split at modeled posts to fit stock length; verify splice bearing and ply fastening.')
    if len(boards)+len(members)+sum(len(beam_ply_items(b)) for b in beams)+len(posts)+len(clips)+len(hardware)>15000:
        raise ValueError('Prototype limit is 15,000 elements.')
    return dict(settings=s,run=run,span=span,boards=boards,members=members,beams=beams,posts=posts,
                clips=clips,hardware=hardware,joints=sorted(joints),rows=rows,supports=clean,
                warnings=warnings,skipped_hanger_connections=skipped,
                counts=dict(boards=sum(b['role']=='BOARD' for b in boards),borders=sum(b['role']=='BORDER' for b in boards),
                            framing=len(members),beams=sum(len(beam_ply_items(b)) for b in beams),beam_assemblies=len(beams),posts=len(posts),clips=len(clips),
                            hangers=sum(h['role'] in ('HANGER','DOUBLE_HANGER') for h in hardware),
                            double_hangers=sum(h['role']=='DOUBLE_HANGER' for h in hardware),
                            hurricane_straps=sum(h['role']=='HURRICANE_STRAP' for h in hardware),
                            corner_straps=sum(h['role']=='CORNER_STRAP' for h in hardware)))


def fixed_framing(s):
    from rt_layout import plan as base_plan
    source_settings=dict(s,board_angle_deg=0,joists_follow_angle=True,
                         clips_enabled=False,_ignore_field_seams=True,_forced_joint_centers=[])
    sf,df=geo.frame(source_settings),geo.frame(s)
    delta=sf['angle']-df['angle']; c,sn=math.cos(delta),math.sin(delta)
    if abs(c)<.05:
        raise ValueError('Decking is nearly parallel to the fixed joists. Enable Rotate joists with decking angle or choose another decking direction.')
    def transform(point):
        x,y=point
        cs,ss=math.cos(sf['angle']),math.sin(sf['angle'])
        original=(sf['shift'][0]+cs*x-ss*y,sf['shift'][1]+ss*x+cs*y)
        cd,sd=math.cos(df['angle']),math.sin(df['angle'])
        x,y=original[0]-df['shift'][0],original[1]-df['shift'][1]
        return (cd*x+sd*y,-sd*x+cd*y)
    field=geo.inset(df['polygon'],s['border_courses']*(s['board_width_in']+s['gap_in'])/12.0) if s['picture_frame'] and s['boards_enabled'] else df['polygon']
    source_field=geo.inset(sf['polygon'],s['border_courses']*(s['board_width_in']+s['gap_in'])/12.0) if s['picture_frame'] and s['boards_enabled'] else sf['polygon']
    breaker_centers=breaker_centers_for(source_field,s)
    y0,y1=min(p[1] for p in field),max(p[1] for p in field)
    rows=[(a+y0,b+y0,mode) for a,b,mode in board_rows(y1-y0,s['board_width_in'],s['gap_in'],s['board_row_layout'])] if s['boards_enabled'] else []
    frame_poly=geo.inset(sf['polygon'],s['joist_width_in']/12.0) if s['rims'] else sf['polygon']
    candidates=[]
    for x in stations(sf['run'],s['joist_width_in']/12.0,s['spacing_in']/12.0):
        if any(abs(x-center)<s['board_width_in']/24+1.5*s['joist_width_in']/12+EPS for center in breaker_centers):
            continue
        for span in clear_spans(frame_poly,x,s['joist_width_in']*2/12.0):
            candidates.append((x,transform((x,span[0])),transform((x,span[1]))))
    boards=[]; forced=set()
    for row,(low,high,mode) in enumerate(rows):
        crossing=[]; y=(low+high)/2
        for foot_x,a,b in candidates:
            if abs(b[1]-a[1])<EPS: continue
            t=(y-a[1])/(b[1]-a[1])
            if EPS<t<1-EPS: crossing.append((a[0]+t*(b[0]-a[0]),foot_x))
        phase=2*s['spacing_in']/12 if s['stagger'] and row%2 else 0
        strips=geo.intersection_parts([(0,low),(df['run'],low),(df['run'],high),(0,high)],field)
        for center in breaker_centers:
            half=(s['board_width_in']+2*s['butt_gap_in'])/24
            masks=[[transform(p) for p in [(a,0),(b,0),(b,sf['span']),(a,sf['span'])]]
                   for a,b in ((0,center-half),(center+half,sf['run']))]
            strips=[part for strip in strips for mask in masks for part in geo.intersection_parts(mask,strip)]
        for region,strip in enumerate(strips):
            start,end=min(p[0] for p in strip),max(p[0] for p in strip)
            joints=joint_stations(start,end,[x for x,foot_x in crossing],s['stock_ft'],phase)
            for cut in joints:
                forced.add(round(min(crossing,key=lambda value:abs(value[0]-cut))[1],8))
            cuts=[start]+joints+[end]
            for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
                a+=s['butt_gap_in']/24 if i else 0; b-=s['butt_gap_in']/24 if i<len(cuts)-2 else 0
                for part,shape in enumerate(geo.intersection_parts([(a,low),(b,low),(b,high),(a,high)],strip)):
                    if shape and b-a>.5/12:
                        boards.append(dict(key='BOARD_{0}_{1}_{2}_{3}'.format(row+1,region+1,i+1,part+1),role='BOARD',row=row,
                                           start=a,end=b,low=low,high=high,polygon=shape,width_in=(high-low)*12,
                                           length_ft=b-a,edge_mode=mode))
    source_settings['_forced_joint_centers']=sorted(forced)
    source=rotated_plan(source_settings) if s['seam_border'] or forced or s.get('footprint_polygon') or s['border_courses']==2 or (
        s['picture_frame'] and max(s['run_ft'],s['span_ft'])>s['stock_ft']) else base_plan(source_settings)
    # The source is only a framing/border scaffold. Its straight field boards
    # are discarded; angled cuts use real crossing positions on its twin joists.
    for board in source['boards']:
        if board['role']!='BORDER': continue
        board=dict(board,polygon=[transform(p) for p in board['polygon']])
        u=board.get('axis_vector',(0,1) if board.get('axis')=='B' else (1,0))
        board['axis_vector']=(c*u[0]-sn*u[1],sn*u[0]+c*u[1]); boards.append(board)
    members=[]
    for item in source['members']+source['beams']:
        members.append(dict(item,a=transform(item['a']),b=transform(item['b'])))
    beams=[m for m in members if m['role']=='BEAM']; members=[m for m in members if m['role']!='BEAM']
    posts=[]
    for item in source['posts']:
        x,y=transform((item['x'],item['y'])); posts.append(dict(item,x=x,y=y,rotation_deg=math.degrees(delta)))
    hardware=[]
    for item in source['hardware']:
        x,y=transform((item['x'],item['y']))
        placed=dict(item,x=x,y=y,rotation_deg=item.get('rotation_deg',0)+math.degrees(delta))
        if item.get('direction'):
            dx,dy=item['direction']; placed['direction']=(c*dx-sn*dy,sn*dx+c*dy)
        if item.get('beam_outward'):
            dx,dy=item['beam_outward']; placed['beam_outward']=(c*dx-sn*dy,sn*dx+c*dy)
        if item.get('joist_across'):
            dx,dy=item['joist_across']; placed['joist_across']=(c*dx-sn*dy,sn*dx+c*dy)
        if item.get('vertex'): placed['vertex']=transform(item['vertex'])
        hardware.append(placed)
    clips=[]; supports=[m for m in members if m['role'] in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT') or
                       (m['role']=='RIM' and abs(m['b'][0]-m['a'][0])>EPS)]
    if s['clips_enabled']:
        clips=clip_crossings(boards,members,rows)
    counts=dict(source['counts'],boards=sum(b['role']=='BOARD' for b in boards),
                borders=sum(b['role']=='BORDER' for b in boards),clips=len(clips))
    warnings=list(source['warnings'])+['Joists/beams keep the footprint direction while decking rotates. Angled butt joints use actual paired-joist crossings. Check diagonal product-span limits and corner details.']
    if s['boards_enabled'] and s['spacing_in']>12:
        warnings.append('Verify the selected composite product diagonal-span limits; the chosen spacing is a modeling input, not an approved span.')
    if sum(counts[k] for k in ('boards','borders','framing','beams','posts','clips','hangers','hurricane_straps','corner_straps'))>15000:
        raise ValueError('Prototype limit is 15,000 elements.')
    return dict(settings=s,run=df['run'],span=df['span'],boards=boards,members=members,beams=beams,posts=posts,
                hardware=hardware,clips=clips,joints=sorted(forced),rows=rows,supports=source['supports'],
                warnings=warnings,skipped_hanger_connections=source.get('skipped_hanger_connections',[]),counts=counts)
