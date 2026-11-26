import threading
import unittest
from unittest.mock import patch
import inventory_admission as a
from inventory_lifecycle import Registration, HOOK_ID
from inventory_capacity import CONFIRM
from test_inventory_admission import Tests


class LifecycleTests(Tests):
    # Do not inherit and rerun the parent test methods.
    def setUp(self):
        super().setUp()
        self.reg = Registration()
        self.registry = {}
        self.removes = []
        hooks = self.x.sdk.hooks
        def has(p,t,k): return True if k == self.x.f._MONITOR_ID else (p,t,k) in self.registry
        def add(p,t,k,cb):
            if (p,t,k) in self.registry: return False
            self.registry[p,t,k] = cb
            return True
        def remove(p,t,k):
            self.removes.append(k)
            return self.registry.pop((p,t,k),None) is not None
        hooks.has_hook, hooks.add_hook, hooks.remove_hook = has,add,remove

    def attach(self): self.assertTrue(self.reg.attach('backpack',CONFIRM))
    def invoke(self): return self.reg.callback(self.x.camera,None,None,self.x.bound)

    def test_lifecycle_success(self):
        self.attach();self.assertIsNone(self.invoke())
        self.assertEqual(self.reg.shot.result,(70,71,70))
        self.assertFalse(self.removes);self.assertIsNone(self.invoke())
        self.assertTrue(self.reg.disable());self.assertEqual(self.removes,[HOOK_ID])
        self.assertFalse(self.registry);self.assertTrue(self.reg.disable());self.assertFalse(self.reg.attach('backpack',CONFIRM))

    def test_lifecycle_disable_before_callback(self):
        self.attach();self.assertTrue(self.reg.disable());self.assertIsNone(self.invoke())
        self.assertIsNone(self.reg.shot.result);self.assertEqual(self.x.field.Value,70)

    def test_lifecycle_foreign_collision(self):
        key=(a.PATH,1,HOOK_ID);self.registry[key]='foreign'
        self.assertFalse(self.reg.attach('backpack',CONFIRM));self.assertFalse(self.reg.disable())
        self.assertEqual(self.registry[key],'foreign');self.assertFalse(self.removes)

    def test_lifecycle_partial_add(self):
        def partial(p,t,k,cb): self.registry[p,t,k]=cb;return False
        self.x.sdk.hooks.add_hook=partial
        self.assertFalse(self.reg.attach('backpack',CONFIRM));self.assertIsNone(self.invoke())
        self.assertFalse(self.reg.disable());self.assertFalse(self.removes)
        self.assertIsNone(self.reg.shot.result)

    def test_lifecycle_missing_registration(self):
        self.attach();self.registry.clear();self.assertIsNone(self.invoke())
        self.assertIsNone(self.reg.shot.result);self.assertIn('missing',self.reg.status)
        self.assertFalse(self.reg.disable());self.assertFalse(self.removes)

    def test_lifecycle_remove_failure(self):
        self.attach();self.x.sdk.hooks.remove_hook=lambda *args:False
        self.assertFalse(self.reg.disable());self.assertTrue(self.reg.owned)
        self.assertIsNone(self.invoke());self.assertIsNone(self.reg.shot.result)

    def test_lifecycle_wrong_thread_disable(self):
        self.attach();out=[];t=threading.Thread(target=lambda:out.append(self.reg.disable()));t.start();t.join()
        self.assertEqual(out,[False]);self.assertTrue(self.reg.disable())

    def test_lifecycle_disable_inside_callback(self):
        self.attach();orig=self.reg.shot.callback
        def run(*args):
            self.assertFalse(self.reg.disable());self.assertFalse(self.removes)
            return orig(*args)
        with patch.object(self.reg.shot,'callback',side_effect=run):self.invoke()
        self.assertTrue(self.reg.disable());self.assertEqual(self.reg.shot.result,(70,71,70))

# Keep inherited fixture setup but exclude inherited test methods from discovery.
for _name in dir(Tests):
    if _name.startswith('test_'): setattr(LifecycleTests,_name,None)
del Tests
