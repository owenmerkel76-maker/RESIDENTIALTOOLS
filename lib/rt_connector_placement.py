# -*- coding: utf-8 -*-
"""Probe native connector geometry in a rolled-back subtransaction, then fit it.

Simple measurable seat hangers, square L angles and reviewed perpendicular-tab
ties are supported. Ambiguous geometry fails before the old layout is deleted.
"""
import math
import json
import io
import os
import re
import rt_connector_geometry as geo
import rt_hardware_nails

ROLES=('HANGER','DOUBLE_HANGER','CORNER_STRAP','HURRICANE_STRAP')
FIT_TOL=.02/12.0


def xyz(value,DB): return DB.XYZ(*value)
def vector(value): return (value.X,value.Y,value.Z)


def triangles_of(element,DB):
    options=DB.Options(); options.DetailLevel=DB.ViewDetailLevel.Fine
    result=[]
    def mesh_triangles(mesh):
        for i in range(mesh.NumTriangles):
            tri=mesh.get_Triangle(i)
            result.append(tuple(vector(tri.get_Vertex(j)) for j in range(3)))
            if len(result)>100000: raise ValueError('Connector exceeds the geometry probe limit (100,000 triangles).')
    def visit(objects):
        for obj in objects:
            if isinstance(obj,DB.GeometryInstance): visit(obj.GetInstanceGeometry())
            elif isinstance(obj,DB.Solid):
                for face in obj.Faces: mesh_triangles(face.Triangulate())
            elif isinstance(obj,DB.Mesh): mesh_triangles(obj)
    visit(element.get_Geometry(options))
    if not result: raise ValueError('Selected connector has no measurable Fine-detail solid or mesh geometry.')
    return result


def native_basis(instance):
    t=instance.GetTransform()
    return tuple(vector(v) for v in (t.BasisX,t.BasisY,t.BasisZ))


def create_plane(doc,origin,normal,direction,name,DB):
    origin=xyz(origin,DB); normal=xyz(geo.unit(normal),DB)
    direction=xyz(geo.unit(direction),DB)
    if abs(normal.DotProduct(direction))>1.e-6: raise ValueError('Connector host frame is not perpendicular.')
    plane=doc.Create.NewReferencePlane(origin+direction,origin,normal.CrossProduct(direction),doc.ActiveView)
    if plane is None: raise ValueError('Could not create connector mounting plane.')
    plane.Name=name; doc.Regenerate()
    if plane.GetPlane().Normal.DotProduct(normal)<0: plane.Flip(); doc.Regenerate()
    if plane.GetPlane().Normal.DotProduct(normal)<.999999 or plane.GetReference() is None:
        raise ValueError('Revit could not orient the connector mounting plane.')
    return plane


def point_instance(doc,point,symbol,level,DB,structural_type):
    if symbol.Category.Id.Equals(DB.ElementId(DB.BuiltInCategory.OST_StructConnections)):
        return doc.Create.NewFamilyInstance(point,symbol,structural_type)
    return doc.Create.NewFamilyInstance(point,symbol,level,structural_type)


def log_probe_failure(triangles,symbol,item,model,log):
    """Keep a local replay mesh without hiding the original probe exception."""
    try:
        folder=getattr(log,'report_folder',None)
        if folder:
            token=re.sub(r'[^A-Za-z0-9_-]','_',symbol.UniqueId)[-80:]
            path=os.path.join(folder,'connector_probe_{0}_{1}.json'.format(item['role'],token))
            payload=dict(role=item['role'],family_name=symbol.Family.Name,model=model,
                         symbol_uid=symbol.UniqueId,width_in=item.get('width_in'),depth_in=item.get('depth_in'),
                         units='feet',coordinates='temporary probe instance at project origin',triangles=triangles)
            with io.open(path,'w',encoding='utf-8') as stream:
                stream.write(u'{0}'.format(json.dumps(payload)))
            log('Connector replay mesh saved locally: '+path)
        faces=geo.planes(triangles)
        log('Connector probe could not identify contact faces: type={0}; model={1}; triangles={2}; major_planes={3}'.format(
            symbol.UniqueId,model,len(triangles),json.dumps([
                dict(normal=p['n'],offset=p['q'],area=p['area'],centroid=geo.area_centroid(p['triangles']))
                for p in sorted(faces,key=lambda p:p['area'],reverse=True)[:12]])))
    except Exception as error:
        try:log('Connector probe diagnostic unavailable: {0}'.format(error))
        except Exception:pass


def probe(doc,symbol,item,level,DB,structural_type,log):
    temporary=DB.SubTransaction(doc); temporary.Start()
    try:
        point=DB.XYZ(0,0,0)
        if symbol.Family.FamilyPlacementType==DB.FamilyPlacementType.WorkPlaneBased:
            plane=create_plane(doc,(0,0,0),(0,0,1),(1,0,0),'RT Temporary connector probe',DB)
            instance=doc.Create.NewFamilyInstance(plane.GetReference(),point,DB.XYZ.BasisX,symbol)
        else: instance=point_instance(doc,point,symbol,level,DB,structural_type)
        if instance is None: raise ValueError('Connector probe instance was not created.')
        doc.Regenerate(); triangles=triangles_of(instance,DB)
        model=rt_hardware_nails.model_name(getattr(symbol.Family,'Name',''))
        try:
            profile=(geo.tie_profile(triangles,model=model if model=='H2.5A' else None) if item['role']=='HURRICANE_STRAP' else
                     geo.angle_profile(triangles) if item['role']=='CORNER_STRAP' else
                     geo.hanger_profile(triangles,item['width_in'],item['depth_in']))
        except Exception:
            log_probe_failure(triangles,symbol,item,model,log)
            raise
        if item['role']=='CORNER_STRAP' and profile['details']['length_in']>item['depth_in']+.02:
            raise ValueError('Selected corner angle is taller than the modeled joist depth. Select a shorter angle.')
        profile['native_basis']=native_basis(instance)
        profile['holes']=geo.measured_holes(triangles,profile)
        profile['width_in']=item.get('width_in'); profile['depth_in']=item.get('depth_in')
        log('Measured connector profile: type={0}; role={1}; profile={2}'.format(symbol.UniqueId,item['role'],json.dumps(profile)))
        return profile
    finally:
        temporary.RollBack()


def build_profiles(doc,symbols,items,level,DB,structural_type,log):
    result={}
    for item in items:
        if item['role'] not in ROLES: continue
        symbol=symbols[item['role']]
        if symbol is None: raise ValueError('No selected native family for '+item['role'])
        key=(item['role'],symbol.UniqueId,item.get('width_in'),item.get('depth_in'))
        if key not in result: result[key]=probe(doc,symbol,item,level,DB,structural_type,log)
    return result


def placement(profile,item,coord,underside):
    def world_direction(dx,dy):
        return geo.unit(geo.add(geo.mul(vector(coord[1]),dx),geo.mul(vector(coord[2]),dy)))
    up=(0,0,1)
    if item['role']=='CORNER_STRAP':
        angle=math.radians(item['rotation_deg']); x=world_direction(math.cos(angle),math.sin(angle))
        target=(x,geo.cross(up,x),up)
    elif item['role']=='HURRICANE_STRAP':
        y=world_direction(*item['beam_outward']); sign=profile['details']['upper_sign']
        if item.get('joist_side'):
            x=geo.mul(world_direction(*item['joist_across']),item['joist_side'])
            y=geo.mul(geo.cross(up,x),sign)
        else:x=geo.mul(geo.cross(y,up),sign)
        target=(x,y,geo.cross(x,y))
    else:
        forward=world_direction(*item['direction']); target=(geo.cross(forward,up),forward,up)
    datum=geo.add(vector(coord[0]),geo.add(geo.mul(vector(coord[1]),item['x']),geo.mul(vector(coord[2]),item['y'])))
    datum=geo.add(datum,(0,0,underside+item.get('z_offset_in',0)/12.0))
    if item['role']=='HURRICANE_STRAP':
        datum=geo.add(datum,geo.add(geo.mul(target[0],item['joist_width_in']/24),geo.mul(target[1],item['beam_width_in']/24)))
    rotate=lambda v:geo.rotate(v,profile['axes'],target)
    origin=geo.sub(datum,rotate(profile['origin']))
    normal=rotate((0,0,1)); direction=rotate((1,0,0))
    # Plane identity includes orientation and distance, rather than elevation.
    n=geo.unit(normal)
    plane_key=tuple(round(v,8) for v in n)+(round(geo.dot(n,origin),8),)
    return dict(origin=origin,normal=normal,direction=direction,target=target,datum=datum,
                native_basis=tuple(rotate(v) for v in profile['native_basis']),plane_key=plane_key)


def rotation_axis_angle(source,target):
    """Quaternion from a measured proper orthonormal frame change."""
    m=[[sum(target[k][i]*source[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    trace=sum(m[i][i] for i in range(3))
    if trace>0:
        r=math.sqrt(1+trace)*2; w=.25*r
        x,y,z=(m[2][1]-m[1][2])/r,(m[0][2]-m[2][0])/r,(m[1][0]-m[0][1])/r
    else:
        i=max(range(3),key=lambda j:m[j][j]); j=(i+1)%3; k=(i+2)%3
        r=math.sqrt(max(0,1+m[i][i]-m[j][j]-m[k][k]))*2
        if r<1.e-9: raise ValueError('Connector frame is mirrored or degenerate.')
        q=[0,0,0]; q[i]=.25*r; q[j]=(m[i][j]+m[j][i])/r; q[k]=(m[i][k]+m[k][i])/r
        x,y,z=q; w=(m[k][j]-m[j][k])/r
    length=math.sqrt(x*x+y*y+z*z)
    if length<1.e-9: return (0,0,1),0
    return (x/length,y/length,z/length),2*math.atan2(length,w)


def create(doc,item,profile,fit,symbol,level,plane,DB,structural_type):
    point=xyz(fit['origin'],DB)
    if symbol.Family.FamilyPlacementType==DB.FamilyPlacementType.WorkPlaneBased:
        if plane is None: raise ValueError('Measured connector requires its oriented host plane.')
        instance=doc.Create.NewFamilyInstance(plane.GetReference(),point,xyz(fit['direction'],DB),symbol)
    else:
        instance=point_instance(doc,point,symbol,level,DB,structural_type)
        if instance is None: raise ValueError('Measured connector could not be placed.')
        doc.Regenerate(); axis,angle=rotation_axis_angle(native_basis(instance),fit['native_basis'])
        if abs(angle)>1.e-9:
            DB.ElementTransformUtils.RotateElement(doc,instance.Id,DB.Line.CreateBound(point,point+xyz(axis,DB)),angle)
    if instance is None: raise ValueError('Measured connector could not be placed.')
    doc.Regenerate()
    if any(geo.dot(a,b)<.99999 for a,b in zip(native_basis(instance),fit['native_basis'])):
        raise ValueError('Family hosting/vertical constraints prevented the measured mounting orientation: '+item['key'])
    points=[p for tri in triangles_of(instance,DB) for p in tri]
    actual=geo.assemble('verification',points,fit['target'],fit['datum'],{})
    errors=[abs(a-b) for bounds,expected in zip(actual['bounds'],profile['bounds']) for a,b in zip(bounds,expected)]
    errors.extend(abs(a-b) for a,b in zip(actual['mean'],profile['mean']))
    if max(errors)>FIT_TOL:
        raise ValueError('Connector geometry did not reach its measured seat/contact datum: {0}; error {1:.4f} inches.'.format(item['key'],max(errors)*12))
    return instance
