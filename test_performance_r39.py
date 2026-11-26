"""Synthetic regression for live conflict detection and late pickup revalidation."""
import sys
import types
from test_vacuum_r25 import VacuumTests, Obj

class LateVacuum(VacuumTests):
    def during_rotation(self, effect):
        old=self.a.K2_GetActorRotation
        def changed():
            effect();return old()
        changed.func=old.func;self.a.K2_GetActorRotation=changed
    def test_owner_changes_after_candidate_scan(self):
        self.start();self.during_rotation(lambda:setattr(self.a,'Owner',Obj('foreign')));self.tick();self.assertFalse(self.calls);self.assertFalse(self.lease.attempted)
    def test_classification_changes_after_candidate_scan(self):
        self.start();self.during_rotation(lambda:setattr(self.a,'BodyData',Obj('/Game/Pickups/MissionAmmo')));self.tick();self.assertFalse(self.calls)
    def test_vendor_appears_during_prepare(self):
        m=self.actor('vendor',(301,0,0));m.GetIOTDForPlayer=lambda pc:self.a
        self.start();self.during_rotation(lambda:self.machines.append(m));self.tick();self.assertFalse(self.calls)
    def test_locked_during_destination_creation(self):
        self.start();old=self.lease.make
        def make(*a,**kw):
            self.a.UsableActorState.bInteractabilityLockedReplicated=True;return old(*a,**kw)
        self.lease.make=make;self.tick();self.assertFalse(self.calls)
    def test_lifetime_ends_during_last_context(self):
        self.start();old=self.lease.resolve;calls=[]
        def resolve():
            out=old();calls.append(1)
            if len(calls)==4:self.now+=31
            return out
        self.lease.resolve=resolve;self.tick();self.assertFalse(self.calls);self.assertIsNone(self.lease.record)
    def test_nearest_four_stable(self):
        self.actors=[self.drop(str(i),'ammo',(300+d,0,0)) for i,d in enumerate((8,2,2,1,5,0,9))];self.start();self.tick();self.assertEqual([c[0] for c in self.calls],['5','3','1','2'])

class ConflictIndex(VacuumTests):
    def install(self,name,enabled=False):
        old=sys.modules.get(name);present=name in sys.modules
        def restore():
            if present:sys.modules[name]=old
            else:sys.modules.pop(name,None)
        self.addCleanup(restore)
        obj=types.SimpleNamespace(mod=types.SimpleNamespace(is_enabled=enabled));sys.modules[name]=obj;return obj
    def test_unchanged_names_reuse_index(self):
        m=self.base.m;self.install('Loot_Magnet');self.assertFalse(m.conflicting_mods());index=m._conflict_index;self.assertFalse(m.conflicting_mods());self.assertIs(m._conflict_index,index)
    def test_enabled_value_is_not_cached(self):
        m=self.base.m;mod=self.install('Loot_Magnet');self.assertFalse(m.conflicting_mods());mod.mod.is_enabled=True;self.assertTrue(m.conflicting_mods());mod.mod.is_enabled=False;self.assertFalse(m.conflicting_mods())
    def test_import_removal_detected(self):
        m=self.base.m;self.assertFalse(m.conflicting_mods());self.install('BL4_AutoReload',True);self.assertTrue(m.conflicting_mods());sys.modules.pop('BL4_AutoReload');self.assertFalse(m.conflicting_mods())
    def test_same_name_replacement_detected(self):
        m=self.base.m;self.install('Loot_Magnet');self.assertFalse(m.conflicting_mods());sys.modules['Loot_Magnet']=types.SimpleNamespace(mod=types.SimpleNamespace(is_enabled=True));self.assertTrue(m.conflicting_mods())
    def test_unknown_enable_state_fails_closed(self):
        m=self.base.m;self.install('Loot_Magnet');self.assertFalse(m.conflicting_mods());sys.modules['Loot_Magnet']=None;self.assertTrue(m.conflicting_mods())
