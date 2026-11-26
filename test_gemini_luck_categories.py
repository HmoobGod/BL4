"""Synthetic SDK read-only schema/identity tests; not native gameplay."""
import unittest
import sys
from unittest.mock import patch
from test_foundation import Test
from test_combat_r13 import Node, desc, arraydesc
from test_double_jump_r52 import p, t, FGbxDefPtr

class LuckEvidence(unittest.TestCase):
    def setUp(self):
        self.base=Test();self.base.setUp();self.addCleanup(self.base.tearDown)
        from bl4_custom_foundation import luck_categories as L
        self.L=L
        self.cat_type=t('LuckCategoryDef', L.DEFINITION,
            p('CategoryType','ZEnumProperty',Enum=Node(Name=L.CATEGORY_ENUM)),
            p('ModifierType','ZEnumProperty',Enum=Node(Name=L.MODIFIER_ENUM)))
        self.attr_type=t('GbxAttributeFloat', L.FLOAT, p('Value','ZFloatProperty'),p('BaseValue','ZFloatProperty'))
        self.entry_type=t('LuckCategoryAttribute',L.ENTRY,p('Category','ZGbxDefPtrProperty',Struct=self.cat_type),desc('Value',self.attr_type))
        self.state_type=t('LuckCategoryAttributesState',L.STATE,arraydesc('LuckCategories',desc('inner',self.entry_type)))
        self.a=self.entry('Fixture_A');self.b=self.entry('Fixture_B',kind='Formula',v=0.,base=1.)
        self.arr=[self.a,self.b];self.state=Node(_type=self.state_type,LuckCategories=self.arr)
        self.pc=Node(Class=t('OakPlayerController',L.PC,desc('LuckCategoryAttributesState',self.state_type)),LuckCategoryAttributesState=self.state)
        self.pawn=Node();self.world=Node();self.ok=True
    def entry(self,name,kind='ModifiableAttribute',v=1.,base=1.):
        return Node(_type=self.entry_type,Category=FGbxDefPtr(_type=self.cat_type,_name=name,CategoryType=Node(name=kind),ModifierType=Node(name='ScaleMultiply')),Value=Node(_type=self.attr_type,Value=v,BaseValue=base))
    def context(self):return self.pc,self.pawn,self.world,self.ok
    def observe(self):return self.L.observe(self.context)
    def test_reports_both_types_without_selecting(self):
        rows=self.observe();self.assertEqual(rows,(('Fixture_A','ModifiableAttribute','ScaleMultiply',1.,1.),('Fixture_B','Formula','ScaleMultiply',0.,1.)))
        self.assertIn('preview only',self.L.report_lines(rows)[-1]);self.assertNotIn('overall_loot_luck',self.base.m.AUTO_OPTIONS)
    def test_reordering(self):
        before=self.observe();self.arr.reverse();self.assertEqual(self.observe(),before)
    def test_no_casefold_alias(self):
        self.b.Category._name='fixture_a';self.assertRaises(ValueError,self.observe)
    def test_missing_name(self):
        self.a.Category._name='None';self.assertRaises(ValueError,self.observe)
    def test_null_type(self):
        self.a.Category._type=None;self.assertRaises(ValueError,self.observe)
    def test_wrong_enum(self):
        self.a.Category.CategoryType=Node(name='Unknown');self.assertRaises(ValueError,self.observe)
    def test_bad_float(self):
        self.a.Value.BaseValue=float('nan');self.assertRaises(ValueError,self.observe)
    def test_empty(self):
        self.arr.clear();self.assertRaises(ValueError,self.observe)
    def test_ineligible(self):
        self.ok=False;self.assertRaises(ValueError,self.observe)
    def test_replaced_controller(self):
        old=self.pc;new=Node(**vars(old));seen=[0]
        def ctx():
            seen[0]+=1;return (old if seen[0]==1 else new),self.pawn,self.world,True
        self.assertRaises(ValueError,self.L.observe,ctx)
    def test_value_change(self):
        seen=[0]
        def ctx():
            seen[0]+=1
            if seen[0]==2:self.a.Value.Value=3.
            return self.context()
        self.assertRaises(ValueError,self.L.observe,ctx);self.assertEqual(self.a.Value.Value,3.)
    def test_negative_and_zero_observed_not_written(self):
        self.a.Value.Value=-.25;self.a.Value.BaseValue=0.;self.assertEqual(self.observe()[0][-2:],(-.25,0.))
    def test_read_only_existing_report_hook(self):
        m=self.base.m;lines=[];m.loot_context=lambda *_: (self.world,lambda:None);m.legendary_value=lambda _:1.
        m.bound_session=lambda _:None;m.current_session=lambda _:self.context();m._write_report=lambda _,l:lines.extend(l)
        with patch.dict(sys.modules, {'unrealsdk':Node()}):
            m.inspect_loot_readonly()
        self.assertTrue(any('Category=Fixture_A' in s for s in lines), lines);self.assertEqual(self.a.Value.Value,1.)
