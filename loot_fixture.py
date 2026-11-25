"""Mocked SDK tests: no game or native code execution."""
import contextlib
import io
import math
import sys
import tempfile
import types
import unittest
from pathlib import Path
from test_foundation import Test as Foundation

class Modifier:
    def __init__(self, owner):
        self.owner = owner
        self._type = types.SimpleNamespace(_properties=lambda: [type('ZFloatProperty',(),{'Name':'Value','ArrayDim':1})()])
    @property
    def Value(self):
        return self.owner.weight
    @Value.setter
    def Value(self, v):
        self.owner.writes.append(v)
        mode = self.owner.mode
        if mode == 'ignore': return
        if mode == 'fail_restore' and len(self.owner.writes)>1: raise RuntimeError('restore failure')
        if mode == 'foreign' and len(self.owner.writes)==1:
            self.owner.weight = 7.0; return
        self.owner.weight = float(v)
        if mode == 'raise_after' and len(self.owner.writes)==1: raise RuntimeError('setter threw after write')

class Loot(unittest.TestCase):
    def setUp(self):
        self.base=Foundation(); self.base.setUp(); self.addCleanup(self.base.tearDown); self.m=self.base.m
        self.weight=.25; self.writes=[]; self.mode='normal'; self.players=1; self.server=True; self.ded=False; self.solo=False
        self.pawn=types.SimpleNamespace(Class=types.SimpleNamespace(Name='OakCharacter'))
        self.pc=types.SimpleNamespace(Pawn=self.pawn, PlayerState=object(),IsLocalPlayerController=lambda:True,HasAuthority=lambda:True)
        sys.modules['mods_base'].get_pc=lambda **k:self.pc
        self.modifier=Modifier(self)
        self.state=types.SimpleNamespace(_path_name=lambda:'/Game/Map.GameState',Class=types.SimpleNamespace(Name='OakGameState'),RarityState=types.SimpleNamespace(LegendaryModifier=self.modifier,CommonModifier=types.SimpleNamespace(Value=9)))
        self.funcs=[]
        self.bind(self.m._LOOT_SYSTEM+'IsStandalone',self.m._LOOT_BOOL_SIG,lambda p:self.solo)
        self.bind(self.m._LOOT_SYSTEM+'IsServer',self.m._LOOT_BOOL_SIG,lambda p:self.server)
        self.bind(self.m._LOOT_SYSTEM+'IsDedicatedServer',self.m._LOOT_BOOL_SIG,lambda p:self.ded)
        self.bind(self.m._LOOT_STATICS+'GetNumPlayerStates',(('WorldContextObject','ZObjectProperty'),('ReturnValue','ZIntProperty')),lambda p:self.players)
        self.bind(self.m._LOOT_STATICS+'GetGameState',(('WorldContextObject','ZObjectProperty'),('ReturnValue','ZObjectProperty')),lambda p:self.state)
        self.sdk=types.SimpleNamespace(find_all=lambda *a,**k:self.funcs)
    def bind(self,path,sig,callback):
        name=path.rsplit(':',1)[1]
        def bound(*a): return callback(*a)
        fn=types.SimpleNamespace(Name=name,NumParams=len(sig),_path_name=lambda:path,_properties=lambda:[type(t,(),{'Name':n})() for n,t in sig],Outer=types.SimpleNamespace(ClassDefaultObject=types.SimpleNamespace(**{name:bound})))
        bound.func=fn; self.funcs.append(fn)
