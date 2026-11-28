"""Read-only native reserve-aware vacuum; synthetic SDK and relocation only."""
import unittest
from test_vacuum_r25 import VacuumTests
from test_native_resource_rates import FGbxDefPtr
from test_double_jump_r52 import p,t
from test_combat_r13 import Node

class AmmoNeedVacuumTests(VacuumTests):
    def exact(self,name,kind,pos):
        a=self.drop(name,'ammo',pos)
        body=next(b for b,(key,_) in self.v.AMMO_TYPES.items() if key==kind)
        a.BodyData.path=body
        return a
    def start_with(self,reader,kinds=('ammo',)):
        self.assertTrue(self.start(kinds));self.lease.ammo_reader=reader
    def test_full_reserve_skipped_and_later_needed(self):
        a=self.exact('full','pistol',(300,0,0));self.actors=[a];ratio=[1.]
        self.start_with(lambda pawn,body:ratio[0]);self.tick();self.assertFalse(self.calls);self.assertFalse(self.lease.attempted)
        ratio[0]=.5;self.tick();self.assertEqual(len(self.calls),1)
    def test_known_depleted_priority(self):
        self.actors=[self.exact(str(i),'pistol',(300+i,0,0)) for i in range(4)]+[self.exact('depleted','smg',(350,0,0))]
        self.start_with(lambda pawn,body:0. if 'smg' in body else .99);self.tick();self.assertEqual(self.calls[0][0],'depleted');self.assertEqual(len(self.calls),4)
    def test_scan_cache_per_type_and_fresh_read(self):
        self.actors=[self.exact(str(i),'pistol',(300+i,0,0)) for i in range(8)];reads=[]
        self.start_with(lambda pawn,body:reads.append(body) or .3);self.tick();self.assertEqual(len(reads),5)
    def test_full_during_preparation(self):
        self.actors=[self.exact('a','pistol',(300,0,0))];ratios=iter((.2,1.))
        self.start_with(lambda pawn,body:next(ratios));self.tick();self.assertFalse(self.calls);self.assertFalse(self.lease.attempted)
    def test_lost_witness_not_attempted(self):
        self.actors=[self.exact('a','pistol',(300,0,0))];ratios=iter((.2,None))
        self.start_with(lambda pawn,body:next(ratios));self.tick();self.assertFalse(self.calls)
    def test_missing_and_unknown_legacy(self):
        self.actors=[self.exact('exact','pistol',(300,0,0)),self.a];reads=[]
        def missing(pawn,body):reads.append(body);raise ValueError('unavailable')
        self.start_with(missing);self.tick();self.assertEqual(len(self.calls),2);self.assertEqual(len(reads),2)
    def test_permission_lost_on_fresh_read(self):
        self.actors=[self.exact('a','pistol',(300,0,0))];reads=[]
        def read(pawn,body):
            reads.append(body)
            if len(reads)==2:self.ok=False
            return .3
        self.start_with(read);self.tick();self.assertFalse(self.calls);self.assertIsNone(self.lease.record)
    def test_body_change_on_fresh_read(self):
        a=self.exact('a','pistol',(300,0,0));self.actors=[a];reads=[]
        def read(pawn,body):
            reads.append(body)
            if len(reads)==2:a.BodyData.path='/Game/Pickups/Ammo/Changed.Changed'
            return .3
        self.start_with(read);self.tick();self.assertFalse(self.calls)
    def test_full_ammo_does_not_block_cash(self):
        self.actors=[self.exact('full','pistol',(300,0,0)),self.drop('cash','cash',(400,0,0))]
        self.start_with(lambda pawn,body:1.,('ammo','cash'));self.tick();self.assertEqual([c[0] for c in self.calls],['cash'])

class AmmoNeedBindingTests(unittest.TestCase):
    def setUp(self):
        self.base=VacuumTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.v=self.base.v
        from bl4_custom_foundation import native_resource_rates as R
        self.R=R;self.attr=t('GbxAttributeDef',R.DEF,p('Context','ZGbxInlineStructProperty'),p('Value','ZGbxInlineStructProperty'));self.attr.definitions={}
        self.pawn=self.base.pawn;self.pawn.Class.path='/Script/OakGame.OakCharacter'
        self.values={};self.calls=[]
        for key,ammo_type in self.v.AMMO_TYPES.values():
            for which in ('Current','Max'):
                name='ammo_'+key+'_'+which.lower()+'value'
                c=Node(_type=t('ActorContextResolver','/Script/GbxEngine.ActorContextResolver'))
                v=Node(_type=t('OakAmmoValueResolver','/Script/OakGame.OakAmmoValueResolver',p('AmmoType','ZEnumProperty',Enum=Node(Name='/Script/OakGame.EOakAmmoType')),p('Value','ZEnumProperty',Enum=Node(Name='/Script/OakGame.EOakAmmoResolverValue')),p('bFromPickup','ZBoolProperty')),AmmoType=Node(name=ammo_type),Value=Node(name=which),bFromPickup=False)
                self.attr.definitions[name]=Node(Context=c,Value=v);self.values[name]=5. if which=='Current' else 10.
        sig=R.SPECS['GetValueOfAttribute'];ps=[p(n,k) for n,k in sig];ps[1].PropertyClass=Node(Name='/Script/CoreUObject.Object')
        self.fn=Node(Name='GetValueOfAttribute',NumParams=len(ps),_properties=lambda:ps,Outer=Node(Name=R.LIB[:-1]),_path_name=lambda:R.LIB+'GetValueOfAttribute')
        self.reader=self.bind()
    def bind(self):return self.v.AmmoNeedReader([self.fn],lambda *a:self.get,FGbxDefPtr,self.attr)
    def get(self,name,pawn,default):self.assertIs(pawn,self.pawn);self.calls.append(name);return self.values.get(name,default)
    def pistol(self):return next(b for b,(key,_) in self.v.AMMO_TYPES.items() if key=='pistol')
    def test_all_five_exact_types(self):
        for body,(key,_) in self.v.AMMO_TYPES.items():self.assertEqual(self.reader(self.pawn,body),.5);self.assertEqual(self.calls[-2:],['ammo_'+key+'_currentvalue','ammo_'+key+'_maxvalue'])
    def test_wrong_resolver_or_pickup_context(self):
        v=self.attr.definitions['ammo_pistol_currentvalue'].Value;v.bFromPickup=True
        with self.assertRaises(ValueError):self.reader(self.pawn,self.pistol())
        self.assertFalse(self.calls)
    def test_sentinel_and_zero_max_and_invalid_counts(self):
        for c,m in ((-123456.,10),(0,0),(11,10),(1.5,10),(True,10),(0,float('nan'))):
            self.values.update(ammo_pistol_currentvalue=c,ammo_pistol_maxvalue=m)
            with self.assertRaises(ValueError):self.reader(self.pawn,self.pistol())
    def test_wrong_ammo_enum(self):
        self.attr.definitions['ammo_pistol_maxvalue'].Value.AmmoType.name='SMG'
        with self.assertRaises(ValueError):self.reader(self.pawn,self.pistol())
        self.assertFalse(self.calls)
    def test_signature_mismatch(self):
        self.fn.NumParams=3
        with self.assertRaises(ValueError):self.bind()
    def test_zero_current_valid(self):
        self.values['ammo_pistol_currentvalue']=0
        self.assertEqual(self.reader(self.pawn,self.pistol()),0)
