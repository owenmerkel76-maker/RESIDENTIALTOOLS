# -*- coding: utf-8 -*-
"""Measured connector contact frames; no assumed vendor family axes."""
import math

EPS=1.e-9
PLANE_TOL=.002/12.0


def add(a,b): return tuple(a[i]+b[i] for i in range(3))
def sub(a,b): return tuple(a[i]-b[i] for i in range(3))
def mul(a,v): return tuple(x*v for x in a)
def dot(a,b): return sum(a[i]*b[i] for i in range(3))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def size(a): return math.sqrt(dot(a,a))
def unit(a):
    length=size(a)
    if length<EPS: raise ValueError('Connector geometry has a degenerate direction.')
    return mul(a,1.0/length)
def extent(points,axis):
    values=[dot(p,axis) for p in points]
    return min(values),max(values)


def planes(triangles):
    result=[]
    for tri in triangles:
        raw=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0])); area=size(raw)/2
        if area<1.e-10: continue
        n=unit(raw)
        if next(v for v in n if abs(v)>1.e-5)<0: n=mul(n,-1)
        q=dot(n,tri[0])
        matched=next((p for p in result if dot(p['n'],n)>1-1.e-6 and abs(p['q']-q)<PLANE_TOL),None)
        if matched is None:
            matched=dict(n=n,q=q,area=0,points=[],triangles=[]); result.append(matched)
        matched['area']+=area; matched['points'].extend(tri); matched['triangles'].append(tri)
    return result


def dominant_axes(faces):
    orientations=[]
    for face in faces:
        found=next((row for row in orientations if abs(dot(row['n'],face['n']))>1-1.e-6),None)
        if found: found['area']+=face['area']
        else: orientations.append(dict(n=face['n'],area=face['area']))
    major=sorted(orientations,key=lambda row:row['area'],reverse=True)[:16]
    pairs=[(a['area']*b['area'],a['n'],b['n']) for i,a in enumerate(major) for b in major[i+1:] if abs(dot(a['n'],b['n']))<.002]
    if not pairs: raise ValueError('No perpendicular mounting plate faces were detected.')
    unused,a,b=max(pairs,key=lambda row:row[0])
    return (a,b,unit(cross(a,b)))


def assemble(kind,points,axes,origin,details):
    local=[tuple(dot(sub(p,origin),axis) for axis in axes) for p in points]
    return dict(kind=kind,axes=axes,origin=origin,
                bounds=[(min(p[i] for p in local),max(p[i] for p in local)) for i in range(3)],
                mean=[sum(p[i] for p in local)/len(local) for i in range(3)],details=details)


def angle_profile(triangles):
    points=[p for tri in triangles for p in tri]; faces=planes(triangles); axes=dominant_axes(faces)
    directions=[]
    for axis in axes[:2]:
        candidates=[p for p in faces if abs(dot(p['n'],axis))>1-1.e-6]
        plate=max(candidates,key=lambda p:p['area']); low,high=extent(points,axis)
        q=sum(dot(p,axis) for p in plate['points'])/len(plate['points'])
        if min(abs(q-low),abs(q-high))>.15/12:
            raise ValueError('Angle mounting plates are not at the heel of a simple L section.')
        directions.append(axis if abs(q-low)<abs(q-high) else mul(axis,-1))
    x,y=directions; z=unit(cross(x,y)); lowz,highz=extent(points,z)
    if highz-lowz<1.2*max(extent(points,x)[1]-extent(points,x)[0],extent(points,y)[1]-extent(points,y)[0]):
        raise ValueError('Could not distinguish the angle length from its two legs.')
    origin=add(add(mul(x,extent(points,x)[0]),mul(y,extent(points,y)[0])),mul(z,(lowz+highz)/2))
    return assemble('corner',points,(x,y,z),origin,dict(length_in=(highz-lowz)*12,datum='two outer contact planes; length centered'))


def hanger_profile(triangles,width_in,depth_in):
    points=[p for tri in triangles for p in tri]; faces=planes(triangles); axes=dominant_axes(faces); candidates=[]
    for axis in axes:
        low,high=extent(points,axis); height=(high-low)*12
        if not depth_in*.3<=height<=depth_in+3: continue
        parallel=[p for p in faces if abs(dot(p['n'],axis))>1-1.e-6]
        for sign in (1,-1):
            up=mul(axis,sign); bottom=extent(points,up)[0]
            seat_faces=[p for p in parallel if abs(sum(dot(v,up) for v in p['points'])/len(p['points'])-bottom)<.15/12]
            if not seat_faces: continue
            largest=max(p['area'] for p in seat_faces)
            seat_faces=[p for p in seat_faces if p['area']>=largest*.5]
            seat=max(seat_faces,key=lambda p:sum(dot(v,up) for v in p['points'])/len(p['points']))
            seat_top=sum(dot(p,up) for p in seat['points'])/len(seat['points'])
            for width_axis in axes:
                if abs(dot(width_axis,up))>.01: continue
                a,b=extent(seat['points'],width_axis); error=abs((b-a)*12-width_in)
                if error>max(.25,width_in*.08): continue
                depth_axis=unit(cross(up,width_axis)); da,db=extent(seat['points'],depth_axis)
                if not .5<(db-da)*12<6 or largest*144<width_in*.4: continue
                back_faces=[p for p in faces if abs(dot(p['n'],depth_axis))>1-1.e-6]
                if not back_faces: continue
                back=max(back_faces,key=lambda p:p['area']); back_q=sum(dot(v,depth_axis) for v in back['points'])/len(back['points'])
                into=(da+db)/2-back_q
                if abs(into)<.25/12: continue
                forward=depth_axis if into>0 else mul(depth_axis,-1)
                right=unit(cross(forward,up)); center=sum(extent(seat['points'],right))/2
                peak=sum(dot(v,forward) for v in back['points'])/len(back['points'])
                mounting=[p for p in back_faces if p['area']>=back['area']*.4 and
                          abs(sum(dot(v,forward) for v in p['points'])/len(p['points'])-peak)<.15/12]
                rear=min(sum(dot(v,forward) for v in p['points'])/len(p['points']) for p in mounting)
                origin=add(add(mul(right,center),mul(forward,rear)),mul(up,seat_top))
                profile=assemble('hanger',points,(right,forward,up),origin,
                    dict(clear_width_in=(b-a)*12,seat_depth_in=(db-da)*12,height_in=height,datum='seat top; rear mounting plane; channel center'))
                candidates.append((error,profile))
    if not candidates: raise ValueError('Could not identify a seat and rear mounting plate matching the selected joist width.')
    candidates.sort(key=lambda value:value[0])
    best=candidates[0]
    if any(abs(error-best[0])<.025 and dot(profile['axes'][2],best[1]['axes'][2])<.99 for error,profile in candidates[1:]):
        raise ValueError('Ambiguous hanger seat directions. Geometry diagnostics are in run.log; no rotation is guessed.')
    return best[1]


def rotate(vector,source,target):
    result=(0,0,0)
    for old,new in zip(source,target): result=add(result,mul(new,dot(vector,old)))
    return result


def component_planes(faces):
    """Keep coplanar tab ends out of a face unless they share a mesh edge."""
    result=[]
    for face in faces:
        links={};triangles=face['triangles']
        for i,tri in enumerate(triangles):
            keys=[tuple(round(v,7) for v in p) for p in tri]
            for a,b in zip(keys,keys[1:]+keys[:1]):links.setdefault(tuple(sorted((a,b))),[]).append(i)
        unseen=set(range(len(triangles)))
        while unseen:
            stack=[unseen.pop()];indices=[]
            while stack:
                i=stack.pop();indices.append(i)
                keys=[tuple(round(v,7) for v in p) for p in triangles[i]]
                for a,b in zip(keys,keys[1:]+keys[:1]):
                    for other in links[tuple(sorted((a,b)))]:
                        if other in unseen:unseen.remove(other);stack.append(other)
            parts=[triangles[i] for i in indices];points=[p for tri in parts for p in tri]
            area=sum(size(cross(sub(tri[1],tri[0]),sub(tri[2],tri[0])))/2 for tri in parts)
            result.append(dict(n=face['n'],q=face['q'],points=points,triangles=parts,area=area))
    return result


def area_centroid(triangles):
    """Surface centroid independent of vertex density and mesh refinement."""
    total=0.0;weighted=(0,0,0)
    for tri in triangles:
        area=size(cross(sub(tri[1],tri[0]),sub(tri[2],tri[0])))/2
        if area<EPS*EPS:continue
        center=mul(add(add(tri[0],tri[1]),tri[2]),1.0/3)
        weighted=add(weighted,mul(center,area));total+=area
    if total<EPS*EPS:raise ValueError('Tie mounting face has no measurable surface area.')
    return mul(weighted,1.0/total)


def mounting_rail(triangles,axes,origin,plane_index):
    """Intersect a vertical schematic nail rail with actual mounting metal.

    Intervals describe solid face coverage, including tapered edges and holes;
    they are not manufacturer fastener-hole coordinates.
    """
    local=[tuple(tuple(dot(sub(p,origin),axis) for axis in axes) for p in tri) for tri in triangles]
    across_index=1-plane_index
    values=[p[across_index] for tri in local for p in tri]
    across=(min(values)+max(values))/2
    intervals=[]
    for tri in local:
        values=[]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            da,db=a[across_index]-across,b[across_index]-across
            if abs(da)<EPS:values.append(a[2])
            if abs(db-da)>EPS:
                t=-da/(db-da)
                if -EPS<=t<=1+EPS:values.append(a[2]+max(0,min(1,t))*(b[2]-a[2]))
        if len(values)>=2 and max(values)-min(values)>EPS:intervals.append((min(values),max(values)))
    merged=[]
    for low,high in sorted(intervals):
        if merged and low<=merged[-1][1]+EPS:merged[-1][1]=max(merged[-1][1],high)
        else:merged.append([low,high])
    center=area_centroid(triangles)
    return dict(plane=dot(sub(center,origin),axes[plane_index]),across=across,intervals=merged)


def tie_profile(triangles,model=None):
    """Fit contact planes; recognized US H2.5A uses its published plate line.

    H2.5A has equal-height flanges with overlapping tapered tails. Their overall
    heights cannot identify an upper tab or the beam seating datum. The current
    US drawing (C-C-2026 p299) places either plate line 2-3/16 in from its end.
    """
    points=[p for tri in triangles for p in tri]; faces=component_planes(planes(triangles)); axes=dominant_axes(faces)
    plates=[]
    for axis in axes[:2]:
        group=[p for p in faces if abs(dot(p['n'],axis))>1-1.e-6]
        plates.append(max(group,key=lambda p:p['area']))
    centers=[area_centroid(p['triangles']) for p in plates]
    if abs(dot(sub(centers[0],centers[1]),axes[2]))<.5/12:
        raise ValueError('Tie mounting faces have no distinct vertical nail-tab regions; review this family.')
    # Either symmetric H2.5A flange can be the upper flange. Pick the first
    # measured plane and derive up from its area centroid, never its mesh count.
    upper,lower=0,1;x,y=axes[upper],axes[lower]
    directions=[]
    for axis,plate,other in ((x,plates[upper],plates[lower]),(y,plates[lower],plates[upper])):
        base=dot(area_centroid(plate['triangles']),axis)
        center=dot(area_centroid(other['triangles']),axis)
        if abs(center-base)<.15/12: raise ValueError('Hurricane tie mounting legs have no measurable corner offset.')
        directions.append(axis if center>base else mul(axis,-1))
    x,y=directions; z=unit(cross(x,y))
    uc=dot(centers[upper],z);lc=dot(centers[lower],z)
    sign=1 if uc>lc else -1
    up=mul(z,sign); ulow,uhigh=extent(plates[upper]['points'],up); llow,lhigh=extent(plates[lower]['points'],up)
    height=(extent(points,up)[1]-extent(points,up)[0])*12
    if model=='H2.5A':
        if abs(height-6)>.06:
            raise ValueError('Recognized US H2.5A must measure 6 inches overall; measured {0:.4f}. No plate datum was assumed.'.format(height))
        for i,plate in enumerate(plates):
            across=axes[1-i];lo,hi=extent(plate['points'],across)
            if not .75<=(hi-lo)*12<=2.5:
                raise ValueError('Recognized H2.5A flange width is inconsistent with its mounting geometry.')
        plate_line=extent(points,up)[0]+2.1875/12
        if dot(centers[upper],up)<=plate_line+.1/12 or dot(centers[lower],up)>=plate_line-.1/12:
            raise ValueError('Recognized H2.5A mounting tabs do not straddle its published plate line; review this family.')
        datum='US H2.5A published plate line: 2-3/16 inches from lower end'
    else:
        if ulow<lhigh-.25/12:
            raise ValueError('Custom tie tabs overlap; a verified model-specific plate-line datum is required.')
        plate_line=(ulow+lhigh)/2
        datum='separated custom mounting tabs; transition center'
    contacts=[];outer_faces=[]
    for axis,plate in ((x,plates[upper]),(y,plates[lower])):
        q=dot(area_centroid(plate['triangles']),axis)
        broad=[p for p in faces if abs(dot(p['n'],axis))>1-1.e-6 and
               p['area']>=plate['area']*.4 and abs(dot(area_centroid(p['triangles']),axis)-q)<.15/12]
        # Equal-area sheet faces can arrive in either order. The minimum plane
        # along the away-from-wood axis contacts the member, without burying metal.
        contacts.append(min(dot(v,axis) for face in broad for v in face['points']))
        front=max(dot(area_centroid(face['triangles']),axis) for face in broad)
        outer_faces.append(max((face for face in broad if abs(dot(area_centroid(face['triangles']),axis)-front)<PLANE_TOL),
                               key=lambda face:face['area']))
    origin=add(add(mul(x,contacts[0]),mul(y,contacts[1])),mul(up,plate_line))
    rails={group:mounting_rail(face['triangles'],(x,y,z),origin,index)
           for index,group,face in ((0,'joist tie tab',outer_faces[0]),(1,'beam tie tab',outer_faces[1]))}
    return assemble('tie',points,(x,y,z),origin,dict(upper_sign=sign,datum=datum,model=model,
        height_in=height,plate_line_from_lower_in=2.1875 if model=='H2.5A' else None,
        source_url='https://ssttoolbox.widen.net/content/orplhjaqw1/original/C-C-2026.pdf?download=true' if model=='H2.5A' else None,
        transition_gap_in=(ulow-lhigh)*12,
        mounting_face_centroids=centers,schematic_nail_rails=rails))


def measured_holes(triangles,profile):
    """Small closed boundaries in planar CAD mesh faces; tooling holes excluded."""
    result=[]
    for face in planes(triangles):
        edges={}; vertices={}
        for tri in face['triangles']:
            for a,b in zip(tri,tri[1:]+tri[:1]):
                ka,kb=tuple(round(v,7) for v in a),tuple(round(v,7) for v in b)
                if ka==kb: continue
                key=tuple(sorted((ka,kb))); edges[key]=edges.get(key,0)+1; vertices[ka]=a;vertices[kb]=b
        border=set(key for key,count in edges.items() if count==1); adjacency={}
        for a,b in border:adjacency.setdefault(a,[]).append(b);adjacency.setdefault(b,[]).append(a)
        while border:
            a,b=next(iter(border)); loop=[a]; previous,current=a,b; border.remove(tuple(sorted((a,b))))
            for unused in range(len(adjacency)+1):
                if current==a:break
                loop.append(current)
                choices=[p for p in adjacency.get(current,[]) if p!=previous and tuple(sorted((current,p))) in border]
                if len(choices)!=1:break
                nxt=choices[0];border.remove(tuple(sorted((current,nxt))));previous,current=current,nxt
            if current!=a or len(loop)<6:continue
            pts=[vertices[k] for k in loop]; n=face['n']
            u=unit(cross(n,(1,0,0) if abs(n[0])<.9 else (0,1,0)));v=cross(n,u)
            ua,ub=extent(pts,u);va,vb=extent(pts,v)
            if not (.12<min(ub-ua,vb-va)*12<.32 and max(ub-ua,vb-va)*12<.6):continue
            center=add(add(mul(u,(ua+ub)/2),mul(v,(va+vb)/2)),mul(n,face['q']))
            local=tuple(dot(sub(center,profile['origin']),axis) for axis in profile['axes'])
            normal=tuple(dot(n,axis) for axis in profile['axes'])
            result.append(dict(center=local,normal=normal,diameter_in=min(ub-ua,vb-va)*12))
    return result
