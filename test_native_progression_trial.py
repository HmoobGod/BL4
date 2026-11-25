"""Source-only trial tests; fake API, no game execution."""
import unittest
from types import SimpleNamespace as NS
import test_batch

class Obj:
    def _get_address(self): return id(self)

class API:
    def __init__(self): self.value=1.; self.calls=[]; self.ambiguous=False
    def read(self,k,p): return self.value
    def add(self,k,p,d):
        self.calls.append((k,p,d)); self.value=f32(self.value+d)
        if self.ambiguous: raise ValueError('ambiguous')

class Tests(unittest.TestCase):
    def setUp(self):
        fixture=test_batch.Batch();fixture.setUp();self.addCleanup(fixture.doCleanups)
        global Trial, f32
        from native_progression_trial import Trial, f32
        self.pc,self.pawn,self.state=Obj(),Obj(),Obj()
        self.slot=NS(SourceItemHandle=NS(Handle=3),ReplicationID=2,ReplicationKey=1)
        self.pawn.EquippedInventorySlots=NS(items=[self.slot]); self.eligible=True; self.consent=True
        self.c=NS(context=lambda:(self.pc,self.pawn,self.state,self.eligible),thread=lambda:1,
                  weak_pointer=lambda obj:lambda:obj,fault=False,stop_pending=None,log=lambda msg:True)
        self.c.fail=lambda msg:setattr(self.c,'fault',True)
        self.a=API();self.t=Trial(self.c,self.a,lambda:self.consent,'xp')
    def test_add_inverse_once(self):
        self.assertTrue(self.t.activate(2.5));self.assertEqual(self.a.value,2.5)
        self.assertTrue(self.t.cancel());self.assertEqual(self.a.value,1.)
        self.assertFalse(self.t.cancel());self.assertFalse(self.t.activate(3.))
        self.assertEqual([c[2] for c in self.a.calls],[1.5,-1.5])
    def test_cash_independent(self):
        other=API();t=Trial(self.c,other,lambda:True,'cash')
        self.assertTrue(t.activate(10));self.assertEqual(other.calls[0][0],'cash');self.assertEqual(self.a.calls,[])
    def test_no_eridium(self):
        with self.assertRaises(ValueError):Trial(self.c,self.a,lambda:True,'eridium')
    def test_precision(self):
        for value in (1,1.05,10.1,True,float('nan')):self.assertFalse(self.t.activate(value))
        self.assertEqual(self.a.calls,[])
    def test_nonunit_baseline(self):
        self.a.value=1.1;self.assertFalse(self.t.activate(2));self.assertEqual(self.a.calls,[])
    def test_no_consent(self):
        self.consent=False;self.assertFalse(self.t.activate(2));self.assertEqual(self.a.calls,[])
    def test_no_solo(self):
        self.eligible=False;self.assertFalse(self.t.activate(2));self.assertEqual(self.a.calls,[])
    def test_ambiguous_no_retry(self):
        self.a.ambiguous=True;self.assertFalse(self.t.activate(2));self.assertTrue(self.c.fault)
        self.assertFalse(self.t.cancel());self.assertFalse(self.t.activate(2));self.assertEqual(len(self.a.calls),1)
    def test_drift_no_inverse(self):
        self.assertTrue(self.t.activate(2));self.a.value=3.;self.assertFalse(self.t.cancel());self.assertEqual(len(self.a.calls),1)
    def test_gear_changed_no_inverse(self):
        self.assertTrue(self.t.activate(2));self.slot.ReplicationKey+=1
        self.assertFalse(self.t.cancel());self.assertEqual(len(self.a.calls),1)
    def test_pawn_changed_no_inverse(self):
        self.assertTrue(self.t.activate(2));new=Obj();new.EquippedInventorySlots=self.pawn.EquippedInventorySlots;self.pawn=new
        self.assertFalse(self.t.cancel());self.assertEqual(len(self.a.calls),1)
    def test_fraction(self):
        self.assertTrue(self.t.activate(1.1));self.assertTrue(self.t.cancel());self.assertEqual(self.a.value,1.)
