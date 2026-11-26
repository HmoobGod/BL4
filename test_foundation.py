"""Simulated SDK + GUI contract tests; NOT actual game or native GUI execution."""
import ast
import contextlib
import importlib.util
import io
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
SOURCE = ROOT / 'bl4_custom_foundation' / '__init__.py'

class Base:
    def __init__(self, identifier, *, display_name=None, description='', **kw):
        self.identifier = identifier
        self.display_name = display_name or identifier
        self.description = description
        self.__dict__.update(kw)

class Value(Base):
    def __init__(self, identifier, value, **kw):
        super().__init__(identifier, **kw)
        self.value = self.default_value = value

class Bool(Value): pass
class Slider(Value):
    def __init__(self, identifier, value, min_value, max_value, **kw):
        super().__init__(identifier, value, **kw)
        self.min_value, self.max_value = min_value, max_value
class Button(Base): pass
class Nested(Base):
    def __init__(self, identifier, children, **kw):
        super().__init__(identifier, **kw)
        self.children = children

class Mod:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.is_enabled = True
        self.saved = None
        self.fail_save = False
        self.save_count = 0
    def save_settings(self):
        if self.fail_save: raise OSError('simulated disk failure')
        def opts(items):
            return {o.identifier: opts(o.children) if isinstance(o, Nested) else o.value
                    for o in items if not isinstance(o, Button)}
        self.saved = json.loads(json.dumps(dict(options=opts(self.options), enabled=self.is_enabled,
                                              keybinds={k.identifier:k.key for k in self.keybinds})))
        self.save_count += 1
    def restore(self, saved):
        def load(items, data):
            for o in items:
                if o.identifier not in data: continue
                if isinstance(o, Nested): load(o.children, data[o.identifier])
                elif isinstance(o, Value): o.value = data[o.identifier]
        load(self.options, saved['options'])
        self.is_enabled = self.auto_enable and saved['enabled']
        for k in self.keybinds:
            k.key = saved.get('keybinds', {}).get(k.identifier, k.key)

class UI:
    def __init__(self): self.clicks = set(); self.edits = {}; self.labels = []
    def text(self, label): self.labels.append(label)
    text_wrapped = text
    def separator(self): pass
    def same_line(self): pass
    def button(self, label):
        self.labels.append(label)
        return label in self.clicks
    def checkbox(self, label, value):
        self.labels.append(label)
        return label in self.edits, self.edits.get(label, value)
    def slider_float(self, label, value, lo, hi, fmt):
        self.labels.append(label)
        return label in self.edits, self.edits.get(label, value)

class GUI:
    __version__ = '1.1'
    def __init__(self):
        self.active = False; self.closing = False; self.title = ''; self.opens = 0; self.closes = 0
        self.IMPL = types.SimpleNamespace(_draw_callback=lambda: None)
        self.exit_requested = False
        self.hello_imgui = types.SimpleNamespace(is_using_hello_imgui=lambda:self.active,
            get_runner_params=lambda:types.SimpleNamespace(app_window_params=types.SimpleNamespace(window_title=self.title), app_shall_exit=self.exit_requested))
        self.imgui = UI()
    def is_window_open(self): return self.active and not self.closing
    def set_draw_callback(self, cb): self.IMPL._draw_callback = cb
    def create_window(self, title, width, height, callback):
        self.opens += 1; self.active = True; self.title = title; self.runner_callback = callback; self.exit_requested=False
        self.IMPL._draw_callback = callback
    def close_window(self): self.closes += 1; self.closing = True
    def finish_close(self): self.active = False; self.closing = False

class Test(unittest.TestCase):
    def setUp(self):
        self.old_sdk = sys.modules.get('mods_base'); self.old_gui = sys.modules.pop('blimgui',None)
        sdk = types.ModuleType('mods_base')
        sdk.BoolOption, sdk.SliderOption, sdk.ButtonOption, sdk.NestedOption = Bool, Slider, Button, Nested
        sdk.build_mod = Mod
        sdk.keybind = lambda identifier, key, callback, **kw: types.SimpleNamespace(identifier=identifier,key=key,callback=callback,**kw)
        sys.modules['mods_base'] = sdk
        spec = importlib.util.spec_from_file_location('test_bl4', SOURCE)
        self.m = importlib.util.module_from_spec(spec); sys.modules['test_bl4'] = self.m; spec.loader.exec_module(self.m)
        self.gui = GUI()
    def tearDown(self):
        for k,v in [('mods_base',self.old_sdk),('blimgui',self.old_gui)]:
            if v is None: sys.modules.pop(k,None)
            else: sys.modules[k]=v
    def install_gui(self): sys.modules['blimgui'] = self.gui
    def open(self): self.install_gui(); self.m.toggle_menu()
    def test_categories(self): self.assertEqual(len(self.m.CATEGORIES),9)
    def test_defaults(self):
        for o in self.m.ALL: self.assertEqual(o.value, False if isinstance(o,Bool) else (30.0 if o.identifier=='vacuum_pref_radius' else 1.0))
    def test_unique_ids(self): self.assertEqual(len({o.identifier for o in self.m.ALL}),len(self.m.ALL))
    def test_no_game_hooks_commands(self): self.assertEqual((self.m.mod.hooks,self.m.mod.commands),([],[]))
    def test_no_game_imports(self):
        tree=ast.parse(SOURCE.read_text()); imports={a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
        imports|={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        self.assertEqual(imports,{'math','sys','mods_base','pathlib','threading','time','gameplay_fields','session_control','ground_speed','health_pulse','skill_pulse','reload_assist','inventory_capacity','loot_vacuum','weapon_rates','shield_rates','gadget_rates','double_jump'})
    def test_existing_settings_key(self):
        self.m.mod.restore({'options':{'settings_test':True},'enabled':True})
        self.assertTrue(self.m.probe.value); self.assertTrue(self.m.mod.is_enabled)
    def test_roundtrip(self):
        self.m.apply({'damage':2.4,'auto_reload':True,'settings_test':True}); self.m.open_key.key='F9'; self.m.mod.save_settings()
        saved=self.m.mod.saved
        self.m.reset(); self.m.open_key.key='F8'; self.m.mod.restore(saved)
        self.assertEqual(self.m.ALL[0].value,2.4); self.assertTrue(self.m.probe.value); self.assertEqual(self.m.open_key.key,'F9')
        self.assertTrue(next(o for o in self.m.ALL if o.identifier=='auto_reload').value)
    def test_clamp_and_bad_values(self):
        o=self.m.ALL[0]; self.assertEqual(self.m.normalize(o,999),5.0); self.assertEqual(self.m.normalize(o,-5),0.5)
        self.assertEqual(self.m.normalize(o,float('nan')),1.0); self.assertEqual(self.m.normalize(self.m.probe,'true'),False)
    def test_missing_gui(self):
        self.m.toggle_menu(); self.assertIsNone(self.m._backend); self.assertTrue(self.m.mod.is_enabled)
    def test_wrong_version(self):
        self.install_gui(); self.gui.__version__='2.0'; self.m.toggle_menu(); self.assertEqual(self.gui.opens,0)
    def test_disabled(self):
        self.install_gui(); self.m.mod.is_enabled=False; self.m.toggle_menu(); self.assertEqual(self.gui.opens,0)
    def test_open_close_hotkey(self):
        self.install_gui(); old=self.gui.IMPL._draw_callback; self.m.open_key.callback(); self.assertEqual(self.gui.title,self.m.TITLE)
        self.assertIs(self.gui.IMPL._draw_callback,old); self.assertIs(self.gui.runner_callback,self.m.draw)
        self.m.open_key.callback(); self.assertEqual(self.gui.closes,1); self.m.open_key.callback(); self.assertEqual(self.gui.opens,1)
        self.gui.finish_close(); self.m.open_key.callback(); self.assertEqual(self.gui.opens,2)
    def test_foreign_window(self):
        self.install_gui(); self.gui.active=True; self.gui.title='Other'; self.m.toggle_menu(); self.assertEqual((self.gui.opens,self.gui.closes),(0,0))
    def test_foreign_after_ours(self):
        self.open(); self.gui.title='Other'; self.m.disabled(); self.assertEqual(self.gui.closes,0)
    def test_draft_and_apply(self):
        self.open(); self.gui.imgui.edits={'Damage multiplier##damage':2.7}; self.m.draw()
        self.assertEqual(self.m.ALL[0].value,1.0); self.assertEqual(self.m.mod.save_count,0)
        self.gui.imgui.edits={}; self.gui.imgui.clicks={'Apply and save'}; self.m.draw()
        self.assertEqual(self.m.ALL[0].value,2.7); self.assertEqual(self.m.mod.save_count,1)
    def test_each_category(self):
        self.open()
        for i,(_,label,options) in enumerate(self.m.CATEGORIES):
            self.gui.imgui.clicks={label+(' *' if i==self.m._category else '')+'##cat'+str(i)}
            self.gui.imgui.labels=[]; self.m.draw(); self.assertEqual(self.m._category,i)
            for o in options: self.assertIn(o.display_name+'##'+o.identifier,self.gui.imgui.labels)
    def test_reset(self):
        self.m.apply({'damage':4,'settings_test':True}); self.m.reset()
        self.assertEqual(self.m.ALL[0].value,1); self.assertFalse(self.m.probe.value)
    def test_save_failure_rolls_back_memory(self):
        self.m.mod.fail_save=True
        with self.assertRaises(OSError): self.m.apply({'damage':4})
        self.assertEqual(self.m.ALL[0].value,1)
    def test_close_discards(self):
        self.open(); self.m._pending['damage']=2.0; self.m.close_menu(); self.assertFalse(self.m._pending); self.assertEqual(self.m.ALL[0].value,1)
    def test_discard_preserves_console(self):
        self.open(); self.m._pending['damage']=2; self.m.ALL[0].value=3
        self.gui.imgui.clicks={'Discard draft'}; self.m.draw(); self.assertFalse(self.m._pending); self.assertEqual(self.m.ALL[0].value,3)
    def test_disable_closes(self): self.open(); self.m.disabled(); self.assertEqual(self.gui.closes,1)
    def test_no_write_on_draw(self): self.open(); self.m.draw(); self.assertEqual(self.m.mod.save_count,0)

    def test_progression_six_defaults_ranges(self):
        opts=self.m.CATEGORIES[1][2]
        self.assertEqual(len(opts),6)
        for o in opts:
            self.assertEqual((o.default_value,o.min_value,o.max_value),(1.0,1.0,10.0))
            self.assertEqual(self.m.normalize(o,50),10.0)
            self.assertEqual(self.m.normalize(o,0),1.0)
    def test_old_preview_does_not_migrate(self):
        self.m.mod.restore({'options':{'progression':{'xp':5,'money':4}},'enabled':True})
        self.assertTrue(all(o.value==1.0 for o in self.m.CATEGORIES[1][2]))
    def test_progression_roundtrip_reset(self):
        opts=self.m.CATEGORIES[1][2]; self.m.apply({o.identifier:8.5 for o in opts})
        saved=self.m.mod.saved; self.m.reset(); self.assertTrue(all(o.value==1 for o in opts))
        self.m.mod.restore(saved); self.assertTrue(all(o.value==8.5 for o in opts))
    def test_discovery_metadata_only(self):
        class Obj:
            def __dir__(self): return ['AwardExperience','Currency','PrivateName','_xp']
            def __getattr__(self,name): raise AssertionError('value read forbidden')
        calls=[]
        def find_all(name,exact): calls.append((name,exact)); return [Obj()]
        self.check_discovery(types.SimpleNamespace(find_all=find_all), 'PlayerState.AwardExperience', absent='PrivateName')
        self.assertEqual(calls,[('PlayerController',False),('PlayerState',False)])
        self.assertEqual(self.m.mod.save_count,0)
    def check_discovery(self,sdk,expected,absent=None):
        old=sys.modules.get('unrealsdk'); sys.modules['unrealsdk']=sdk
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out: self.m.inspect_reward_members()
            self.assertIn(expected,out.getvalue())
            if absent: self.assertNotIn(absent,out.getvalue())
        finally:
            if old is None: sys.modules.pop('unrealsdk',None)
            else: sys.modules['unrealsdk']=old
    def test_discovery_disabled(self):
        self.m.mod.is_enabled=False
        self.check_discovery(types.SimpleNamespace(find_all=lambda *a,**k: self.fail('unexpected lookup')), 'Enable the mod first')
    def test_discovery_limit(self):
        self.check_discovery(types.SimpleNamespace(find_all=lambda *a,**k: [None]*33),'too many objects')
    def test_discovery_error(self):
        def fail(*a,**k): raise RuntimeError('mock reflection failure')
        self.check_discovery(types.SimpleNamespace(find_all=fail),'reflection unavailable (RuntimeError)')
    def test_discovery_not_automatic(self):
        self.check_discovery(types.SimpleNamespace(find_all=lambda *a,**k: []),'REWARD METADATA END')
        self.assertEqual(self.m.mod.hooks,[])
        self.assertNotIn('inspect_reward_members', [getattr(k.callback,'__name__','') for k in self.m.mod.keybinds])

if __name__=='__main__': unittest.main(verbosity=2)
