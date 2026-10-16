# -*- coding: utf-8 -*-
"""Revit 2025/2027 adapter: geometry, ownership, atomic coordinated rebuild."""
import json
import math
import uuid
from contextlib import contextmanager

from System import Guid, String
from System.Collections.Generic import List
from Autodesk.Revit import DB
from Autodesk.Revit.DB.ExtensibleStorage import (AccessLevel, DataStorage, Entity,
                                                 ExtensibleStorageFilter, Schema, SchemaBuilder)
from Autodesk.Revit.DB.Structure import StructuralFramingUtils, StructuralType

import rt_board_profile
import rt_clip
import rt_simpson_catalog
import rt_geometry
import rt_connector_placement
import rt_hardware_nails
from rt_layout import OWNER, VERSION, owned_registered, validate_deletion_scope, beam_ply_items

SCHEMA_GUID = Guid('4c61be62-398d-4fef-87a5-506ba95d2ec3')
LENGTH_TOL = .001 / 12.0
try:
    text_type = unicode
except NameError:
    text_type = str


def id_value(eid):
    return int(eid.Value)


def schema():
    result = Schema.Lookup(SCHEMA_GUID)
    if result is not None:
        field = result.GetField('Payload')
        if (result.SchemaName != 'ResidentialToolsRectV1' or field is None or
                field.ValueType.FullName != 'System.String'):
            raise RuntimeError('Residential ownership schema conflicts with another schema.')
        return result
    builder = SchemaBuilder(SCHEMA_GUID)
    builder.SetSchemaName('ResidentialToolsRectV1')
    builder.SetVendorId('RSDT')
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.AddSimpleField('Payload', String)
    return builder.Finish()


def read_stamp(element):
    entity = element.GetEntity(schema())
    if not entity.IsValid():
        return {}
    payload = entity.Get[String](schema().GetField('Payload'))
    try:
        result = json.loads(payload)
    except (ValueError, TypeError):
        raise ValueError('Corrupt Residential metadata on element ' + str(id_value(element.Id)))
    if not isinstance(result, dict):
        raise ValueError('Residential element metadata must be a JSON object.')
    return result


def write_stamp(element, payload):
    entity = Entity(schema())
    entity.Set[String](schema().GetField('Payload'),
                       text_type(json.dumps(payload, ensure_ascii=False)))
    element.SetEntity(entity)


def layout_records(doc):
    records = []
    seen = set()
    for element in DB.FilteredElementCollector(doc).OfClass(DataStorage):
        stamp = read_stamp(element)
        if stamp.get('owner') == OWNER and stamp.get('role') == 'LAYOUT':
            if stamp.get('version') != VERSION:
                raise ValueError('Layout version is not supported by this baseline.')
            if stamp.get('layout_id') in seen:
                raise ValueError('Duplicate layout registry detected. Refusing ambiguous rebuild.')
            seen.add(stamp.get('layout_id'))
            records.append((element, stamp))
    return records


class FailureLogger(DB.IFailuresPreprocessor):
    def __init__(self, log):
        self.log = log

    def PreprocessFailures(self, accessor):
        error = False
        for failure in accessor.GetFailureMessages():
            self.log('REVIT {0}: {1}; element ids={2}'.format(
                failure.GetSeverity(), failure.GetDescriptionText(),
                [id_value(e) for e in failure.GetFailingElementIds()]))
            if failure.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(failure)
            else:
                error = True
        return (DB.FailureProcessingResult.ProceedWithRollBack if error
                else DB.FailureProcessingResult.Continue)


@contextmanager
def transaction(doc, title, log):
    tx = DB.Transaction(doc, title)
    handler = FailureLogger(log)
    try:
        if tx.Start() != DB.TransactionStatus.Started:
            raise RuntimeError('Transaction could not start.')
        options = tx.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(handler)
        options.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(options)
        yield
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise RuntimeError('Revit rejected the build; transaction rolled back.')
    finally:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        tx.Dispose()


def types(doc, category):
    return list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(category))


def symbol_name(symbol):
    parameter = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    family=symbol.Family.Name
    name=parameter.AsString() if parameter and parameter.HasValue else symbol.UniqueId
    return family if family==name else family+' | '+name


def clip_types(doc):
    categories = (DB.BuiltInCategory.OST_GenericModel,)
    return [symbol for symbol in types(doc, categories[0])
            if not point_family_reason(symbol.Family, categories)]


def hardware_categories():
    # Loadable connector RFAs such as Simpson LUS use Structural Connections.
    # OfClass(FamilySymbol) excludes system StructuralConnectionHandler objects.
    return (DB.BuiltInCategory.OST_GenericModel, DB.BuiltInCategory.OST_StructConnections)


def hardware_types(doc):
    categories = hardware_categories()
    return [symbol for category in categories for symbol in types(doc, category)
            if not hardware_family_reason(symbol.Family)]


def hardware_family_reason(family):
    """Accept unhosted points and non-face-hosted work-plane connectors."""
    if family.FamilyPlacementType != DB.FamilyPlacementType.WorkPlaneBased:
        return point_family_reason(family, hardware_categories())
    category = family.FamilyCategory
    if category is None or not any(category.Id.Equals(DB.ElementId(value))
                                  for value in hardware_categories()):
        return 'This work-plane family category is not supported for hardware.'
    if DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family):
        return 'Adaptive families require a separate placement workflow.'
    host = family.get_Parameter(DB.BuiltInParameter.FAMILY_HOSTING_BEHAVIOR)
    if host is not None and host.AsInteger() != 0:
        return ('Family host behavior is {0}; face/wall/floor-hosted hardware '
                'requires a separate placement workflow.').format(host.AsInteger())
    return ''


def family_diagnostics(family):
    category = family.FamilyCategory
    host = family.get_Parameter(DB.BuiltInParameter.FAMILY_HOSTING_BEHAVIOR)
    plane = family.get_Parameter(DB.BuiltInParameter.FAMILY_WORK_PLANE_BASED)
    return dict(name=family.Name, category=category.Name if category else None,
                category_id=id_value(category.Id) if category else None,
                placement=text_type(family.FamilyPlacementType),
                host_behavior=host.AsInteger() if host is not None else None,
                work_plane_based=plane.AsInteger() if plane is not None else None,
                adaptive=bool(DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family)))


def point_family_reason(family, categories):
    category = family.FamilyCategory
    if category is None or not any(category.Id.Equals(DB.ElementId(value)) for value in categories):
        return 'Category {0} is not supported by this picker.'.format(category.Name if category else '(none)')
    if family.FamilyPlacementType != DB.FamilyPlacementType.OneLevelBased:
        return 'Family placement is {0}; unhosted point placement is required.'.format(family.FamilyPlacementType)
    if DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family):
        return 'Adaptive families require a separate placement workflow.'
    for key, label in ((DB.BuiltInParameter.FAMILY_HOSTING_BEHAVIOR, 'host behavior'),
                       (DB.BuiltInParameter.FAMILY_WORK_PLANE_BASED, 'work-plane requirement')):
        parameter = family.get_Parameter(key)
        if parameter is not None and parameter.AsInteger() != 0:
            return 'Family {0} is {1}; unhosted point placement is required.'.format(label, parameter.AsInteger())
    return ''


def type_dimensions(symbol):
    result = {}
    for key, suffix in (('joist_width_in', 'Width'), ('joist_depth_in', 'Depth')):
        for prefix in ('LL_AsGenerated_', 'FT_AsGenerated_'):
            parameter = symbol.LookupParameter(prefix + suffix)
            if parameter is not None and parameter.HasValue:
                result[key] = parameter.AsDouble() * 12.0
                break
    # Common Revit section parameters provide dimensions for ordinary loaded
    # families without assigning treatment/material identity from their names.
    for key, names in (('joist_width_in', ('b', 'Width', 'Section Width')),
                       ('joist_depth_in', ('h', 'Depth', 'Height', 'Section Depth'))):
        if key in result:
            continue
        for name in names:
            parameter = symbol.LookupParameter(name)
            if (parameter is not None and parameter.HasValue and
                    parameter.StorageType == DB.StorageType.Double and
                    parameter.Definition.GetDataType().Equals(DB.SpecTypeId.Length) and
                    parameter.AsDouble() > 0):
                result[key] = parameter.AsDouble() * 12.0
                break
    return result


def type_category(symbol):
    parameter = symbol.LookupParameter('LL_Category')
    if parameter is not None and parameter.HasValue:
        return parameter.AsString()
    name = symbol.Family.Name.upper()
    if name.startswith('FT_PT_'):
        return 'pressure_treated'
    if name.startswith('FT_KD_'):
        return 'untreated_dimensional'
    return 'unknown'


def post_dimensions(symbol):
    """Read column section dimensions without treating overall Height as depth."""
    result={}
    for key,names in (('joist_width_in',('b','Width','Section Width')),
                       ('joist_depth_in',('d','h','Depth','Section Depth'))):
        for name in names:
            parameter=symbol.LookupParameter(name)
            if (parameter is not None and parameter.HasValue and parameter.StorageType==DB.StorageType.Double and
                    parameter.Definition.GetDataType().Equals(DB.SpecTypeId.Length) and parameter.AsDouble()>0):
                result[key]=parameter.AsDouble()*12.0
                break
    return result


def validate_type(doc, settings):
    if not settings['framing_enabled']:
        return None
    uid = settings.get('joist_symbol_uid')
    symbol = doc.GetElement(uid) if uid else None
    if not isinstance(symbol, DB.FamilySymbol) or not symbol.Category.Id.Equals(
            DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming)):
        raise ValueError('Select a loaded Structural Framing type. Generate/test the '
                         'Lumber Library RFAs and load them into this project first.')
    expected = {'Exterior pressure-treated': 'pressure_treated',
                'Interior untreated': 'untreated_dimensional'}.get(settings['exposure'])
    if expected is not None and type_category(symbol) != expected:
        raise ValueError('Selected framing type is {0}; the chosen exposure requires {1}. '
                         'For a loaded family without verified LL/FT treatment metadata, '
                         'choose User-verified engineered/custom and verify its material and section.'
                         .format(type_category(symbol), expected))
    dimensions = type_dimensions(symbol)
    for key, value in dimensions.items():
        if abs(settings[key] - value) > .001:
            raise ValueError('Entered {0} does not match selected type metadata ({1:g} in).'.format(key, value))
    return symbol


def validate_block_type(doc, settings, default_symbol):
    """Resolve a separately selected framing symbol for generated blocking."""
    uid = settings.get('block_symbol_uid')
    symbol = doc.GetElement(uid) if uid else default_symbol
    if not isinstance(symbol, DB.FamilySymbol) or not symbol.Category.Id.Equals(
            DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming)):
        raise ValueError('Select a loaded Structural Framing type for solid blocking.')
    expected = {'Exterior pressure-treated': 'pressure_treated',
                'Interior untreated': 'untreated_dimensional'}.get(settings['exposure'])
    if expected is not None and type_category(symbol) != expected:
        raise ValueError('Selected blocking family category does not match framing exposure. '
                         'Choose a matching LL/FT family, or use user-verified custom framing.')
    dimensions = type_dimensions(symbol)
    for key, dimension_key in (('block_width_in', 'joist_width_in'),
                               ('block_depth_in', 'joist_depth_in')):
        if dimension_key in dimensions:
            if abs(settings[key] - dimensions[dimension_key]) > .001:
                raise ValueError('Entered {0} does not match selected blocking type metadata ({1:g} in).'
                                 .format(key, dimensions[dimension_key]))
    return symbol


def validate_clip_type(doc, settings):
    if not settings['clips_enabled'] or settings['clip_mode'] != 'Loaded family':
        return None
    uid = settings.get('clip_symbol_uid')
    symbol = doc.GetElement(uid) if uid else None
    eligible = set(item.UniqueId for item in clip_types(doc))
    if symbol is None or symbol.UniqueId not in eligible:
        raise ValueError('Choose an unhosted, non-adaptive, point-based Generic Model clip type.')
    schematic = symbol.Family.Name.startswith((rt_clip.FAMILY_NAME, 'DT_CAMO_EDGECLIP_3-16_SCHEMATIC'))
    if schematic and abs(settings['gap_in'] - .1875) > 1.e-7:
        raise ValueError('Selected reused schematic clip family requires a 3/16 inch side gap.')
    return symbol


def validate_hardware_type(doc, unique_id, label):
    if not unique_id:
        return None
    symbol = doc.GetElement(unique_id)
    eligible = set(item.UniqueId for item in hardware_types(doc))
    if symbol is None or symbol.UniqueId not in eligible:
        raise ValueError('Choose a loaded unhosted point-based Generic Model or loadable '
                         'Structural Connections type, or a non-face-hosted work-plane '
                         'type for {0}. Face/wall/floor-hosted, adaptive and line-based '
                         'families require a different placement workflow.'.format(label))
    role={'joist hangers':'hanger','double joist hangers':'double_hanger',
          'hurricane straps':'hurricane','corner straps':'corner'}.get(label)
    if role and not rt_simpson_catalog.role_allowed(symbol_name(symbol),role):
        raise ValueError('This known product belongs to a different connection. Choose a reviewed type for '+label+'.')
    return symbol


def validate_support_types(doc, settings):
    if not settings.get('supports_enabled'):
        return None, None
    symbols = []
    for key, category, width_key, depth_key, label in (
            ('beam_symbol_uid', DB.BuiltInCategory.OST_StructuralFraming,
             'beam_width_in', 'beam_depth_in', 'beam'),
            ('post_symbol_uid', DB.BuiltInCategory.OST_StructuralColumns,
             'post_width_in', 'post_depth_in', 'post')):
        uid = settings.get(key)
        symbol = doc.GetElement(uid) if uid else None
        if not isinstance(symbol, DB.FamilySymbol) or not symbol.Category.Id.Equals(DB.ElementId(category)):
            raise ValueError('Select a loaded {0} family in its structural category.'.format(label))
        expected = {'Exterior pressure-treated': 'pressure_treated',
                    'Interior untreated': 'untreated_dimensional'}.get(settings['exposure'])
        known = type_category(symbol)
        if expected and known in ('pressure_treated', 'untreated_dimensional') and known != expected:
            raise ValueError('Selected {0} treatment metadata conflicts with framing exposure.'.format(label))
        dimensions = post_dimensions(symbol) if label=='post' else type_dimensions(symbol)
        for target, source in ((width_key, 'joist_width_in'), (depth_key, 'joist_depth_in')):
            if source in dimensions and abs(settings[target]-dimensions[source]) > .001:
                raise ValueError('Entered {0} does not match the selected {1} section.'.format(target, label))
        if label == 'post' and (symbol.Family.FamilyPlacementType != DB.FamilyPlacementType.TwoLevelsBased or
                DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(symbol.Family)):
            raise ValueError('Posts require a non-adaptive, two-level Structural Column family.')
        symbols.append(symbol)
    return tuple(symbols)


def axes(anchor, settings):
    base_u = DB.XYZ(anchor['u'][0], anchor['u'][1], 0)
    base_v = DB.XYZ(-base_u.Y, base_u.X, 0)
    origin = DB.XYZ(anchor['origin'][0], anchor['origin'][1], 0)
    frame = rt_geometry.frame(settings)
    origin = origin + base_u*frame['shift'][0] + base_v*frame['shift'][1]
    u = base_u*math.cos(frame['angle']) + base_v*math.sin(frame['angle'])
    v = DB.XYZ(-u.Y, u.X, 0)
    return origin, u, v


def world_point(coord, x, y, z):
    origin, u, v = coord
    return origin + u * x + v * y + DB.XYZ.BasisZ * z


def loop(points):
    result = DB.CurveLoop()
    for i, point in enumerate(points):
        result.Append(DB.Line.CreateBound(point, points[(i+1) % len(points)]))
    loops = List[DB.CurveLoop]()
    loops.Add(result)
    return loops


def extrusion(points, direction, length, material):
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(
        loop(points), direction, length, DB.SolidOptions(material, DB.ElementId.InvalidElementId))


def material(doc, name, color):
    for item in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if item.Name == name:
            return item.Id
    eid = DB.Material.Create(doc, name)
    doc.GetElement(eid).Color = DB.Color(*color)
    return eid


def set_text(element, bip, value):
    parameter = element.get_Parameter(bip)
    if parameter is None or parameter.IsReadOnly:
        raise ValueError('Generated element lacks writable schedule metadata.')
    if not parameter.Set(text_type(value)):
        raise ValueError('Could not set schedule metadata.')


def tag(element, item, layout_id, generation, name):
    write_stamp(element, dict(owner=OWNER, version=VERSION, layout_id=layout_id,
                              generation=generation, role=item['role'], key=item['key'], item=item))
    set_text(element, DB.BuiltInParameter.ALL_MODEL_MARK, layout_id[:8] + '_' + item['key'])
    set_text(element, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
             'RESIDENTIALTOOLS | {0} | {1} | {2}'.format(name, item['role'], item['key']))
    import rt_schedules
    rt_schedules.stamp_generated(element,item,layout_id,name)


def safe_element_name(name):
    """Revit element names cannot contain reserved punctuation/control characters."""
    prohibited = '\\:{}[]|;<>?`~'
    return ''.join('-' if c in prohibited or ord(c)<32 else c
                   for c in text_type(name)).strip() or 'RESIDENTIALTOOLS element'


def shape(doc, geometries, name, layout_id, item):
    result = DB.DirectShape.CreateElement(doc, DB.ElementId(DB.BuiltInCategory.OST_GenericModel))
    result.ApplicationId = OWNER
    result.ApplicationDataId = layout_id + ':' + item['key']
    result.Name = safe_element_name(name)
    geometry = List[DB.GeometryObject]()
    for solid in geometries:
        geometry.Add(solid)
    result.SetShape(geometry)
    return result


def create_board(doc, board, coord, underside, settings, mat, layout_id):
    if board['role'] == 'BORDER' and board['edge_mode']=='square':
        points = [world_point(coord, x, y, underside) for x, y in board['polygon']]
        solid = extrusion(points, DB.XYZ.BasisZ, settings['board_thickness_in']/12.0, mat)
    elif board['role']=='BORDER':
        u=board.get('axis_vector',(0,1) if board.get('axis')=='B' else (1,0)); n=(-u[1],u[0])
        shape2d=board['polygon']; along=[x*u[0]+y*u[1] for x,y in shape2d]; across=[x*n[0]+y*n[1] for x,y in shape2d]
        start,end=min(along),max(along); center=(min(across)+max(across))/2
        profile=rt_board_profile.make_outline(board['width_in'],board['edge_mode'],thickness_in=settings['board_thickness_in'])
        points=[world_point(coord,start*u[0]+(center+y/12.0)*n[0],start*u[1]+(center+y/12.0)*n[1],underside+z/12.0)
                for y,z in profile]
        solid=extrusion(points,coord[1]*u[0]+coord[2]*u[1],end-start,mat)
        trim=extrusion([world_point(coord,x,y,underside) for x,y in shape2d],DB.XYZ.BasisZ,settings['board_thickness_in']/12.0,mat)
        solid=DB.BooleanOperationsUtils.ExecuteBooleanOperation(solid,trim,DB.BooleanOperationsType.Intersect)
    else:
        outline = rt_board_profile.make_outline(board['width_in'], board['edge_mode'],
                                                thickness_in=settings['board_thickness_in'])
        center = (board['low'] + board['high'])/2.0
        points = [world_point(coord, board['start'], center+y/12.0, underside+z/12.0)
                  for y, z in outline]
        solid = extrusion(points, coord[1], board['length_ft'], mat)
        if board.get('polygon'):
            trim = extrusion([world_point(coord,x,y,underside) for x,y in board['polygon']],
                             DB.XYZ.BasisZ,settings['board_thickness_in']/12.0,mat)
            solid = DB.BooleanOperationsUtils.ExecuteBooleanOperation(solid,trim,DB.BooleanOperationsType.Intersect)
    return shape(doc, [solid], 'RT Composite ' + board['key'], layout_id, board)


def geometry_solids(geometry):
    for item in geometry:
        if isinstance(item, DB.Solid) and item.Volume > 1.e-9:
            yield item
        elif isinstance(item, DB.GeometryInstance):
            for solid in geometry_solids(item.GetInstanceGeometry()):
                yield solid


def vertices(element):
    result = []
    geometry = element.get_Geometry(DB.Options())
    if geometry is not None:
        for solid in geometry_solids(geometry):
            for face in solid.Faces:
                result.extend(face.Triangulate().Vertices)
    if not result:
        raise ValueError('Structural family produced no measurable 3D solids: ' + element.UniqueId)
    return result


def create_member(doc, member, coord, underside, settings, symbol, level):
    a = world_point(coord, member['a'][0], member['a'][1], underside)
    b = world_point(coord, member['b'][0], member['b'][1], underside)
    result = doc.Create.NewFamilyInstance(DB.Line.CreateBound(a, b), symbol, level, StructuralType.Beam)
    if result is None:
        raise ValueError('Revit could not create structural framing instance.')
    StructuralFramingUtils.DisallowJoinAtEnd(result, 0)
    StructuralFramingUtils.DisallowJoinAtEnd(result, 1)
    doc.Regenerate()
    points = vertices(result)
    # Use measured solid top, handling both the centered LL section and FT's
    # top-origin sections without guessing numeric justification enum values.
    delta = underside - max(p.Z for p in points)
    if abs(delta) > LENGTH_TOL:
        DB.ElementTransformUtils.MoveElement(doc, result.Id, DB.XYZ(0, 0, delta))
        doc.Regenerate()
        points = vertices(result)
    along = (b-a).Normalize()
    across = DB.XYZ(-along.Y, along.X, 0)
    expected_width = member.get('section_width_in', settings['joist_width_in']) / 12.0
    expected_depth = member.get('section_depth_in', settings['joist_depth_in']) / 12.0
    checks = [(max(p.DotProduct(along) for p in points)-min(p.DotProduct(along) for p in points), a.DistanceTo(b), 'length'),
              (max(p.DotProduct(across) for p in points)-min(p.DotProduct(across) for p in points), expected_width, 'width'),
              (max(p.Z for p in points)-min(p.Z for p in points), expected_depth, 'depth'),
              (max(p.Z for p in points), underside, 'top'),
              ((max(p.DotProduct(across) for p in points)+min(p.DotProduct(across) for p in points))/2.0,
               a.DotProduct(across), 'lateral center'),
              (min(p.DotProduct(along) for p in points), min(a.DotProduct(along), b.DotProduct(along)), 'start'),
              (max(p.DotProduct(along) for p in points), max(a.DotProduct(along), b.DotProduct(along)), 'end')]
    for measured, expected, label in checks:
        if abs(measured-expected) > LENGTH_TOL:
            raise ValueError('Family geometry {0} mismatch on {1}: expected {2:g} ft, got {3:g}. '
                             'Check family flex/offsets; entire rebuild will roll back.'.format(
                                 label, member['key'], expected, measured))
    return result


def create_post(doc, item, coord, underside, symbol, level, log=None):
    top = underside + item['top_offset_in']/12.0
    bottom = top - item['height_ft']
    point = world_point(coord, item['x'], item['y'], bottom)
    result = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.Column)
    if result is None:
        raise ValueError('Revit could not create post ' + item['key'])
    # Both constraints reference the chosen project level, with explicit offsets.
    # Lower the base first, then set the top offset and level. Avoid an interim
    # top below the base when both constraints reference the same level.
    for bip, value in ((DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, level.Id),
                       (DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM, bottom-level.Elevation),
                       (DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM, top-level.Elevation),
                       (DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, level.Id)):
        parameter = result.get_Parameter(bip)
        if parameter is None or parameter.IsReadOnly or not parameter.Set(value):
            raise ValueError('Post family lacks writable base/top constraints: ' + item['key'])
    doc.Regenerate()
    local=math.radians(item.get('rotation_deg',0))
    post_u=(coord[1]*math.cos(local)+coord[2]*math.sin(local)).Normalize()
    post_v=DB.XYZ(-post_u.Y,post_u.X,0)
    # Revit may create a column with an existing insertion rotation. Rotate TO
    # the planned axes rather than adding the deck angle to that rotation.
    transform=result.GetTransform()
    current=transform.BasisX
    if abs(current.Z)>1.e-7 or abs(abs(transform.BasisZ.Z)-1)>1.e-7:
        raise ValueError('Post '+item['key']+' must be a vertical column; slanted posts are unsupported.')
    current_angle=math.atan2(current.Y,current.X)
    desired_angle=math.atan2(post_u.Y,post_u.X)
    angle=math.atan2(math.sin(desired_angle-current_angle),math.cos(desired_angle-current_angle))
    family_label=symbol_name(symbol)
    if log:
        log('Post {0}; family/type={1}; requested section={2:g} x {3:g} in; '
            'initial rotation={4:g} deg; target={5:g} deg; correction={6:g} deg.'
            .format(item['key'],family_label,item['width_in'],item['depth_in'],
                    math.degrees(current_angle),math.degrees(desired_angle),math.degrees(angle)))
    if abs(angle) > 1.e-9:
        DB.ElementTransformUtils.RotateElement(doc, result.Id,
            DB.Line.CreateBound(point, point+DB.XYZ.BasisZ), angle)
    doc.Regenerate()
    if result.GetTransform().BasisX.Normalize().DotProduct(post_u)<.999999:
        raise ValueError('Could not align post '+item['key']+' to its planned beam axes. Rebuild will roll back.')
    points = vertices(result)
    # A custom column's insertion origin can be at a corner or offset from its
    # solid. Center its actual section under the planned beam support point.
    shift=DB.XYZ(0,0,0)
    for axis in (post_u,post_v):
        center=(max(p.DotProduct(axis) for p in points)+min(p.DotProduct(axis) for p in points))/2.0
        shift=shift+axis*(point.DotProduct(axis)-center)
    if shift.GetLength()>LENGTH_TOL:
        DB.ElementTransformUtils.MoveElement(doc,result.Id,shift)
        doc.Regenerate()
        points=vertices(result)
        if log: log('Post '+item['key']+' section centered under beam; horizontal adjustment={0:g} in.'.format(shift.GetLength()*12))
    checks = [(min(p.Z for p in points), bottom, 'base'), (max(p.Z for p in points), top, 'top')]
    for axis, dimension, label in ((post_u, item['width_in']/12.0, 'width'),
                                    (post_v, item['depth_in']/12.0, 'depth')):
        low, high = min(p.DotProduct(axis) for p in points), max(p.DotProduct(axis) for p in points)
        checks.extend([(high-low, dimension, label), ((high+low)/2.0, point.DotProduct(axis), label+' center')])
    if log:
        log('Post '+item['key']+' geometry checks (inches): '+json.dumps(
            [dict(check=label,actual=measured*12,expected=expected*12) for measured,expected,label in checks]))
    for measured, expected, label in checks:
        if abs(measured-expected) > LENGTH_TOL:
            raise ValueError('Post {0} geometry {1} mismatch for {2}; expected {3:g} in, got {4:g} in. '
                             'Check the selected post type and actual section under Supports. '
                             'Alignment was checked; incompatible family geometry still rolls back the rebuild.'
                             .format(item['key'],label,family_label,expected*12,measured*12))
    return result


def schematic_clip_solids(coord, clip, underside, materials):
    result = []
    angle=math.radians(clip.get('rotation_deg',0)); c,s=math.cos(angle),math.sin(angle)
    for outline, z, height, kind in rt_clip.parts():
        points = [world_point(coord, clip['x']+(c*x-s*y)/12.0, clip['y']+(s*x+c*y)/12.0, underside+z/12.0)
                  for x, y in outline]
        result.append(extrusion(points, DB.XYZ.BasisZ, height/12.0, materials[kind]))
    return result


def create_clip(doc, clip, coord, underside, level, symbol, materials, layout_id):
    if symbol is None:
        return shape(doc, schematic_clip_solids(coord, clip, underside, materials),
                     'RT Generic CAMO-style schematic clip', layout_id, clip)
    point = world_point(coord, clip['x'], clip['y'], underside)
    result = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
    if result is None:
        raise ValueError('Clip family instance could not be created.')
    current=result.GetTransform().BasisX
    angle = math.atan2(coord[1].Y, coord[1].X)+math.radians(clip.get('rotation_deg',0))-math.atan2(current.Y,current.X)
    angle=math.atan2(math.sin(angle),math.cos(angle))
    if abs(angle) > 1.e-9:
        DB.ElementTransformUtils.RotateElement(doc, result.Id,
            DB.Line.CreateBound(point, point+DB.XYZ.BasisZ), angle)
    return result


def create_face_fastener(doc,item,coord,top,steel,layout_id):
    solids=[]
    for radius,z,height in ((.055,-1.75,1.73),(.13,-.02,.04)):
        points=[world_point(coord,item['x']+x/12.0,item['y']+y/12.0,top+z/12.0) for x,y in rt_clip.octagon(radius)]
        solids.append(extrusion(points,DB.XYZ.BasisZ,height/12.0,steel))
    return shape(doc,solids,'RT Schematic deck face screw',layout_id,item)


def create_hardware_nail(doc,item,steel,layout_id):
    """One countable shank/head element; no manufacturer nail CAD is implied."""
    p=DB.XYZ(*item['head']); axis=DB.XYZ(*item['direction']).Normalize()
    u=axis.CrossProduct(DB.XYZ.BasisZ if abs(axis.Z)<.9 else DB.XYZ.BasisX).Normalize()
    v=axis.CrossProduct(u);solids=[]
    for radius,start,length in ((item['diameter_in']/2.0,0,item['nail_length_in']),
                                (item['diameter_in']*1.05,-.035,.035)):
        ring=[p+axis*(start/12.0)+u*(x/12.0)+v*(y/12.0) for x,y in rt_clip.octagon(radius)]
        solids.append(extrusion(ring,axis,length/12.0,steel))
    return shape(doc,solids,'RT '+item['product'],layout_id,item)


def create_hardware_plane(doc, coord, underside, layout_id, generation, plane_key='hardware', fit=None):
    """Create one owned horizontal host; keep it out of connector quantities."""
    if fit is not None:
        return rt_connector_placement.create_plane(doc,fit['origin'],fit['normal'],fit['direction'],
            'RT Hardware '+layout_id[:8]+' '+generation[:8]+' '+plane_key,DB)
    origin = world_point(coord, 0, 0, underside)
    result = doc.Create.NewReferencePlane(origin + coord[1], origin, coord[2], doc.ActiveView)
    if result is None:
        raise ValueError('Revit could not create the hardware work plane.')
    result.Name = 'RT Hardware ' + layout_id[:8] + ' ' + generation[:8] + ' ' + plane_key
    doc.Regenerate()
    if result.GetPlane().Normal.DotProduct(DB.XYZ.BasisZ) < 0:
        result.Flip()
        doc.Regenerate()
    if result.GetPlane().Normal.DotProduct(DB.XYZ.BasisZ) < .999999:
        raise ValueError('Hardware work plane must face upward horizontally.')
    if result.GetReference() is None:
        raise ValueError('Hardware work plane has no usable reference.')
    return result


def hardware_direction(item,coord):
    """Desired family local X, relative to the actual member and deck axes."""
    if item.get('direction'):
        dx,dy=item['direction']
        # Family local Y follows the member into the supported span.
        angle=math.atan2(dy,dx)-math.pi/2
    else:
        angle=math.radians(item.get('rotation_deg',0))+(math.pi if item.get('end')==1 else 0)
    angle+=math.radians(item.get('family_rotation_deg',0))
    v=coord[2] if len(coord)>2 else DB.XYZ(-coord[1].Y,coord[1].X,0)
    return coord[1]*math.cos(angle)+v*math.sin(angle)


def create_hardware(doc, item, coord, underside, level, symbol, hardware_plane=None, profile=None, fit=None):
    """Place a native point or work-plane connector at its planned joint point."""
    if profile is not None:
        return rt_connector_placement.create(doc,item,profile,fit,symbol,level,hardware_plane,DB,StructuralType.NonStructural)
    point = world_point(coord, item['x'], item['y'], underside + item.get('z_offset_in', 0)/12.0)
    direction=hardware_direction(item,coord)
    if symbol.Family.FamilyPlacementType == DB.FamilyPlacementType.WorkPlaneBased:
        if hardware_plane is None:
            raise ValueError('Work-plane hardware requires a managed reference plane: ' + item['key'])
        plane = hardware_plane.GetPlane()
        if abs((point - plane.Origin).DotProduct(plane.Normal)) > LENGTH_TOL:
            raise ValueError('Hardware insertion point is outside its managed plane: ' + item['key'])
        # Reference direction sets rotation in the host plane. Do not rotate the
        # hosted instance afterwards or use the level/XYZ overload for this RFA.
        result = doc.Create.NewFamilyInstance(hardware_plane.GetReference(), point, direction, symbol)
        if result is None:
            raise ValueError('Work-plane hardware could not be created: ' + item['key'])
        return result
    if symbol.Category.Id.Equals(DB.ElementId(DB.BuiltInCategory.OST_StructConnections)):
        result = doc.Create.NewFamilyInstance(point, symbol, StructuralType.NonStructural)
    else:
        result = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
    if result is None:
        raise ValueError('Hardware family instance could not be created: ' + item['key'])
    doc.Regenerate()
    current=result.GetTransform().BasisX
    angle=math.atan2(direction.Y,direction.X)-math.atan2(current.Y,current.X)
    angle=math.atan2(math.sin(angle),math.cos(angle))
    if abs(angle) > 1.e-9:
        DB.ElementTransformUtils.RotateElement(doc, result.Id,
            DB.Line.CreateBound(point, point+DB.XYZ.BasisZ), angle)
    return result


def registered_elements(doc, record, require_editable=True):
    result, missing = [], []
    if record is None:
        return result, missing
    for uid in record['element_uids']:
        element = doc.GetElement(uid)
        if element is None:
            missing.append(uid)
            continue
        if not owned_registered(record, read_stamp(element), uid):
            raise ValueError('Ownership changed for registered element. Rebuild refuses to delete it: ' + uid)
        if require_editable and (element.Pinned or not element.GroupId.Equals(DB.ElementId.InvalidElementId)):
            raise ValueError('Generated element is pinned or grouped. Unpin/ungroup before rebuilding: ' + uid)
        result.append(element)
    return result, missing


def rebuild(doc, data_storage, record, anchor, planned, log):
    schema()
    s = planned['settings']
    level = doc.GetElement(s['level_uid']) if s.get('level_uid') else None
    if not isinstance(level, DB.Level):
        raise ValueError('Select a valid project Level.')
    if anchor.get('roof_projection'):
        if s.get('supports_enabled'):
            raise ValueError('Projected roof-deck mode builds level boards/framing. Roof stanchions and bases are not implemented; disable freestanding beams/posts and use reviewed roof supports.')
        framing_bottom=level.Elevation+s['height_in']/12.0-(s['joist_depth_in']/12.0 if s['framing_enabled'] else 0)
        if framing_bottom<anchor['source_peak_ft']+s['roof_clearance_in']/12.0-LENGTH_TOL:
            raise ValueError('Increase deck elevation to maintain the chosen framing clearance above the sloped Floor peak.')
    joist_symbol = validate_type(doc, s)
    beam_symbol, post_symbol = validate_support_types(doc, s)
    rt_simpson_catalog.validate_selections(s, type_category(joist_symbol) if joist_symbol else None)
    block_symbol = (validate_block_type(doc, s, joist_symbol)
                    if any(item['role'] in ('BLOCK','BORDER_BACKING') for item in planned['members']) else None)
    clip_symbol = validate_clip_type(doc, s)
    hardware_symbols = {
        'HANGER': validate_hardware_type(doc, s.get('hanger_symbol_uid'), 'joist hangers'),
        'DOUBLE_HANGER': validate_hardware_type(doc, s.get('double_hanger_symbol_uid'), 'double joist hangers'),
        'HURRICANE_STRAP': validate_hardware_type(doc, s.get('hurricane_symbol_uid'), 'hurricane straps'),
        'CORNER_STRAP': validate_hardware_type(doc, s.get('corner_strap_symbol_uid'), 'corner straps')}
    old, missing = registered_elements(doc, record)
    layout_id = record['layout_id'] if record else str(uuid.uuid4())
    unregistered = []
    known_uids = set(record['element_uids']) if record else set()
    for element in DB.FilteredElementCollector(doc).WherePasses(ExtensibleStorageFilter(SCHEMA_GUID)):
        stamp = read_stamp(element)
        if (stamp.get('owner') == OWNER and stamp.get('layout_id') == layout_id and
                stamp.get('role') != 'LAYOUT' and element.UniqueId not in known_uids):
            unregistered.append(element.UniqueId)
    generation = str(uuid.uuid4())
    coord = axes(anchor, s)
    underside = level.Elevation + s['height_in']/12.0
    generated, item_records = [], []
    with transaction(doc, 'RESIDENTIALTOOLS | coordinated rebuild ' + s['name'], log):
        if joist_symbol is not None:
            joist_symbol.Activate()
        if block_symbol is not None:
            block_symbol.Activate()
        if clip_symbol is not None:
            clip_symbol.Activate()
        for symbol in (beam_symbol, post_symbol):
            if symbol is not None:
                symbol.Activate()
        for symbol in hardware_symbols.values():
            if symbol is not None:
                symbol.Activate()
        doc.Regenerate()
        connector_profiles=rt_connector_placement.build_profiles(doc,hardware_symbols,planned['hardware'],
            level,DB,StructuralType.NonStructural,log)
        board_mat = material(doc, 'RT_Composite_Schematic', (121, 91, 65))
        clip_mats = dict(nylon=material(doc, 'RT_Clip_Nylon_Schematic', (32, 35, 41)),
                         steel=material(doc, 'RT_Clip_Steel_Schematic', (164, 172, 177)))
        for item in planned['boards']:
            element = create_board(doc, item, coord, underside, s, board_mat, layout_id)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned['members']:
            member_symbol = block_symbol if item['role'] in ('BLOCK','BORDER_BACKING') else joist_symbol
            element = create_member(doc, item, coord, underside, s, member_symbol, level)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned['clips']:
            element = create_clip(doc, item, coord, underside, level, clip_symbol, clip_mats, layout_id)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned.get('face_fasteners',[]):
            element=create_face_fastener(doc,item,coord,underside+s['board_thickness_in']/12.0,clip_mats['steel'],layout_id)
            tag(element,item,layout_id,generation,s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId,element_id=id_value(element.Id),item=item))
        for item in [ply for beam in planned.get('beams', []) for ply in beam_ply_items(beam)]:
            element = create_member(doc, item, coord, underside+item['z_offset_in']/12.0, s, beam_symbol, level)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned.get('posts', []):
            element = create_post(doc, item, coord, underside, post_symbol, level, log=log)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        hardware_planes = {};nail_records=[];nail_notes=[]
        nail_steel=(material(doc,'RT_Hardware_Nails_'+s.get('hardware_nail_finish','Unspecified - review').split(' - ')[0].replace(' ','_')+'_Schematic',
                             (164,172,177)) if s.get('hardware_nails_enabled',True) and planned['hardware'] else clip_mats['steel'])
        for item in planned['hardware']:
            symbol = hardware_symbols[item['role']]
            if symbol is None:
                raise ValueError('No loaded family selected for planned hardware role ' + item['role'])
            hardware_plane = None
            profile,fit=None,None
            if item['role'] in rt_connector_placement.ROLES:
                profile=connector_profiles[(item['role'],symbol.UniqueId,item.get('width_in'),item.get('depth_in'))]
                fit=rt_connector_placement.placement(profile,item,coord,underside)
                item=dict(item,measured_contact=dict(datum_ft=fit['datum'],axes=fit['target'],family_origin_ft=fit['origin']))
            if symbol.Family.FamilyPlacementType == DB.FamilyPlacementType.WorkPlaneBased:
                elevation = underside + item.get('z_offset_in', 0)/12.0
                plane_key = fit['plane_key'] if fit else round(elevation, 8)
                if plane_key not in hardware_planes:
                    name_key = 'plane-{0}'.format(len(hardware_planes)+1)
                    hardware_plane = create_hardware_plane(doc, coord, elevation, layout_id, generation, name_key,fit)
                    plane_item = dict(role='HARDWARE_PLANE', key=name_key,
                                      elevation_ft=elevation, normal=fit['normal'] if fit else [0, 0, 1])
                    # Reference planes have no writable Mark/Comments fields.
                    write_stamp(hardware_plane, dict(owner=OWNER, version=VERSION, layout_id=layout_id,
                                generation=generation, role=plane_item['role'], key=plane_item['key'], item=plane_item))
                    generated.append(hardware_plane)
                    item_records.append(dict(unique_id=hardware_plane.UniqueId,
                                              element_id=id_value(hardware_plane.Id), item=plane_item))
                    hardware_planes[plane_key] = hardware_plane
                    log('Hardware host plane: id={0}; normal={1}; equation={2}; '
                        'placement/fit require Revit review.'.format(id_value(hardware_plane.Id),plane_item['normal'],plane_key))
                hardware_plane = hardware_planes[plane_key]
            try:
                log('Hardware request: family={0}; item={1}; native origin/seat fit requires review.'.format(
                    symbol_name(symbol),json.dumps(item)))
                element = create_hardware(doc, item, coord, underside, level, symbol, hardware_plane,profile,fit)
            except Exception:
                log('Hardware placement failed: item={0}; family={1}; diagnostics={2}'.format(
                    json.dumps(item), symbol_name(symbol), json.dumps(family_diagnostics(symbol.Family))))
                raise
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
            if profile is not None and s.get('hardware_nails_enabled',True):
                nails,notes=rt_hardware_nails.nail_items(profile,fit,item,symbol_name(symbol),s)
                nail_notes.extend(note for note in notes if note not in nail_notes)
                if len(generated)+len(nails)>15000:raise ValueError('Layout including individual hardware nails exceeds 15,000 elements.')
                for nail in nails:
                    try:nail_element=create_hardware_nail(doc,nail,nail_steel,layout_id)
                    except Exception:
                        log('Individual connector nail failed: '+json.dumps(nail));raise
                    tag(nail_element,nail,layout_id,generation,s['name']);generated.append(nail_element)
                    item_records.append(dict(unique_id=nail_element.UniqueId,element_id=id_value(nail_element.Id),item=nail))
                    nail_records.append(nail)
        # Creating and checking new geometry BEFORE deleting the previous layout
        # means every failure leaves the previous layout intact via rollback.
        old_ids = List[DB.ElementId]()
        old_values = set()
        for element in old:
            old_ids.Add(element.Id)
            old_values.add(id_value(element.Id))
        if old:
            deleted = set(id_value(eid) for eid in doc.Delete(old_ids))
            validate_deletion_scope(old_values, deleted)
        if data_storage is None:
            data_storage = DataStorage.Create(doc)
        result = dict(owner=OWNER, version=VERSION, role='LAYOUT', layout_id=layout_id,
                      generation=generation, settings=s, anchor=anchor,
                      element_uids=[element.UniqueId for element in generated],
                      items=item_records, counts=dict(planned['counts']), warnings=list(planned['warnings'])+nail_notes,
                      skipped_hanger_connections=planned.get('skipped_hanger_connections', []),
                      unsupported_border_fasteners=planned.get('unsupported_border_fasteners',[]),
                      managed_hardware_planes=len(hardware_planes),
                      missing_previous_elements=missing,
                      preserved_unregistered_tagged_copies=unregistered,
                      joist_type=symbol_name(joist_symbol) if joist_symbol else None,
                      blocking_type=symbol_name(block_symbol) if block_symbol else None,
                      beam_type=symbol_name(beam_symbol) if beam_symbol else None,
                      post_type=symbol_name(post_symbol) if post_symbol else None,
                      clip_type=symbol_name(clip_symbol) if clip_symbol else 'Generic CAMO-style schematic solids',
                      hardware_types=dict((role, symbol_name(symbol) if symbol else None)
                                          for role, symbol in hardware_symbols.items()))
        if nail_records or 'hardware_nails' in result['counts']:
            result['counts']['hardware_nails']=len(nail_records)
            result['counts']['nails_at_measured_holes']=sum(n['measured_hole'] for n in nail_records)
        result['connector_nail_schedules']=[dict(connector_key=item['key'],
            schedule=rt_hardware_nails.schedule(symbol_name(hardware_symbols[item['role']]),s))
            for item in planned['hardware']] if s.get('hardware_nails_enabled',True) else []
        import rt_code_review
        result['code_review']=rt_code_review.review(planned)
        if unregistered:
            result['warnings'].append('{0} unregistered tagged copies were preserved and '
                                      'excluded from managed layout counts.'.format(len(unregistered)))
        write_stamp(data_storage, result)
        doc.Regenerate()
        for element in generated:
            if doc.GetElement(element.Id) is None:
                raise ValueError('Generated element disappeared before commit.')
    log('COMMITTED layout {0}; counts={1}; removed={2}; missing={3}'.format(
        layout_id, result['counts'], len(old), len(missing)))
    return result


def generate_clip_family(app, template, path, log):
    doc = app.NewFamilyDocument(template)
    if doc is None:
        raise ValueError('Could not open Generic Model template.')
    try:
        category = doc.OwnerFamily.FamilyCategory
        if category is None or not category.Id.Equals(DB.ElementId(DB.BuiltInCategory.OST_GenericModel)):
            raise ValueError('Clip RFA requires a Generic Model template.')
        if doc.OwnerFamily.FamilyPlacementType != DB.FamilyPlacementType.OneLevelBased:
            raise ValueError('Use an unhosted Generic Model.rft, not a face/work-plane/line template.')
        with transaction(doc, 'RT schematic clip family', log):
            manager = doc.FamilyManager
            if manager.CurrentType is None:
                manager.NewType('3-16 Gap - Schematic')
            else:
                manager.RenameCurrentType('3-16 Gap - Schematic')
            mats = dict(nylon=material(doc, 'RT_Clip_Nylon_Schematic', (32, 35, 41)),
                        steel=material(doc, 'RT_Clip_Steel_Schematic', (164, 172, 177)))
            for outline, z, height, kind in rt_clip.parts():
                points = [DB.XYZ(x/12.0, y/12.0, z/12.0) for x, y in outline]
                profile = DB.CurveArray()
                for i, point in enumerate(points):
                    profile.Append(DB.Line.CreateBound(point, points[(i+1) % len(points)]))
                profiles = DB.CurveArrArray()
                profiles.Append(profile)
                sketch = DB.SketchPlane.Create(doc, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, points[0]))
                form = doc.FamilyCreate.NewExtrusion(True, profiles, sketch, height/12.0)
                form.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM).Set(mats[kind])
            param = manager.AddParameter('RT_Model_Status', DB.GroupTypeId.IdentityData, DB.SpecTypeId.String.Text, False)
            manager.Set(param, 'Generic schematic; not CAMO CAD; not manufacturer approved')
            doc.Regenerate()
        options = DB.SaveAsOptions()
        options.OverwriteExistingFile = False
        doc.SaveAs(path, options)
    finally:
        if not doc.Close(False):
            raise RuntimeError('Schematic clip family document did not close.')
