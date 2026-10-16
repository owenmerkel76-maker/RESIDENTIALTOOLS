"""Exercise the native nail adapter with IronPython integer division semantics."""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj


class Vector:
    def __init__(self, x, y, z): self.xyz = (x, y, z)
    @property
    def Z(self): return self.xyz[2]
    def __add__(self, other): return Vector(*(a+b for a,b in zip(self.xyz,other.xyz)))
    def __mul__(self, scalar): return Vector(*(a*scalar for a in self.xyz))
    def Normalize(self):
        length = math.sqrt(sum(a*a for a in self.xyz))
        return self*(1.0/length)
    def CrossProduct(self, other):
        x,y,z = self.xyz; a,b,c = other.xyz
        return Vector(y*c-z*b,z*a-x*c,x*b-y*a)


def py2_div(a,b):
    return a//b if isinstance(a,int) and isinstance(b,int) else a/b


class Python2Division(ast.NodeTransformer):
    def visit_BinOp(self,node):
        self.generic_visit(node)
        if isinstance(node.op,ast.Div):
            return ast.copy_location(ast.Call(func=ast.Name(id='py2_div',ctx=ast.Load()),
                                             args=[node.left,node.right],keywords=[]),node)
        return node


class NailExtrusionTests(unittest.TestCase):
    def test_whole_inch_nails_have_positive_correct_shanks_under_ironpython(self):
        path = Path(__file__).resolve().parents[1]/'lib'/'rt_revit.py'
        node = next(n for n in ast.parse(path.read_text()).body
                    if isinstance(n,ast.FunctionDef) and n.name=='create_hardware_nail')
        module = ast.fix_missing_locations(Python2Division().visit(ast.Module(body=[node],type_ignores=[])))
        Vector.BasisZ = Vector(0,0,1); Vector.BasisX = Vector(1,0,0)
        calls = []
        def extrusion(points,axis,length,steel):
            self.assertGreater(length,0)
            calls.append((points,axis,length))
            return length
        import rt_clip
        scope = dict(DB=Obj(XYZ=Vector),rt_clip=rt_clip,py2_div=py2_div,
                     extrusion=extrusion,shape=lambda doc,solids,*args:solids)
        exec(compile(module,str(path),'exec'),scope)
        for length in (1,1.5,2.5,3,3.5):
            for direction in ((0,1,0),(-2**-.5,2**-.5,0),(0,0,1)):
                calls[:] = []
                result = scope['create_hardware_nail'](None,dict(head=(1,17,8),direction=direction,
                         diameter_in=.148,nail_length_in=length,product='nail'),None,'layout')
                self.assertAlmostEqual(result[0],length/12.0)
                self.assertAlmostEqual(result[1],.035/12.0)
                # The head starts just outside the mounting plane.
                points,axis,_ = calls[1]
                center = [sum(p.xyz[i] for p in points)/len(points) for i in range(3)]
                for i,value in enumerate((1,17,8)):
                    self.assertAlmostEqual(center[i],value-axis.xyz[i]*.035/12.0)
