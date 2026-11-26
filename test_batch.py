"""Mocked session, reflection and GUI tests. Not native gameplay evidence."""
import ast
import sys
import tempfile
import types
import unittest
from pathlib import Path
import loot_fixture

class Attr:
    def __init__(self, value):
        self._values = {'Value':value, 'BaseValue':value}
        self.writes=[]; self.reject=None; self.raise_after=None
        self._type=types.SimpleNamespace(_properties=lambda:[type('ZFloatProperty',(),{'Name':n,'ArrayDim':1})() for n in self._values])
    def _get_address(self): return id(self)
    def __getattr__(self,n):
        if n in self._values:return self._values[n]
        raise AttributeError(n)
    def __setattr__(self,n,v):
        if n in ('Value','BaseValue'):
            self.writes.append((n,v))
            if self.reject == n: raise RuntimeError('refused write')
            self._values[n]=v
            if self.raise_after == n:
                self.raise_after=None;raise RuntimeError('post-write error')
        else:object.__setattr__(self,n,v)

class Batch(unittest.TestCase):
    def setUp(self):
        self.f=loot_fixture.Loot();self.f.setUp();self.addCleanup(self.f.doCleanups);self.m=self.f.m
        self.f.weight=1.;self.f.modifier._get_address=lambda:id(self.f.modifier)
        for o in [self.f.state,self.f.pc,self.f.pawn,self.f.state.RarityState]:o._get_address=lambda o=o:id(o)
        self.f.pawn.ElementalDamageModifiers=types.SimpleNamespace(FireModifier=Attr(1.0))
        self.fire=self.f.pawn.ElementalDamageModifiers.FireModifier
        self.f.pawn.HealthState=types.SimpleNamespace(RepairKitCooldown=Attr(20.0))
        self.cool=self.f.pawn.HealthState.RepairKitCooldown
        self.jump=types.SimpleNamespace(JumpZVelocity=620.,CharacterOwner=self.f.pawn,_path_name=lambda:'Player.Movement')
        self.jump._get_address=lambda:id(self.jump)
        self.jump.Class=types.SimpleNamespace(_properties=lambda:[type('ZFloatProperty',(),{'Name':'JumpZVelocity','ArrayDim':1})()])
        self.f.pawn.CharacterMovement=self.jump
        self.hooks={}
        self.f.sdk.hooks=types.SimpleNamespace(Type=types.SimpleNamespace(POST_UNCONDITIONAL='post'),
          has_hook=lambda p,t,i:(p,t,i) in self.hooks,add_hook=self.add_hook)
        self.f.sdk.unreal=types.SimpleNamespace(WeakPointer=lambda o:lambda:o)
        old=sys.modules.get('unrealsdk');sys.modules['unrealsdk']=self.f.sdk
        self.addCleanup(self.restore_module,'unrealsdk',old)
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'bl4_custom_session_report.txt';self.m.loot_report_path=lambda:self.path
        self.m.inspect_attribute_compatibility=lambda:None
        self.f.base.install_gui();self.gui=self.f.base.gui
        self.gui.THREADED_RENDERING=False
        self.gui.IMPL=type('HookBasedBackend',(),{'__module__':'blimgui.backends.hook_based','_draw_callback':None})()
        self.m.open_key.callback();self.m.monitor_tick();self.m._offline_confirmed=True
    def restore_module(self,name,old):
        if old is None:sys.modules.pop(name,None)
        else:sys.modules[name]=old
    def add_hook(self,p,t,i,cb):self.hooks[p,t,i]=cb;return True
    def activate(self,k,v):
        self.m.activate_feature(k,v)
        self.m.monitor_tick()
    def report(self):return self.path.read_text()
    def test_no_startup_write(self):self.assertEqual(self.f.writes,[]);self.assertIsNone(self.m._controller);self.assertEqual(self.fire.writes,[])
    def test_loot_persistent_nonstacking(self):
        self.activate('legendary_weight',2);self.m.close_menu();self.m.monitor_tick();self.assertEqual(self.f.weight,2)
        self.gui.finish_close();self.m.open_key.callback();self.m.monitor_tick();self.activate('legendary_weight',3)
        self.assertEqual(self.f.writes,[2.,3.]);self.assertEqual(self.f.weight,3)
        self.activate('legendary_weight',3);self.assertEqual(self.f.writes,[2.,3.]);self.activate('legendary_weight',1);self.assertEqual(self.f.weight,1)
    def test_gui_button(self):
        self.m._category=2;self.m._pending['legendary_weight']=2.
        self.gui.imgui.clicks={'Activate / Update Legendary rarity weight##activate_legendary_weight'};self.m.draw();self.assertEqual(self.f.weight,1);self.m.monitor_tick();self.assertEqual(self.f.weight,2)
    def test_all_four_active_then_restore(self):
        for k,v in [('legendary_weight',4),('jump',2),('repair_cooldown',.5)]:self.activate(k,v)
        self.assertEqual(len(self.m._controller.records),3);self.assertEqual((self.f.weight,self.jump.JumpZVelocity,self.fire.Value,self.cool.Value),(4,1240,1,10));self.assertEqual(self.cool.BaseValue,10)
        self.m.request_stop('test',immediate=True);self.assertEqual((self.f.weight,self.jump.JumpZVelocity,self.fire.Value,self.cool.Value),(1,620,1,20));self.assertEqual(self.fire.BaseValue,1);self.assertEqual(self.cool.BaseValue,20);self.assertFalse(self.m._controller.records)
    def test_fire_experimental_cycle(self):
        self.activate('fire_damage',2);self.assertEqual((self.fire.Value,self.fire.BaseValue),(2.,2.))
        self.activate('fire_damage',3);self.assertEqual((self.fire.Value,self.fire.BaseValue),(3.,3.))
        self.activate('fire_damage',1);self.assertEqual((self.fire.Value,self.fire.BaseValue),(1.,1.))
        self.assertIn('gameplay unverified',self.report())
    def test_cooldown_baseline(self):self.activate('repair_cooldown',.5);self.assertEqual(self.cool.Value,10);self.activate('repair_cooldown',2);self.assertEqual(self.cool.Value,40)
    def test_jump_restore(self):self.activate('jump',1.5);self.assertEqual(self.jump.JumpZVelocity,930);self.activate('jump',1);self.assertEqual(self.jump.JumpZVelocity,620)
    def test_no_confirmation(self):self.m._offline_confirmed=False;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[]);self.assertIn('confirm offline',self.report())
    def test_missing_monitor(self):self.hooks.clear();self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_stale_monitor(self):
        self.m._monitor_seen=0;self.m.activate_feature('legendary_weight',2);self.assertEqual(self.f.writes,[])
        self.m.monitor_tick();self.assertEqual(self.f.writes,[2.])
    def test_first_callback_required(self):
        self.m._monitor_thread=None;self.m._monitor_seen=0
        self.m.activate_feature('legendary_weight',2);self.assertIn('awaiting first callback',self.report());self.assertEqual(self.f.writes,[])
        self.m.monitor_tick();self.assertEqual(self.f.writes,[2.])
    def test_wrong_draw_thread_no_write(self):
        self.m.activate_feature('legendary_weight',2)
        k,v,t,d=self.m._activation_request;self.m._activation_request=(k,v,t+1,d)
        self.m.monitor_tick();self.assertEqual(self.f.writes,[]);self.assertIn('thread differs',self.report())
    def test_no_callback_expiry(self):
        self.m.activate_feature('legendary_weight',2)
        k,v,t,d=self.m._activation_request;self.m._activation_request=(k,v,t,0)
        self.m.expire_activation();self.m.monitor_tick();self.assertEqual(self.f.writes,[]);self.assertIn('no matching game-hook callback',self.report())
    def test_close_cancels_queue(self):
        self.m.activate_feature('legendary_weight',2);self.m.close_menu();self.m.monitor_tick();self.assertEqual(self.f.writes,[])
    def test_confirm_withdrawal_cancels_queue(self):
        self.m.activate_feature('legendary_weight',2);self.m.request_stop('owner withdrew confirmation');self.m.monitor_tick();self.assertEqual(self.f.writes,[])
    def test_unregister_after_queue(self):
        self.m.activate_feature('legendary_weight',2);self.hooks.clear();self.m.monitor_tick();self.assertEqual(self.f.writes,[]);self.assertIn('not registered at execution',self.report())
    def test_queued_duplicate_no_second_write(self):
        self.m.activate_feature('legendary_weight',2);self.m.activate_feature('legendary_weight',4)
        self.m.monitor_tick();self.m.monitor_tick();self.assertEqual(self.f.writes,[2.]);self.assertIn('already queued',self.report())
    def test_f8_open_thread_not_required_for_queued_action(self):
        self.m._menu_thread=-1;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[2.])
    def test_wrong_backend(self):self.gui.THREADED_RENDERING=True;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_disabled(self):self.activate('legendary_weight',2);self.m.disabled();self.m.mod.is_enabled=False;self.m.monitor_tick();self.assertEqual(self.f.weight,1);self.assertFalse(self.m._controller.records)
    def test_join(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.activate('legendary_weight',2);self.activate('repair_cooldown',2);self.f.players=2;self.m.monitor_tick();self.assertEqual((self.f.weight,self.fire.Value),(1,1));self.assertFalse(self.m._offline_confirmed)
    def test_no_reapply_after_engine_reset(self):self.activate('legendary_weight',2);self.f.weight=1;self.m.monitor_tick();self.assertEqual(self.f.writes,[2.]);self.assertFalse(self.m._controller.records)
    def test_foreign_change_refused(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.activate('legendary_weight',2);self.activate('repair_cooldown',2);self.f.weight=7;self.m.monitor_tick();self.assertEqual(self.f.weight,7);self.assertEqual(self.fire.Value,1);self.assertTrue(self.m._controller.fault)
    def test_world_change_fault_no_new_world_write(self):self.activate('legendary_weight',2);self.f.state=types.SimpleNamespace(Class=types.SimpleNamespace(Name='OakGameState'),_get_address=lambda:123);self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.f.writes,[2.])
    def test_pawn_replaced_loot_restore_and_pawn_fault(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.activate('legendary_weight',2);self.activate('repair_cooldown',2);new=types.SimpleNamespace(Class=self.f.pawn.Class,_get_address=lambda:99999);self.f.pc.Pawn=new;self.m.monitor_tick();self.assertEqual(self.f.weight,1);self.assertTrue(self.m._controller.fault);self.assertEqual(self.fire.Value,2)
    def test_client_refused(self):self.f.server=False;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_multi_refused(self):self.f.players=2;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_dedicated_refused(self):self.f.ded=True;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_bad_baseline(self):self.f.weight=1.1;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_pair_diff_hold(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.fire._values['Value']=1.5;self.activate('repair_cooldown',2);self.assertEqual(self.fire.writes,[])
    def test_jump_wrong_owner_hold(self):self.jump.CharacterOwner=self.f.pc;self.activate('jump',2);self.assertEqual(self.jump.JumpZVelocity,620)
    def test_wrong_property_metadata(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.fire._type._properties=lambda:[];self.activate('repair_cooldown',2);self.assertEqual(self.fire.writes,[])
    def test_pair_partial_raise_after_write_restores(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.fire.raise_after='BaseValue';self.activate('repair_cooldown',2);self.assertEqual((self.fire.Value,self.fire.BaseValue),(1,1));self.assertFalse(self.m._controller.fault)
    def test_pair_second_write_rejected_restores(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.fire.reject='BaseValue';self.activate('repair_cooldown',2);self.assertEqual((self.fire.Value,self.fire.BaseValue),(1,1));self.assertFalse(self.m._controller.fault)
    def test_restore_failure_fault_latch(self):
        self.f.pawn.HealthState.RepairKitCooldown=self.fire
        self.activate('repair_cooldown',2);self.fire.reject='Value';self.activate('repair_cooldown',1);self.assertTrue(self.m._controller.fault);self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_report_preflight_failure(self):self.m.loot_report_path=lambda:None;self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_conflict(self):
        old=sys.modules.get('LootTreadmill');sys.modules['LootTreadmill']=types.SimpleNamespace(mod=types.SimpleNamespace(is_enabled=True));self.addCleanup(self.restore_module,'LootTreadmill',old);self.activate('legendary_weight',2);self.assertEqual(self.f.writes,[])
    def test_conflict_while_active(self):
        self.activate('legendary_weight',2);old=sys.modules.get('LootTreadmill');sys.modules['LootTreadmill']=types.SimpleNamespace(mod=types.SimpleNamespace(is_enabled=True));self.addCleanup(self.restore_module,'LootTreadmill',old);self.m.monitor_tick();self.assertEqual(self.f.weight,1)
    def test_settings_only(self):self.m.apply({'legendary_weight':10,'jump':3,'fire_damage':3,'repair_cooldown':.5});self.assertEqual(self.f.writes,[]);self.assertEqual(self.jump.JumpZVelocity,620);self.assertEqual(self.fire.writes,[])
    def test_unsupported_feature(self):self.activate('cooldown',2);self.assertEqual(self.fire.writes,[]);self.assertIn('feature HOLD',self.report())
    def test_out_of_range(self):self.activate('legendary_weight',11);self.assertEqual(self.f.writes,[])
    def test_bad_fraction(self):self.activate('legendary_weight',2.55);self.assertEqual(self.f.writes,[])
    def test_no_f9(self):self.assertEqual([k.identifier for k in self.m.mod.keybinds],['open_custom_menu'])
    def test_no_native_grant_calls(self):
        for p in Path(self.m.__file__).parent.glob('*.py'):
            for n in ast.walk(ast.parse(p.read_text())):
                if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):self.assertNotIn(n.func.attr,{'AddModifierToGbxAttribute','RemoveAttributeModifier','RemoveModifierFromGbxAttribute','RemoveMultipleAttributeModifiers','SpawnInventoryFromItemPool','GiveCurrency','BP_SetExperienceLevel'})
                if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store):self.assertNotIn(n.attr,{'ExperiencePoints','ExperienceLevel','currencies'})
