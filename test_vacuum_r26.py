"""Continuous mode and preference regression tests (synthetic only)."""
from test_vacuum_r25 import VacuumTests

class Continuous(VacuumTests):
    def start(self,kinds=('ammo',),radius=30):
        # Existing fixture builds bounded controller; enable mode before begin.
        self.lease=self.v.Vacuum(lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda k,**kw:self.actors if k=='InventoryPickup' else self.machines,lambda n,**kw:__import__('types').SimpleNamespace(**kw),lambda:self.now,lambda:self.thread,self.messages.append,kinds,radius,continuous=True)
        return self.lease.begin()
    def test_continuous_after_30s(self):
        self.start();self.tick(31);self.assertEqual(len(self.calls),1);self.assertIsNotNone(self.lease.record)
    def test_rolling_limit(self):
        self.actors=[self.drop(str(i),'ammo',(300+i,0,0)) for i in range(32)];self.start()
        for _ in range(8):self.tick()
        self.assertEqual(len(self.calls),24);self.assertIsNotNone(self.lease.record)
        self.tick(31);self.assertEqual(len(self.calls),28);self.assertEqual(len(set(c[0] for c in self.calls)),28)
    def test_continuous_jump_pause(self):
        self.start();self.pawn.CharacterMovement.IsMovingOnGround=lambda:False;self.tick();self.assertIsNotNone(self.lease.record);self.assertFalse(self.calls)
        self.pawn.CharacterMovement.IsMovingOnGround=lambda:True;self.tick();self.assertEqual(len(self.calls),1)
    def test_airborne_join_stops(self):
        self.start();self.pawn.CharacterMovement.IsMovingOnGround=lambda:False;self.ok=False;self.tick();self.assertIsNone(self.lease.record)
    def test_session_change_while_throttled(self):
        self.actors=[self.drop(str(i),'ammo',(300+i,0,0)) for i in range(30)];self.start()
        for _ in range(6):self.tick()
        self.ok=False;self.tick();self.assertIsNone(self.lease.record);self.assertEqual(len(self.calls),24)
    def test_continuous_stop(self):
        self.start();self.lease.stop('explicit');self.tick(40);self.assertFalse(self.calls)
    def test_session_dedup(self):
        self.start();self.tick();self.tick(40);self.assertEqual(len(self.calls),1)
    def test_movement_during_dispatch(self):
        self.start();old=self.a.K2_GetActorRotation
        def move():self.pawn.pos=(80,0,0);return old()
        move.func=old.func;self.a.K2_GetActorRotation=move;self.tick();self.assertFalse(self.calls)
    def test_display_path_rejected(self):
        for path in ('/Game/Gear/Shop/Gun','/Game/Pickups/HealthPreview','/Game/Pickups/AmmoShowcase'):self.assertIsNone(self.v.body_kind(path))
    def test_saved_prefs_no_arm(self):
        m=self.base.m;m._vacuum_filters['ammo']=True;m._vacuum_filters['eridium']=True;m._vacuum_radius=40.;m.save_vacuum_preferences();m._vacuum_filters['ammo']=False;m._vacuum_radius=5.;m.load_vacuum_preferences();self.assertTrue(m._vacuum_filters['ammo']);self.assertTrue(m._vacuum_filters['eridium']);self.assertEqual(m._vacuum_radius,40.);self.assertFalse(m.health_active());self.assertIsNone(m._activation_request)
    def test_reset_saved_prefs(self):
        m=self.base.m;m._vacuum_filters['ammo']=True;m.save_vacuum_preferences();m.reset();m.load_vacuum_preferences();self.assertFalse(any(m._vacuum_filters.values()));self.assertEqual(m._vacuum_radius,30.)
    def test_continuous_ui(self):
        m=self.base.m;self.base.open();m._category=5;m._vacuum_filters['ammo']=True;queued=[];m.activate_feature=lambda *a:queued.append(a);self.base.gui.imgui.clicks={'Start continuous Loot Vacuum (session only)'};m.draw();self.assertEqual(queued,[('loot_vacuum_continuous',(('ammo',),30.))])
