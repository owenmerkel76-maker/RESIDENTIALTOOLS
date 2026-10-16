# -*- coding: utf-8 -*-
"""Shared menu text and editable drafts, independent of Revit/WPF."""
from rt_layout import DEFAULTS
import io
import json
import os


def release_version():
    path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'release.json')
    try:
        with io.open(path,'r',encoding='utf-8-sig') as stream: return json.load(stream)['version']
    except (IOError,ValueError,KeyError): return 'development'


def editable_settings(values):
    result=dict(DEFAULTS)
    result.update(values)
    # Combo selections are limited values; leave numeric text fields editable
    # so a family lookup is not blocked by unfinished, unrelated dimensions.
    for key in ('stock_ft','spacing_in','border_courses','beam_plies','hanger_rotation_deg','corner_rotation_deg'):
        result[key]=int(float(result[key]))
    return result


def count_text(counts,breakers=0):
    c=lambda key:int(counts.get(key,0))
    text=('Boards {0} | Borders {1} (breakers {2}) | Clips {3}\n'
            'Framing {4} | Beam pieces {5} | Posts {6}\n'
            'Hangers {7} (double {8}) | Beam ties {9} | Corner brackets {10}').format(
                c('boards'),c('borders'),int(breakers),c('clips'),c('framing'),c('beams'),c('posts'),
                c('hangers'),c('double_hangers'),c('hurricane_straps'),c('corner_straps'))
    if 'border_clips' in counts or 'face_fasteners' in counts:
        text+='\nBorder clips {0} (included above) | Schematic face screws {1}'.format(c('border_clips'),c('face_fasteners'))
    if counts.get('field_edge_screws'):
        text+=' (field edges {0}, included)'.format(c('field_edge_screws'))
    if counts.get('hardware_nails'):
        text+='\nHardware nails {0} (individual schematic pieces)'.format(c('hardware_nails'))
    return text


def edge_labels(poly):
    import math
    return ['Edge {0}: {1:.2f} ft | ({2:.2f}, {3:.2f}) to ({4:.2f}, {5:.2f})'.format(
        i+1,math.hypot(b[0]-a[0],b[1]-a[1]),a[0],a[1],b[0],b[1])
        for i,a in enumerate(poly) for b in [poly[(i+1)%len(poly)]]]
