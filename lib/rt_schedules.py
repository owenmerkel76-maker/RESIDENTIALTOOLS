# -*- coding: utf-8 -*-
"""Owned native category schedules and shared instance takeoff parameters."""
import io
import math
import os
import re
import uuid
from System import Guid
from Autodesk.Revit import DB
import rt_revit as api
from rt_layout import OWNER,VERSION

FIELDS=(('scope','RTD_Scope','text','Managed scope'),('layout','RTD_Layout','text','Deck'),
        ('component','RTD_Component','text','Component'),('product','RTD_Product','text','Family / product'),
        ('section','RTD_Section','text','Actual section (in)'),('material','RTD_Material','text','Material'),
        ('group','RTD_ProductKey','text','Product grouping key'),
        ('cut','RTD_CutLength_ft','number','Cut length (ft)'),('total','RTD_TotalLength_ft','number','Total length (ft)'),
        ('assembly','RTD_Assembly','text','Beam assembly'),('ply','RTD_Ply','integer','Ply'))
NAMESPACE=uuid.UUID('66f42329-f9e5-44b1-9db5-714d5de6e818')
PREFIX='RTD|'
GUIDS=dict((field[0],Guid(str(uuid.uuid5(NAMESPACE,field[0])))) for field in FIELDS)


def field_guid(key): return GUIDS[key]


def scope_token(layout_id): return PREFIX+layout_id


def row_values(row):
    width,depth=row.get('width_in'),row.get('depth_in')
    section=('{0:g} x {1:g}'.format(float(width),float(depth)) if width and depth else '')
    role=row['role']; component='Beam ply' if role=='BEAM' else role.replace('_',' ').title()
    if role=='HARDWARE_NAIL':component='Hardware nail / '+row.get('application','')
    if role=='BORDER' and row.get('board_kind')=='breaker': component='Breaker board'
    length=float(row.get('length_ft',0))
    material=', '.join(row.get('materials',[]))
    return dict(scope=scope_token(row['layout_id']),layout=row['layout_name'],component=component,
                product=row['type_name'],section=section,material=', '.join(row.get('materials',[])),
                group=row['type_name']+' | '+section+' | '+material,
                cut=round(length,6),total=length,assembly=row.get('assembly_key',''),ply=int(row.get('ply_index',0)))


def set_values(element,values,required=False):
    for key,name,kind,heading in FIELDS:
        parameter=element.get_Parameter(field_guid(key))
        if parameter is None:
            if required: raise ValueError('Missing schedule parameter '+name+' on '+element.UniqueId)
            continue
        if parameter.IsReadOnly or not parameter.Set(values[key]):
            raise ValueError('Could not update schedule parameter '+name+' on '+element.UniqueId)


def stamp_generated(element,item,layout_id,name):
    # No binding is created during a build. If schedules were enabled already,
    # keep their counts and planned lengths populated after replacement.
    if item['role']=='HARDWARE_PLANE' or element.get_Parameter(field_guid('scope')) is None: return
    length=item.get('length_ft',item.get('height_ft',0))
    if 'a' in item: length=math.hypot(item['b'][0]-item['a'][0],item['b'][1]-item['a'][1])
    product=api.symbol_name(element.Symbol) if isinstance(element,DB.FamilyInstance) else (
        'Schematic composite' if item['role'] in ('BOARD','BORDER') else
        'Generic schematic clip' if item['role']=='CLIP' else
        'Schematic deck face screw' if item['role']=='FACE_FASTENER' else
        item['product']+' | '+item['application'] if item['role']=='HARDWARE_NAIL' else item['role'].title())
    materials=[element.Document.GetElement(mid).Name for mid in element.GetMaterialIds(False)]
    row=dict(item,layout_id=layout_id,layout_name=name,type_name=product,length_ft=length,materials=materials,
             width_in=item.get('width_in',item.get('section_width_in','')),
             depth_in=item.get('depth_in',item.get('section_depth_in','')))
    set_values(element,row_values(row))


def definitions(app,path):
    # Use our own temporary definitions file and restore the user's global
    # shared-parameter setting on every success/failure path.
    with io.open(path,'w',encoding='utf-8') as stream:
        stream.write(u'# RESIDENTIALTOOLS generated parameter definitions\n*META\tVERSION\tMINVERSION\nMETA\t2\t1\n'
                     u'*GROUP\tID\tNAME\n*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tDESCRIPTION\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n')
    original=app.SharedParametersFilename
    try:
        app.SharedParametersFilename=path
        file=app.OpenSharedParameterFile()
        if file is None: raise ValueError('Revit could not open the temporary takeoff parameter file.')
        group=file.Groups.Create('RESIDENTIALTOOLS takeoff')
        result={}
        for key,name,kind,heading in FIELDS:
            spec=DB.SpecTypeId.String.Text if kind=='text' else DB.SpecTypeId.Int.Integer if kind=='integer' else DB.SpecTypeId.Number
            options=DB.ExternalDefinitionCreationOptions(name,spec); options.GUID=field_guid(key)
            options.Description='RESIDENTIALTOOLS managed schedule data; refresh Material List after manual edits.'
            result[key]=group.Definitions.Create(options)
        return result
    finally: app.SharedParametersFilename=original


def bind_parameters(doc,categories,path):
    external=definitions(doc.Application,path); existing={}
    iterator=doc.ParameterBindings.ForwardIterator(); iterator.Reset()
    own_names=set(field[1] for field in FIELDS)
    while iterator.MoveNext():
        if iterator.Key.Name in own_names:
            if iterator.Key.Name in existing: raise ValueError('Ambiguous duplicate schedule parameter: '+iterator.Key.Name)
            existing[iterator.Key.Name]=(iterator.Key,iterator.Current)
    result={}
    for key,name,kind,heading in FIELDS:
        shared=DB.SharedParameterElement.Lookup(doc,field_guid(key))
        old=existing.get(name)
        if old and (shared is None or not old[0].Id.Equals(shared.Id)):
            raise ValueError('Parameter name conflict: '+name+'. An unrelated parameter will not be replaced.')
        category_set=doc.Application.Create.NewCategorySet()
        current_ids=set()
        if old:
            if not isinstance(old[1],DB.InstanceBinding): raise ValueError(name+' must be an instance parameter.')
            for category in old[1].Categories:
                category_set.Insert(category); current_ids.add(api.id_value(category.Id))
        for category in categories:
            if not category.AllowsBoundParameters: raise ValueError('Category does not allow takeoff parameters: '+category.Name)
            category_set.Insert(category)
        requested=set(api.id_value(category.Id) for category in categories)
        if not old or not requested.issubset(current_ids):
            binding=doc.Application.Create.NewInstanceBinding(category_set)
            definition=old[0] if old else external[key]
            success=(doc.ParameterBindings.ReInsert(definition,binding,DB.GroupTypeId.Data) if old else
                     doc.ParameterBindings.Insert(definition,binding,DB.GroupTypeId.Data))
            if not success: raise ValueError('Could not bind '+name+' to schedule categories.')
        result[key]=DB.SharedParameterElement.Lookup(doc,field_guid(key)).Id
    doc.Regenerate()
    return result


def owned_schedule(doc,scope,category_id):
    found=[]
    for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        stamp=api.read_stamp(view)
        if stamp.get('owner')==OWNER and stamp.get('role')=='MATERIAL_SCHEDULE' and stamp.get('schedule_scope')==scope and stamp.get('category_id')==category_id:
            found.append(view)
    if len(found)>1: raise ValueError('Duplicate owned material schedules; review copies in the Project Browser.')
    return found[0] if found else None


def configure_schedule(view,ids,scope):
    definition=view.Definition
    definition.ClearFilters(); definition.ClearSortGroupFields(); definition.ClearFields()
    available=dict((api.id_value(field.ParameterId),field) for field in definition.GetSchedulableFields())
    fields={}
    for key in ('scope','layout','component','product','section','cut','total','material','assembly','ply','group'):
        if api.id_value(ids[key]) not in available: raise ValueError('Revit cannot schedule required takeoff field '+key)
        field=definition.AddField(available[api.id_value(ids[key])]); fields[key]=field
        field.ColumnHeading=next(spec[3] for spec in FIELDS if spec[0]==key)
        field.GridColumnWidth=.9 if key in ('layout','component','section','material') else 1.8 if key=='product' else .65
        field.IsHidden=key in ('scope','assembly','ply','group')
        if key=='total': field.DisplayType=DB.ScheduleFieldDisplayType.Totals
    count=definition.AddField(DB.ScheduleFieldType.Count); count.ColumnHeading='Pieces'; count.GridColumnWidth=.55
    # Revit supports at most four sort/group fields. A compound product key
    # includes section/material; separate layouts/components retain identity.
    for key in ('layout','component','group','cut'):
        definition.AddSortGroupField(DB.ScheduleSortGroupField(fields[key].FieldId))
    definition.IsItemized=False
    definition.ShowGrandTotal=True; definition.ShowGrandTotalCount=True; definition.ShowGrandTotalTitle=True
    definition.GrandTotalTitle='Installed totals'
    kind=DB.ScheduleFilterType.BeginsWith if scope=='all' else DB.ScheduleFilterType.Equal
    definition.AddFilter(DB.ScheduleFilter(fields['scope'].FieldId,kind,PREFIX if scope=='all' else scope_token(scope)))


def refresh(doc,rows,scope,folder,log):
    elements=dict((row['unique_id'],doc.GetElement(row['unique_id'])) for row in rows)
    categories=dict((api.id_value(element.Category.Id),element.Category) for element in elements.values())
    for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule):
        stamp=api.read_stamp(view)
        if stamp.get('owner')==OWNER and stamp.get('role')=='MATERIAL_SCHEDULE':
            category=DB.Category.GetCategory(doc,DB.ElementId(stamp['category_id']))
            if category is not None: categories[stamp['category_id']]=category
    if not categories: raise ValueError('No current pieces or existing managed schedules to refresh.')
    views=[]; excluded=0
    with api.transaction(doc,'RESIDENTIALTOOLS | refresh material schedules',log):
        ids=bind_parameters(doc,list(categories.values()),os.path.join(folder,'schedule_parameters.txt'))
        # Only our dedicated membership parameter is cleared on copied pieces;
        # their geometry, marks, comments and all unrelated properties survive.
        registered=set(elements)
        for category in categories.values():
            for element in DB.FilteredElementCollector(doc).OfCategoryId(category.Id).WhereElementIsNotElementType():
                parameter=element.get_Parameter(field_guid('scope'))
                if parameter and parameter.HasValue and (parameter.AsString() or '').startswith(PREFIX) and element.UniqueId not in registered:
                    if parameter.IsReadOnly or not parameter.Set(''): raise ValueError('Cannot exclude an unregistered copied piece from schedules: '+element.UniqueId)
                    excluded+=1
        for row in rows: set_values(elements[row['unique_id']],row_values(row),required=True)
        names=set(view.Name for view in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule))
        scope_label='All decks' if scope=='all' else next((row['layout_name'] for row in rows if row['layout_id']==scope),scope[:8])
        for category_id,category in sorted(categories.items()):
            selected=scope=='all' or any(row['layout_id']==scope and api.id_value(elements[row['unique_id']].Category.Id)==category_id for row in rows)
            view=owned_schedule(doc,scope,category_id)
            if not selected and view is None: continue
            if view is None:
                view=DB.ViewSchedule.CreateSchedule(doc,category.Id)
                base=re.sub(r'[\\:{}\[\]|;<>?`~]','-','RT | '+scope_label[:45]+' | '+category.Name)
                candidate=base; suffix=1
                while candidate in names: suffix+=1; candidate=base+' '+str(suffix)
                view.Name=candidate; names.add(candidate)
            configure_schedule(view,ids,scope)
            api.write_stamp(view,dict(owner=OWNER,version=VERSION,role='MATERIAL_SCHEDULE',layout_id='SCHEDULE:'+scope,
                                     schedule_scope=scope,category_id=category_id))
            views.append(view)
        doc.Regenerate()
    log('Committed {0} native schedules; excluded {1} copied/unregistered scope markers; geometry unchanged.'.format(len(views),excluded))
    return views,excluded
