"""Regression model of UnrealSDK v3.2.0 hook collection append behavior."""
import unittest
import test_batch

class HookAppend(unittest.TestCase):
    def setUp(self):
        self.b=test_batch.Batch(); self.b.setUp(); self.addCleanup(self.b.doCleanups)
        self.m=self.b.m
        self.h=self.b.f.sdk.hooks
        self.b.hooks.clear()
        self.m._monitor_registered=False
        self.m._monitor_candidate=False
        self.m._monitor_attempted=False
        self.m._monitor_add_result=None
        self.m._monitor_thread=None
        self.m._monitor_seen=0.
        self.m._monitor_error='not registered'
        self.key=(self.m._MONITOR_PATH,self.h.Type.POST_UNCONDITIONAL,self.m._MONITOR_ID)
        self.other=(self.key[0],self.key[1],'blimgui_hooked_render')
        self.foreign=object()
        self.b.hooks[self.other]=self.foreign
        self.adds=0
    def insert_false(self,p,t,i,cb):
        self.adds+=1
        if (p,t,i) in self.b.hooks:return False
        self.b.hooks[p,t,i]=cb
        return False
    def test_append_false_and_own_callback(self):
        self.h.add_hook=self.insert_false
        self.assertTrue(self.m.ensure_monitor())
        self.assertFalse(self.m._monitor_registered)
        self.assertIn('awaiting own callback',self.m.monitor_status())
        self.m.activate_feature('legendary_weight',2)
        self.assertEqual(self.b.f.writes,[])
        self.b.hooks[self.key]()
        self.assertEqual(self.b.f.writes,[2.])
        self.assertTrue(self.m._monitor_registered)
        self.assertIn('own callback verified', self.m.monitor_status())
        self.assertEqual(self.adds,1)
        self.assertIs(self.b.hooks[self.other],self.foreign)
        self.m.request_stop('test')
        self.b.hooks[self.key]()
        self.assertEqual(self.b.f.writes,[2.,1.])
    def test_false_without_insert(self):
        self.h.add_hook=lambda *a:False
        self.assertFalse(self.m.ensure_monitor())
        self.b.activate('legendary_weight',2)
        self.assertEqual(self.b.f.writes,[])
    def test_preexisting_foreign_never_adopted(self):
        self.b.hooks[self.key]=self.foreign
        self.h.add_hook=self.insert_false
        self.assertFalse(self.m.ensure_monitor())
        self.b.activate('legendary_weight',2)
        self.assertEqual(self.b.f.writes,[])
        self.assertEqual(self.adds,0)
        self.assertIs(self.b.hooks[self.key],self.foreign)
    def test_no_callback_expires(self):
        self.h.add_hook=self.insert_false
        self.m.activate_feature('legendary_weight',2)
        k,v,t,d=self.m._activation_request
        self.m._activation_request=(k,v,t,0)
        self.m.expire_activation()
        self.b.hooks[self.key]()
        self.assertEqual(self.b.f.writes,[])
        self.assertIn('no matching game-hook callback',self.b.report())
    def test_pending_registry_loss(self):
        self.h.add_hook=self.insert_false
        self.m.activate_feature('legendary_weight',2)
        cb=self.b.hooks.pop(self.key)
        cb()
        self.assertEqual(self.b.f.writes,[])
        self.assertFalse(self.m._monitor_registered)
    def test_return_not_bool(self):
        def bad(p,t,i,cb):
            self.b.hooks[p,t,i]=cb
            return None
        self.h.add_hook=bad
        self.assertFalse(self.m.ensure_monitor())
        self.b.hooks[self.key]()
        self.assertFalse(self.m._monitor_registered)
        self.assertEqual(self.b.f.writes,[])
    def test_true_without_insert(self):
        self.h.add_hook=lambda *a:True
        self.assertFalse(self.m.ensure_monitor())
        self.assertFalse(self.m._monitor_registered)
