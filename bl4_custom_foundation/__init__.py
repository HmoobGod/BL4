"""Community integration: explicit solo session controls, progression HOLD."""
import math
import sys
import threading
import time
from pathlib import Path
from mods_base import BoolOption, ButtonOption, NestedOption, SliderOption, build_mod, keybind
from .gameplay_fields import FEATURES, RARITY_KEYS
from .session_control import Controller, DAMAGE_HOLD
from .ground_speed import is_player_animation, sprinting
from .gameplay_fields import identity

TITLE = 'BL4 Custom - Community Integration v0.7.7-experimental'
DESCRIPTION = 'Manual preview by default; optional persistent solo gameplay requires separate master and feature opt-in.'


def changed(option, value):
    print(f'[BL4 Custom] Settings test: {value}')


# Retain the v0.1.1 top-level settings identifier for migration.
probe = BoolOption('settings_test', False, display_name='Settings Test',
                   description='Diagnostic only. No gameplay changes.', on_change_while_enabled=changed)


def slider(identifier, label, minimum=0.5):
    return SliderOption(identifier, 1.0, minimum, 5.0, step=0.1, is_integer=False,
                        display_name=label, description=DESCRIPTION)


def rarity_slider(identifier, label):
    return SliderOption(identifier, 1.0, FEATURES[identifier][1], 10.0, step=0.1, is_integer=False,
                        display_name=label, description='Experimental world-session rarity weight; 1x restores.')


def progression_slider(identifier, label):
    return SliderOption(identifier, 1.0, 1.0, 10.0, step=0.1, is_integer=False,
                        display_name=label, description='Preview only - reward hook not verified.')


def toggle(identifier, label):
    return BoolOption(identifier, False, display_name=label, description=DESCRIPTION)


CATEGORIES = [
    ('combat', 'Combat', [slider('damage', 'Damage multiplier'), slider('fire_rate', 'Fire rate multiplier'), slider('reload', 'Reload speed multiplier'), slider('fire_damage', 'Fire damage multiplier'),
        slider('damage_taken', 'Damage taken multiplier', minimum=0.1), slider('shock_damage', 'Shock damage multiplier'),
        slider('corrosive_damage', 'Corrosive damage multiplier'), slider('cryo_damage', 'Cryo damage multiplier'),
        slider('radiation_damage', 'Radiation damage multiplier')]),
    ('progression', 'XP and Progression', [progression_slider('progress_character_xp', 'Character XP'),
        progression_slider('progress_specialization_xp', 'Specialization XP'),
        progression_slider('progress_money', 'Money'),
        progression_slider('progress_eridium', 'Eridium'),
        progression_slider('progress_enemy_xp', 'Enemy kill XP'),
        progression_slider('progress_mission_xp', 'Mission XP')]),
    ('loot', 'Loot and Drop Rates', [slider('drops', 'Drop rate multiplier'), progression_slider('overall_loot_luck', 'Overall loot luck'), rarity_slider('common_weight', 'Common rarity weight'), rarity_slider('uncommon_weight', 'Uncommon rarity weight'), rarity_slider('rare_weight', 'Rare rarity weight'), rarity_slider('epic_weight', 'Epic rarity weight'), rarity_slider('legendary_weight', 'Legendary rarity weight (selected)')]),
    ('inventory', 'Inventory', [slider('capacity', 'Capacity multiplier')]),
    ('movement', 'Movement', [slider('sprint', 'Sprint speed multiplier'), slider('jump', 'Jump velocity multiplier'), SliderOption('walk_speed', 1., 1., 3., step=.1, is_integer=False, display_name='Ground speed floor (reference multiplier)', description='1x restores; higher raises walk/sprint floor. Actual speed varies.')]),
    ('automation', 'Automation', [toggle('auto_reload', 'Automatic reload'), toggle('auto_loot', 'Automatic loot pickup')]),
    ('quality', 'Quality of Life', [toggle('auto_ammo', 'Automatic ammo pickup'), slider('cooldown', 'Cooldown multiplier'), slider('repair_cooldown', 'Repair-kit cooldown duration multiplier', minimum=0.1), slider('healing_received', 'Healing received multiplier'), slider('repair_duration', 'Repair-kit healing duration multiplier')]),
    ('enemies', 'Enemy Difficulty', [slider('enemy_health', 'Enemy health multiplier'), slider('enemy_damage', 'Enemy damage multiplier')]),
    ('menu', 'Custom Menu', [probe]),
]
PREVIEW = [o for _, _, items in CATEGORIES for o in items if o is not probe]
# Explicit opt-in, separate from legacy saved preview values. Defaults stay vanilla.
auto_master = BoolOption('persistent_master', False, display_name='Persistent gameplay (experimental)')
auto_consent = BoolOption('persistent_offline', False, display_name='I use Offline Local Only; tuning mods disabled')
AUTO_OPTIONS = {k: BoolOption('persistent_' + k, False, display_name='Auto-enable ' + FEATURES[k][0])
                for k in FEATURES if k not in DAMAGE_HOLD}
AUTO_SETTINGS = [auto_master, auto_consent, *AUTO_OPTIONS.values()]
_ground_selection = next(o for o in PREVIEW if o.identifier == 'walk_speed')
ALL = PREVIEW + [probe] + AUTO_SETTINGS
_auto_owned = False
_auto_blocked = ''
_auto_status = 'Not active; opt in to persistent gameplay.'
_auto_ground = None
_auto_api = None
_auto_next = 0.0
_auto_edits = {}
_auto_edit_at = 0.0
_auto_last_diagnostic = ''

_pending = {}
_category = 0
_status = 'No unapplied changes.'
_backend = None
_reward_summary = "Not checked. Read-only checks are available on demand."
_menu_close_ready = False
_compact_view = None  # default compact in persistent mode, full in manual mode


def normalize(option, value):
    if isinstance(option, BoolOption):
        return value if type(value) is bool else option.default_value
    if type(value) not in (int, float) or not math.isfinite(value):
        return option.default_value
    return round(max(option.min_value, min(option.max_value, value)), 1)


def apply(values):
    """Only write mod-owned option objects; SDK owns persistence."""
    previous = [(o, o.value) for o in ALL if o.identifier in values]
    if not previous:
        return
    try:
        for o, _ in previous:
            o.value = normalize(o, values[o.identifier])
        mod.save_settings()
    except Exception:
        for o, old in previous:
            o.value = old
        raise


def reset(_option=None):
    global _status
    pause_auto("vanilla reset requested")
    cancel_activation("vanilla reset requested")
    if _controller is not None and _controller.records:
        request_stop('Restore vanilla defaults', immediate=True)
        if _controller.records or _controller.fault:
            _status = 'Restoration pending or faulted; exit game if instructed.'
            return
    try:
        apply({o.identifier: o.default_value for o in ALL})
    except Exception as exc:
        print(f'[BL4 Custom] Reset failed: {exc}; check SDK settings before restarting.')
        return
    _pending.clear()
    _status = 'Vanilla selection defaults restored.'
    print('[BL4 Custom] ' + _status)


def own_window(lib):
    """Check live runner title, not just the shared library open flag."""
    hello = lib.hello_imgui
    if not hello.is_using_hello_imgui():
        return False
    runner = hello.get_runner_params()
    return runner is not None and runner.app_window_params.window_title == TITLE


def close_menu():
    global _backend, _menu_thread, _menu_close_ready
    _menu_thread = None
    _menu_close_ready = False
    cancel_activation("menu closed before execution")
    flush_auto_edits(force=True)
    lib = _backend
    _pending.clear()
    try:
        if lib is not None and own_window(lib):
            lib.close_window()
    except Exception as exc:
        print(f'[BL4 Custom] Close failed: {exc}. Use the window close control or restart.')
    finally:
        _backend = None


def sync_window_close():
    """Use the owned runner's exit flag; never touch another mod's window."""
    lib = _backend
    if lib is None:
        return False
    try:
        if not own_window(lib):
            close_menu()
            return True
        runner = lib.hello_imgui.get_runner_params()
        if getattr(runner, 'app_shall_exit', False):
            close_menu()
            return True
    except Exception:
        # The explicit Close menu remains available if runner inspection fails.
        pass
    return False


def gui_close_pressed(ui):
    """Read focused ImGui input, without polling OS keys or synthesizing input."""
    global _menu_close_ready
    try:
        enum = ui.Key
        key = str(open_key.key or '').lower()
        keys = [enum.escape]
        if key in {f'f{i}' for i in range(1, 13)}:
            keys.append(getattr(enum, key))
        # Do not close on the keypress that created the window.
        if not _menu_close_ready:
            _menu_close_ready = not any(ui.is_key_down(k) for k in keys)
            return False
        return any(ui.is_key_pressed(k, False) for k in keys)
    except (AttributeError, TypeError):
        return False


def persistent_feature_status(key):
    """Render from saved/draft settings and existing receipts; never query the SDK here."""
    if AUTO_OPTIONS[key].value is not True:
        return 'Off (restoring)' if _controller is not None and key in _controller.records else 'Off'
    if _controller is not None and _controller.fault:
        return 'FAULT / exit game'
    if _auto_blocked or not auto_allowed():
        return 'Paused / HOLD'
    if key in _auto_edits:
        return 'Saving selection...'
    selected = next(o.value for o in PREVIEW if o.identifier == key)
    record = _controller.records.get(key) if _auto_owned and _controller is not None else None
    if selected == 1.0:
        return 'Restoring' if record else '1x / vanilla'
    if record is not None and record.get('selection') == selected:
        return 'Active: ' + str(selected) + 'x (value verified)'
    return 'Waiting for gameplay callback'


def draw():
    global _category, _status, _compact_view
    if _backend is None or not mod.is_enabled:
        return
    if sync_window_close():
        return
    expire_activation()
    flush_auto_edits()
    ui = _backend.imgui
    if gui_close_pressed(ui):
        close_menu()
        return
    ui.text('BL4 CUSTOM | v0.7.7-experimental')
    ui.text_wrapped('Manual or persistent solo activation. XP and unsupported fields HOLD.')
    ui.text_wrapped('Restore all BEFORE travel, character changes, or network changes. Offline Local Only only.')
    global _offline_confirmed
    if auto_master.value is not True:
        edited, confirmed = ui.checkbox('Offline Local Only; other tuning mods disabled##owner_confirm', _offline_confirmed)
        if edited:
            _offline_confirmed = bool(confirmed)
            if not _offline_confirmed:
                request_stop('offline confirmation withdrawn', immediate=True)
    for option in (auto_consent, auto_master):
        changed_auto, selected_auto = ui.checkbox(option.display_name + '##' + option.identifier, option.value is True)
        if changed_auto and selected_auto is not option.value:
            set_auto_setting(option, selected_auto)
    if auto_master.value is True:
        ui.text_wrapped('Persistent: ' + (_auto_blocked or _auto_status))
        if auto_consent.value is not True:
            ui.text_wrapped('HOLD: enable saved offline preference first.')
    compact = auto_master.value is True if _compact_view is None else _compact_view
    edited_compact, compact_value = ui.checkbox('Compact menu (hide preview-only controls)', compact)
    if edited_compact:
        _compact_view = compact = bool(compact_value)
    if not compact or _loot_test_status.startswith(('HOLD', 'FAULT', 'STOP')):
        ui.text_wrapped(_loot_test_status)
    ui.text("Session monitor: " + monitor_status())
    if _controller is not None and _controller.fault:
        ui.text_wrapped('FAULT LATCHED: exit game immediately; do not play.')
    if _controller is not None:
        ui.text_wrapped('Active fields (gameplay unverified): ' + (', '.join(k + ' ' + str(r.get('selection', '?')) + 'x' for k, r in _controller.records.items()) or 'None / vanilla'))
        if _controller.records and not _controller.fault and ui.button('Restore ALL active gameplay values'):
            pause_auto('F8 restore all')
            request_stop('F8 restore all', immediate=True)
    ui.separator()
    for i, (_, name, _) in enumerate(CATEGORIES):
        if i % 2:
            ui.same_line()
        if ui.button(name + (' *' if i == _category else '') + '##cat' + str(i)):
            _category = i
    ui.separator()
    _, name, options = CATEGORIES[_category]
    ui.text(name)
    if compact:
        options = [o for o in options if o is probe or (o.identifier in FEATURES and o.identifier not in DAMAGE_HOLD)]
        if not options:
            ui.text('No supported gameplay controls here; turn off Compact menu to view previews.')
    if _category == 0 and not compact:
        ui.text_wrapped('General damage HOLD. Elemental and incoming damage are EXPERIMENTAL; actual hit effects unverified.')
    if _category == 1 and not compact:
        ui.text_wrapped('HOLD: all six reward hooks are unverified. These sliders only save preview values.')
        ui.text_wrapped(_reward_summary)
        if ui.button('Run read-only reward compatibility check'):
            inspect_attribute_compatibility()
    if _category == 2 and not compact:
        ui.text_wrapped('Offline Local Only ONLY. Restore before travel, character change, or changing network mode. Other loot mods must be disabled.')
        ui.text_wrapped(_loot_status)
        if ui.button('Read-only rarity check'):
            inspect_loot_readonly()
        ui.text_wrapped('Rarity weight is not a guaranteed drop probability. 0x common/uncommon is experimental; higher rarities stay positive.')
    if _category == 4 and not compact:
        ui.text_wrapped('Ground speed: select a new 1–3x value (old saved values may be out of range). 1x restores. 2x targets walk floor 1080 / sprint 1656 (reference units/s); not exact speed multiplier.')
    if compact and _category == 2:
        ui.text('Rarity weight is not guaranteed drop probability; 1x restores.')
    if compact and _category == 4:
        ui.text('Ground speed is a reference floor; 1x restores.')
    if _category == 8:
        ui.text_wrapped('Change the Open Custom Menu key in the SDK console Keybinds section. Default: F8.')
        ui.text('Current hotkey: ' + str(open_key.key or 'Unbound'))
    for o in options:
        value = _auto_edits.get(o.identifier, _pending.get(o.identifier, normalize(o, o.value)))
        label = o.display_name + '##' + o.identifier
        if (o.identifier not in FEATURES or o.identifier in DAMAGE_HOLD) and o is not probe:
            ui.text_wrapped(o.display_name + ' — HOLD / preview only')
        if isinstance(o, BoolOption):
            edited, value = ui.checkbox(label, value)
        else:
            edited, value = ui.slider_float(label, value, o.min_value, o.max_value, '%.1fx')
            if o.identifier in RARITY_KEYS or o.identifier.startswith('progress_') or o.identifier == 'overall_loot_luck':
                # Older bindings may omit input_float; slider remains available.
                numeric = getattr(ui, 'input_float', None)
                if callable(numeric):
                    try:
                        typed, entered = numeric('Value##numeric_' + o.identifier, value, .1, 1., '%.1f')
                        if typed and type(entered) in (int, float) and math.isfinite(entered):
                            edited, value = True, entered
                    except (TypeError, AttributeError):
                        pass
        if edited:
            if auto_master.value is True and o.identifier in AUTO_OPTIONS:
                queue_auto_edit(o, value)
            else:
                _pending[o.identifier] = normalize(o, value)
                _status = 'Unapplied changes.' 
    for selected in options:
        key = selected.identifier
        if key not in FEATURES or key in DAMAGE_HOLD:
            continue
        name = FEATURES[key][0]
        if key in ('fire_damage', 'shock_damage', 'corrosive_damage', 'cryo_damage', 'radiation_damage'):
            ui.text_wrapped('Experimental elemental modifier; actual hit damage unverified. 1x restores.')
        if auto_master.value is True:
            option = AUTO_OPTIONS[key]
            changed_auto, selected_auto = ui.checkbox(option.display_name + '##' + option.identifier, option.value is True)
            if changed_auto and selected_auto is not option.value:
                set_auto_setting(option, selected_auto)
            ui.text(name + ': ' + persistent_feature_status(key))
            continue
        if key in ('damage_taken', 'repair_cooldown', 'fire_damage', 'shock_damage', 'corrosive_damage', 'cryo_damage', 'radiation_damage'):
            ui.text_wrapped('EXPERIMENTAL: gameplay effect unverified. Test separately on a backup character.')
        if key in ('repair_cooldown', 'damage_taken'):
            ui.text_wrapped('1x restores baseline. ' + ('Lower duration is faster.' if key == 'repair_cooldown' else 'Lower means less damage taken.'))
        if not (_controller is not None and _controller.fault) and ui.button('Activate / Update ' + name + '##activate_' + key):
            activate_feature(key, _pending.get(key, selected.value))
        if _controller is not None and key in _controller.records and not _controller.fault:
            if ui.button('Restore ' + name + '##restore_' + key):
                if _valid_test_backend() and _monitor_thread == threading.get_ident():
                    _controller.restore_selected(key, 'F8 restore')
                else:
                    request_stop('F8 restore requested outside verified hook', immediate=False)
    ui.separator()
    if ui.button('Apply and save'):
        try:
            apply(_pending)
            _pending.clear()
            _status = 'Saved preview settings. No gameplay changes.'
        except Exception as exc:
            _status = 'Save failed; check SDK settings before restarting.'
            print(f'[BL4 Custom] {exc}')
    ui.same_line()
    if ui.button('Discard draft'):
        _pending.clear()
        _status = 'Draft discarded.'
    if ui.button('Restore vanilla defaults'):
        reset()
    ui.same_line()
    if ui.button('Close menu'):
        close_menu()
        return
    ui.text_wrapped(_status)


def toggle_menu(_option=None):
    global _backend, _status, _menu_thread, _menu_close_ready
    if not mod.is_enabled:
        print('[BL4 Custom] Enable the mod first.')
        return
    # Never import/initialize a native dependency ourselves. SDK must load it normally.
    lib = sys.modules.get('blimgui')
    if lib is None or getattr(lib, '__version__', None) != '1.1':
        print('[BL4 Custom] BLImGui 1.1 not loaded. Console fallback remains available.')
        return
    try:
        if own_window(lib):
            if _backend is lib:
                close_menu()
            else:
                print('[BL4 Custom] Window is closing; try again after a moment.')
            return
        # is_window_open may already be false while native teardown is pending.
        if lib.hello_imgui.is_using_hello_imgui() or lib.is_window_open():
            print('[BL4 Custom] Another BLImGui window is active; close it first.')
            return
        ensure_monitor()
        _menu_close_ready = False
        _pending.clear()
        _status = 'No unapplied changes.'
        _backend = lib
        _menu_thread = threading.get_ident()
        # BLImGui 1.1 stores a shared default callback. Restore it after the runner
        # captures ours so another mod's default window never inherits our controls.
        previous_callback = lib.IMPL._draw_callback
        try:
            lib.create_window(TITLE, 620, 560, draw)
        finally:
            lib.set_draw_callback(previous_callback)
        if not own_window(lib):
            _backend = None
            _menu_thread = None
            print('[BL4 Custom] Window did not open; use console fallback.')
    except Exception as exc:
        print(f'[BL4 Custom] GUI unavailable: {exc}. Console fallback remains available.')
        close_menu()


def inspect_reward_members(_option=None):
    """One-shot explicit console-only metadata discovery, no gameplay reads/writes or hooks."""
    if not mod.is_enabled:
        print('[BL4 Custom] Enable the mod first.')
        return
    sdk = sys.modules.get('unrealsdk')
    if sdk is None:
        print('[BL4 Custom] SDK reflection unavailable.')
        return
    keywords = ('experience', 'xp', 'reward', 'currency', 'cash', 'money', 'eridium',
                'mission', 'kill', 'specialization', 'netmode', 'localplayer', 'authority')
    print('[BL4 Custom] REWARD METADATA BEGIN (names only)')
    for class_name in ('PlayerController', 'PlayerState'):
        try:
            objects = sdk.find_all(class_name, exact=False)
            if len(objects) > 32:
                print(f'[BL4 Custom] {class_name}: too many objects; skipped')
                continue
            names = set()
            for obj in objects:
                names.update(n for n in dir(obj) if not n.startswith('_')
                             and any(k in n.lower() for k in keywords))
            print(f'[BL4 Custom] {class_name}: {len(objects)} objects, {len(names)} matching names')
            for name in sorted(names)[:100]:
                print('[BL4 Custom] ' + class_name + '.' + name)
            if len(names) > 100:
                print('[BL4 Custom] Output truncated')
        except Exception as exc:
            print(f'[BL4 Custom] {class_name}: reflection unavailable ({type(exc).__name__})')
    print('[BL4 Custom] REWARD METADATA END; no game values changed.')



# Targeted reflection only; no native calls, modifiers, hooks or game-state writes.
ATTRIBUTE_API = ('GetValueOfAttribute', 'AddModifierToGbxAttribute', 'RemoveAttributeModifier')
ATTRIBUTE_NAMES = ('Att_CombatXP_Multiplier', 'Att_PickupCash_Multiplier', 'Att_PickupEridium_Multiplier')


def attribute_report(sdk):
    lines = ['BL4 Custom v0.7.7-experimental - read-only compatibility report',
             'All reward modifications HOLD. Metadata is not proof of live behavior.']
    binding = sys.modules.get('unrealsdk.unreal')
    lines.append('FGbxDefPtr binding visible: ' + str(hasattr(binding, 'FGbxDefPtr')))
    functions = sdk.find_all('Function', exact=False)
    matched = {name: [] for name in ATTRIBUTE_API}
    for fn in functions:
        name = str(fn.Name)
        if name in matched:
            path = fn._path_name()
            if path.startswith('/Script/'):
                matched[name].append((path, fn))
    for name in ATTRIBUTE_API:
        entries = matched[name]
        lines.append(name + ': ' + str(len(entries)) + ' candidate(s)')
        for path, fn in entries[:4]:
            lines.append('  ' + path + ' params=' + str(fn.NumParams))
            for prop in list(fn._properties())[:24]:
                detail = '    ' + str(prop.Name) + ': ' + type(prop).__name__
                for member in ('Struct', 'Enum', 'PropertyClass'):
                    try:
                        target = getattr(prop, member, None)
                        if target is not None:
                            detail += ' ' + member + '=' + target._path_name()
                    except Exception:
                        detail += ' ' + member + '=unavailable'
                lines.append(detail)
        if len(entries) > 4:
            lines.append('  truncated; not safe to resolve uniquely')
    structs = sdk.find_all('ScriptStruct', exact=False)
    names = ('GbxAttributeDef', 'GbxAttributeModifierHandle')
    for name in names:
        paths = sorted(set(x._path_name() for x in structs if str(x.Name) == name))
        lines.append(name + ': ' + (', '.join(paths[:8]) or 'not found'))
    lines.append('Candidate attribute identifiers (not resolved or evaluated): ' + ', '.join(ATTRIBUTE_NAMES))
    lines.append('Metadata section: no game values read or changed. No native reward or modifier function invoked.')
    return '\n'.join(lines), sum(bool(matched[n]) for n in ATTRIBUTE_API)



GETTER_PATH = '/Script/GbxEngine.GbxAttributeBlueprintLibrary:GetValueOfAttribute'
GETTER_SIGNATURE = (('AttributeDef', 'ZNameProperty'), ('ContextSource', 'ZObjectProperty'),
                    ('DefaultValue', 'ZFloatProperty'), ('ReturnValue', 'ZFloatProperty'))


def read_reward_attributes(sdk):
    """One-shot read on the current local authority pawn. Never install modifiers."""
    lines = ['Attribute read probe (no writes; standalone session not established by this check)']
    resolved = 0
    try:
        matches = [fn for fn in sdk.find_all('Function', exact=False)
                   if str(fn.Name) == 'GetValueOfAttribute' and fn._path_name() == GETTER_PATH]
        if len(matches) != 1:
            raise ValueError('getter not unique')
        fn = matches[0]
        signature = tuple((str(p.Name), type(p).__name__) for p in fn._properties())
        if fn.NumParams != 4 or signature != GETTER_SIGNATURE:
            raise ValueError('getter signature mismatch')
        library = fn.Outer.ClassDefaultObject
        getter = library.GetValueOfAttribute
        if getter.func._path_name() != GETTER_PATH:
            raise ValueError('bound getter mismatch')
        pc = sys.modules['mods_base'].get_pc(possibly_loading=True)
        if pc is None or pc.IsLocalPlayerController() is not True or pc.HasAuthority() is not True:
            raise ValueError('local authority controller unavailable')
        pawn = pc.Pawn
        if pawn is None or pawn.Class.Name is None:
            raise ValueError('player pawn unavailable')
        lines.append('Pawn class: ' + str(pawn.Class.Name))
        # A sentinel outside the expected reward range distinguishes missing definitions.
        sentinel = -123456.0
        for name in ATTRIBUTE_NAMES:
            try:
                value = getter(name, pawn, sentinel)
                if type(value) not in (int, float) or not math.isfinite(value):
                    lines.append(name + ': unexpected return type/value')
                elif value == sentinel:
                    lines.append(name + ': unresolved (default sentinel)')
                else:
                    lines.append(name + ': observed value ' + str(value))
                    resolved += 1
            except Exception as exc:
                lines.append(name + ': getter failed (' + type(exc).__name__ + ')')
    except Exception as exc:
        lines.append('Skipped: ' + type(exc).__name__ + ': ' + str(exc)[:160])
    lines.append(str(resolved) + '/3 non-sentinel getter results; no proof of earned reward effect.')
    lines.append('No modifier add/remove or reward-grant calls made. All gameplay effects HOLD.')
    return '\n'.join(lines), resolved

def report_path():
    # Archive and unpacked SDK layouts; refuse unexpected locations.
    for parent in Path(__file__).absolute().parents:
        if parent.name.lower() == 'sdk_mods' and parent.is_dir():
            settings = parent / 'settings'
            if settings.is_dir():
                return settings / 'bl4_custom_reward_report.txt'
    return None


def inspect_attribute_compatibility(_option=None):
    global _reward_summary
    if not mod.is_enabled:
        return
    sdk = sys.modules.get('unrealsdk')
    if sdk is None:
        _reward_summary = 'HOLD: SDK reflection unavailable.'
        return
    try:
        report, count = attribute_report(sdk)
    except Exception as exc:
        report = 'HOLD: compatibility scan failed (' + type(exc).__name__ + '). No gameplay changes.'
        count = 0
    readout, resolved = read_reward_attributes(sdk)
    report += '\n\n' + readout
    _reward_summary = 'HOLD: ' + str(count) + '/3 candidate APIs; ' + str(resolved) + '/3 attribute read results.'
    try:
        path = report_path()
        if path is None:
            raise OSError('SDK settings directory unavailable')
        path.write_text(report + '\n', encoding='utf-8')
        _reward_summary += ' Report saved in sdk_mods/settings/bl4_custom_reward_report.txt.'
    except Exception:
        _reward_summary += ' Report file unavailable; printed to SDK console.'
    print(report)


# Community interface reference: Loot Treadmill, Noah Lincke (MIT),
# commit 4852b34ac82c86c3093192fb029edab495fbb63a. See LICENSE-LootTreadmill.txt.
# Independent bounded transaction; no persistent gameplay activation in this build.
_menu_thread = None
_loot_test_status = 'Inactive. Select weight and activate explicitly.'
_controller = None
_offline_confirmed = False
_monitor_registered = False
_monitor_registering = False
_monitor_candidate = False
_monitor_attempted = False
_monitor_add_result = None
_monitor_thread = None
_monitor_seen = 0.0
_monitor_error = "not registered"
_activation_request = None
_live_lines = []
_loot_status = 'Optional read-only rarity check; activation validates its own field.'
_LOOT_BOOL_SIG = (('WorldContextObject', 'ZObjectProperty'), ('ReturnValue', 'ZBoolProperty'))
_LOOT_STATICS = '/Script/Engine.GameplayStatics:'
_LOOT_SYSTEM = '/Script/Engine.KismetSystemLibrary:'


def loot_bound(functions, path, sig):
    matches = [fn for fn in functions if fn._path_name() == path]
    if len(matches) != 1:
        raise ValueError('function unavailable or ambiguous: ' + path)
    fn = matches[0]
    if fn.NumParams != len(sig) or tuple((str(p.Name), type(p).__name__) for p in fn._properties()) != sig:
        raise ValueError('signature mismatch: ' + path)
    bound = getattr(fn.Outer.ClassDefaultObject, path.rsplit(':', 1)[1])
    if bound.func._path_name() != path:
        raise ValueError('bound function mismatch: ' + path)
    return bound


def loot_context(sdk, lines):
    pc = sys.modules['mods_base'].get_pc(possibly_loading=True)
    if pc is None or pc.Pawn is None or not getattr(pc, 'PlayerState', None):
        raise ValueError('load your solo character first')
    pawn = pc.Pawn
    if str(pawn.Class.Name) != 'OakCharacter':
        raise ValueError('OakCharacter unavailable')
    fs = [fn for fn in sdk.find_all('Function', exact=False)
          if str(fn.Name) in ('IsStandalone', 'IsServer', 'IsDedicatedServer', 'GetNumPlayerStates', 'GetGameState')]
    standalone = loot_bound(fs, _LOOT_SYSTEM+'IsStandalone', _LOOT_BOOL_SIG)
    server = loot_bound(fs, _LOOT_SYSTEM+'IsServer', _LOOT_BOOL_SIG)
    dedicated = loot_bound(fs, _LOOT_SYSTEM+'IsDedicatedServer', _LOOT_BOOL_SIG)
    count = loot_bound(fs, _LOOT_STATICS+'GetNumPlayerStates', (('WorldContextObject','ZObjectProperty'),('ReturnValue','ZIntProperty')))
    state_get = loot_bound(fs, _LOOT_STATICS+'GetGameState', (('WorldContextObject','ZObjectProperty'),('ReturnValue','ZObjectProperty')))
    def verify_session():
        solo, host, ded, players = standalone(pawn), server(pawn), dedicated(pawn), count(pawn)
        lines.append(f'IsStandalone={solo!r}; IsServer={host!r}; IsDedicatedServer={ded!r}; player states={players!r}')
        if (type(solo) is not bool or host is not True or ded is not False or type(players) is not int or players != 1
                or pc.IsLocalPlayerController() is not True or pc.HasAuthority() is not True):
            raise ValueError('local authoritative one-player host required')
        # Local Only + offline is an owner prerequisite; privacy is not independently verified.
    verify_session()
    state = state_get(pc)
    if state is None or str(state.Class.Name) != 'OakGameState' or not state._path_name():
        raise ValueError('GameState unavailable')
    lines.append('GameState class: ' + str(state.Class.Name))
    state_path = state._path_name()
    def verify_context():
        verify_session()
        fresh = state_get(pc)
        if fresh is None or str(fresh.Class.Name) != 'OakGameState' or fresh._path_name() != state_path:
            raise ValueError('GameState changed')
    return state, verify_context


def legendary_field(state):
    # Use the reflected property, never an address or native modifier handle.
    rarity = state.RarityState
    modifier = rarity.LegendaryModifier
    fields = [p for p in modifier._type._properties() if str(p.Name) == 'Value']
    if len(fields) != 1 or type(fields[0]).__name__ not in ('ZFloatProperty','ZDoubleProperty') or fields[0].ArrayDim != 1:
        raise ValueError('LegendaryModifier.Value is not a supported scalar property')
    return modifier


def legendary_value(state):
    value = legendary_field(state).Value
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1e6:
        raise ValueError('invalid or zero legendary weight')
    return float(value)


def loot_report_path():
    p = report_path()
    return None if p is None else p.with_name('bl4_custom_session_report.txt')


def _write_report(path, lines):
    if path is None:
        raise OSError('SDK settings directory unavailable')
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temporary.replace(path)


def inspect_loot_readonly():
    global _loot_status
    lines = ['BL4 Custom v0.7.7-experimental - read-only rarity diagnostic',
             'No gameplay writes; session report is a separate file.',
             f'F8 binding: {open_key.key!r}; mod enabled: {mod.is_enabled!r}']
    try:
        state, _ = loot_context(sys.modules.get('unrealsdk'), lines)
        value = legendary_value(state)
        lines.append(f'Observed LegendaryModifier.Value: {value!r}')
        _loot_status = 'READ PASS: legendary weight observed; no writes. Activation is explicit.'
    except Exception as exc:
        lines.append('Read preflight HOLD: ' + type(exc).__name__ + ': ' + str(exc)[:200])
        _loot_status = 'HOLD: rarity compatibility not confirmed; no writes.'
    try:
        path = loot_report_path()
        _write_report(None if path is None else path.with_name('bl4_custom_loot_read_report.txt'), lines + [_loot_status])
    except Exception as exc:
        _loot_status += ' Report unavailable: ' + type(exc).__name__ + ': ' + str(exc)[:120]
    print('\n'.join(lines + [_loot_status]))


def _valid_menu_backend():
    lib = _backend
    return (lib is not None and lib is sys.modules.get('blimgui')
            and getattr(lib, '__version__', None) == '1.1'
            and getattr(lib, 'THREADED_RENDERING', None) is False
            and type(lib.IMPL).__module__ == 'blimgui.backends.hook_based'
            and type(lib.IMPL).__name__ == 'HookBasedBackend'
            and own_window(lib))


def _valid_test_backend():
    return _valid_menu_backend() and _menu_thread == threading.get_ident()


# The community mod uses RarityState.LegendaryModifier.Value and baseline-relative
# updates. SDK addresses below are identity tokens only, never dereferenced or written.
_MONITOR_PATH = '/Script/Engine.CameraModifier:BlueprintModifyCamera'
_MONITOR_ID = 'bl4_custom_legendary_session_guard_v077exp'


def monitor_status():
    if _monitor_candidate and not _monitor_registered and not _monitor_error:
        return 'inserted; awaiting own callback (add_hook=' + repr(_monitor_add_result) + ')'
    if not _monitor_registered or _monitor_error:
        return 'unavailable: ' + _monitor_error
    if _monitor_thread is None:
        return 'registered; awaiting first callback'
    if time.monotonic() - _monitor_seen > 2.0:
        return 'registered; last callback stale'
    return 'callback observed' + (' (add_hook=False; own callback verified)' if _monitor_add_result is False else '')


def ensure_monitor():
    global _monitor_registered, _loot_test_status, _monitor_error, _monitor_registering
    global _monitor_candidate, _monitor_attempted, _monitor_add_result
    if _monitor_registering:
        return False
    _monitor_registering = True
    try:
        hooks = sys.modules['unrealsdk'].hooks
        kind = hooks.Type.POST_UNCONDITIONAL
        if _monitor_registered or _monitor_candidate:
            if hooks.has_hook(_MONITOR_PATH, kind, _MONITOR_ID) is True:
                _monitor_error = ''
                return True
            raise ValueError('previously registered monitor missing; restart required')
        if _monitor_attempted:
            raise ValueError('previous registration attempt failed; restart required')
        # Do not adopt, remove, or replace an existing identifier.
        before = hooks.has_hook(_MONITOR_PATH, kind, _MONITOR_ID)
        if before is not False:
            raise ValueError('v0.7.7-experimental monitor identifier already exists or cannot be checked; remove duplicate SDKMOD copies if present')
        _monitor_attempted = True
        _monitor_add_result = hooks.add_hook(_MONITOR_PATH, kind, _MONITOR_ID, monitor_tick)
        after = hooks.has_hook(_MONITOR_PATH, kind, _MONITOR_ID)
        if type(_monitor_add_result) is not bool or after is not True:
            raise ValueError('monitor registration unverified: add=' + repr(_monitor_add_result) + ', after=' + repr(after))
        # UnrealSDK v3.2.0 appends a new callback to an existing collection,
        # then incorrectly returns false. Only our actual callback can confirm
        # this candidate. No foreign/pre-existing hook is accepted.
        _monitor_candidate = True
        _monitor_registered = _monitor_add_result is True
        _monitor_error = ''
        return True
    except Exception as exc:
        _monitor_error = type(exc).__name__ + ': ' + str(exc)[:120]
        _loot_test_status = 'HOLD: session monitor unavailable: ' + _monitor_error
        return False
    finally:
        _monitor_registering = False


def report_live(message):
    global _loot_test_status
    _loot_test_status = message
    _live_lines.append(message)
    try:
        _write_report(loot_report_path(), ['BL4 Custom v0.7.7-experimental - community session control',
            'Offline Local Only owner prerequisite; privacy not independently verified.',
            'No direct grants, spawning, raw memory writes or save edits.'] + _live_lines[-150:])
        return True
    except Exception as exc:
        _loot_test_status += ' Report unavailable: ' + str(exc)[:120]
        print('[BL4 Custom] ' + _loot_test_status)
        return False


def bound_session(sdk):
    fs = [fn for fn in sdk.find_all('Function', exact=False) if str(fn.Name) in
          ('IsStandalone', 'IsServer', 'IsDedicatedServer', 'GetNumPlayerStates', 'GetGameState')]
    return tuple(loot_bound(fs, path, sig) for path, sig in (
        (_LOOT_SYSTEM+'IsStandalone', _LOOT_BOOL_SIG),
        (_LOOT_SYSTEM+'IsServer', _LOOT_BOOL_SIG),
        (_LOOT_SYSTEM+'IsDedicatedServer', _LOOT_BOOL_SIG),
        (_LOOT_STATICS+'GetNumPlayerStates', (('WorldContextObject','ZObjectProperty'),('ReturnValue','ZIntProperty'))),
        (_LOOT_STATICS+'GetGameState', (('WorldContextObject','ZObjectProperty'),('ReturnValue','ZObjectProperty')))))


def current_session(api):
    pc = sys.modules['mods_base'].get_pc(possibly_loading=True)
    if pc is None or pc.IsLocalPlayerController() is not True or pc.HasAuthority() is not True:
        raise ValueError('local authoritative controller unavailable')
    solo, server, dedicated, count, get_state = api
    state = get_state(pc)
    if state is None or str(state.Class.Name) != 'OakGameState':
        raise ValueError('OakGameState unavailable')
    pawn = pc.Pawn
    world = pawn if pawn is not None else pc
    if server(world) is not True or dedicated(world) is not False:
        raise ValueError('authoritative non-dedicated state unavailable')
    players, standalone = count(world), solo(world)
    eligible = (type(players) is int and players == 1 and type(standalone) is bool
                and pawn is not None and str(pawn.Class.Name) == 'OakCharacter'
                and getattr(pc, 'PlayerState', None) is not None)
    return pc, pawn, state, eligible


def conflicting_mods():
    # Do not import third-party mods or invoke their private APIs.
    known = {'loottreadmill', 'rarityremover', 'damageandmore', 'bl4damageandmore',
             'resourcesandcooldowns', 'bl4resourcesandcooldowns', 'bl4playermovement',
             'squ1ggsboostingtools', 'apexmovement', 'apexspeed', 'autosprint', 'omnisprint'}
    for name, module in tuple(sys.modules.items()):
        if '.' in name or name.replace('_', '').casefold() not in known:
            continue
        candidate = getattr(module, 'mod', None)
        if candidate is None or getattr(candidate, 'is_enabled', None) is not False:
            return True
    return False


def request_stop(reason, *, immediate=False):
    global _offline_confirmed, _auto_blocked, _auto_ground
    _offline_confirmed = False
    if _auto_owned or auto_master.value is True:
        _auto_blocked = reason + '; toggle master to retry'
        _auto_ground = None
    cancel_activation(reason)
    if _controller is None or not _controller.records or _controller.fault:
        return
    if immediate and _valid_test_backend() and _monitor_thread == threading.get_ident():
        _controller.restore_all(reason)
    else:
        _controller.stop_pending = reason
        report_live('STOP PENDING: ' + reason + '; wait for game hook. If not restored, exit game.')


def cancel_activation(reason):
    global _activation_request
    if _activation_request is not None:
        _activation_request = None
        report_live('HOLD: queued activation cancelled: ' + reason)


def expire_activation():
    if _activation_request is not None and time.monotonic() >= _activation_request[3]:
        cancel_activation('no matching game-hook callback within 3 seconds; ' + monitor_status())


_GROUND_PATH = '/Script/Engine.AnimInstance:BlueprintUpdateAnimation'
_GROUND_ID = 'bl4_custom_ground_speed_v077exp'
_ground_inserted = False
_ground_attempted = False
_ground_anim_id = None
_ground_seen = 0.0

def ensure_ground_hook():
    global _ground_inserted, _ground_attempted
    hooks = sys.modules['unrealsdk'].hooks
    kind = hooks.Type.POST
    if _ground_inserted:
        return hooks.has_hook(_GROUND_PATH, kind, _GROUND_ID) is True
    if _ground_attempted or hooks.has_hook(_GROUND_PATH, kind, _GROUND_ID) is not False:
        return False
    _ground_attempted = True
    result = hooks.add_hook(_GROUND_PATH, kind, _GROUND_ID, ground_tick)
    _ground_inserted = type(result) is bool and hooks.has_hook(_GROUND_PATH, kind, _GROUND_ID) is True
    return _ground_inserted


def ground_tick(obj, *_):
    global _ground_anim_id, _ground_seen, _activation_request, _controller, _auto_ground, _auto_blocked
    request = _activation_request
    automatic = _auto_ground is not None and _auto_owned
    queued = request is not None and request[0] == 'walk_speed'
    if automatic:
        request = ('walk_speed', _auto_ground[0], _monitor_thread, _auto_ground[1])
        queued = True
    elif _auto_owned:
        queued = False  # manual requests may never cross into automatic mode
    active = _controller is not None and 'walk_speed' in _controller.records
    if not _ground_inserted or not (queued or active):
        return
    if active and (_controller.busy or _controller.fault):
        return
    try:
        if _ground_anim_id is not None and identity(obj) != _ground_anim_id and active:
            return
        if threading.get_ident() != _monitor_thread or time.monotonic() - _monitor_seen > 2.0:
            return
        hooks = sys.modules['unrealsdk'].hooks
        if (not _monitor_registered or hooks.has_hook(_MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL, _MONITOR_ID) is not True
                or hooks.has_hook(_GROUND_PATH, hooks.Type.POST, _GROUND_ID) is not True):
            return
        if not (mod.is_enabled and (auto_allowed() if _auto_owned else _offline_confirmed) and not conflicting_mods()):
            return  # camera guard restores; never apply while ineligible
        if _auto_owned:
            desired_speed = _ground_selection.value if AUTO_OPTIONS['walk_speed'].value is True and _ground_selection.value != 1.0 else None
            if desired_speed is None:
                return  # camera restores; no animation writes after toggle-off
            if automatic and ('walk_speed' in _auto_edits or desired_speed != request[1]):
                _auto_ground = None
                return
        if queued and (request[2] != threading.get_ident() or time.monotonic() >= request[3] or (not automatic and not _valid_menu_backend())):
            if automatic:
                _auto_ground = None
                _auto_blocked = 'Animation activation expired; toggle master to retry'
                return
            else:
                cancel_activation('ground activation expired or F8 closed')
            queued = False
        if not (queued or active):
            return
        sdk = sys.modules['unrealsdk']
        # Initial activation obtains the same strict context as all session features.
        if _auto_owned:
            if _controller is None:
                return
            context = _controller.context
        elif _controller is None or not _controller.records:
            api = bound_session(sdk)
            context = lambda: current_session(api)
        else:
            context = _controller.context
        pc, pawn, state, eligible = context()
        if not eligible or not is_player_animation(pc, pawn, obj):
            return
        if automatic and _auto_ground[2] != tuple(identity(x) for x in (pc, pawn, state)):
            _auto_ground = None
            return  # stale request; camera can schedule afresh for eligible context
        _ground_anim_id = identity(obj)
        _ground_seen = time.monotonic()
        stance = sprinting(pawn)
        if queued:
            if automatic:
                _auto_ground = None
                if not _controller.activate('walk_speed', request[1], ground_sprinting=stance):
                    _auto_blocked = 'Ground activation failed; toggle master to retry'
                return
            _activation_request = None
            if _controller is None or not _controller.records:
                _controller = Controller(context, sdk.unreal.WeakPointer, report_live, threading.get_ident)
            _controller.activate('walk_speed', request[1], ground_sprinting=stance)
        elif active:
            _controller.ground_frame(stance, observed=(pc, pawn, state, eligible))
            if _auto_owned and 'walk_speed' not in _controller.records:
                _auto_blocked = 'Ground frame stopped; toggle master to retry'
                _auto_ground = None
    except Exception as exc:
        if queued:
            if automatic:
                _auto_ground = None
                _auto_blocked = 'Ground callback failed; toggle master to retry'
            else:
                cancel_activation('ground callback failed: ' + str(exc)[:100])
        if active:
            request_stop('ground callback failed: ' + str(exc)[:100])


def monitor_tick(*_):
    global _monitor_thread, _monitor_seen, _offline_confirmed, _activation_request
    global _monitor_registered, _monitor_error
    if not _monitor_registered:
        if not _monitor_candidate:
            return
        try:
            hooks = sys.modules['unrealsdk'].hooks
            if hooks.has_hook(_MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL, _MONITOR_ID) is not True:
                return
            _monitor_registered = True
            _monitor_error = ''
        except Exception:
            return
    if globals().get('mod') is None:
        return  # SDK can enable while build_mod has not returned yet
    _monitor_thread = threading.get_ident()
    _monitor_seen = time.monotonic()
    if _backend is not None:
        sync_window_close()
    if auto_master.value is True or _auto_owned:
        auto_tick()
        report_auto_status_change()
        return
    # No reflection, conflict scans, or report I/O in the inactive camera hook.
    if _activation_request is None and not (_controller is not None and _controller.records):
        return
    try:
        permitted = mod.is_enabled and _offline_confirmed and not conflicting_mods()
    except Exception:
        permitted = False
    if _controller is not None and _controller.records:
        if _controller.busy:
            return
        if 'walk_speed' in _controller.records and time.monotonic() - _ground_seen > 2.0:
            _controller.restore_all('local animation callback stale')
        else:
            _controller.tick(permitted)
        if not _controller.records or _controller.fault:
            _offline_confirmed = False
    expire_activation()
    request = _activation_request
    if request is None or request[0] == 'walk_speed':
        return
    # Claim exactly once. No world writes from the button callback itself.
    _activation_request = None
    key, selection, ui_thread, deadline = request
    try:
        if _monitor_thread != ui_thread:
            raise ValueError('game-hook callback thread differs from requesting F8 draw thread')
        if not _valid_menu_backend():
            raise ValueError('verified F8 window no longer open')
        if not permitted or not _offline_confirmed:
            raise ValueError('offline confirmation or conflict check failed before execution')
        hooks = sys.modules['unrealsdk'].hooks
        if not _monitor_registered or hooks.has_hook(_MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL, _MONITOR_ID) is not True:
            raise ValueError('session monitor not registered at execution')
        if _controller is not None and _controller.fault:
            raise ValueError('fault latched; exit game')
        execute_activation(key, selection)
    except Exception as exc:
        report_live('HOLD: game-hook execution rejected: ' + str(exc)[:160])
        if _controller is not None and _controller.records:
            request_stop('queued activation preflight failed', immediate=False)


def activate_feature(key, selection):
    global _activation_request
    try:
        if _controller is not None and _controller.fault:
            raise ValueError('fault latched; exit game')
        if not mod.is_enabled:
            raise ValueError('mod disabled')
        if auto_master.value is True or _auto_owned:
            raise ValueError('disable persistent master before manual activation')
        if not _valid_menu_backend():
            raise ValueError('verified BLImGui 1.1 hook-based F8 window required')
        if not _offline_confirmed:
            raise ValueError('confirm offline Local Only in F8')
        if conflicting_mods():
            raise ValueError('disable overlapping tuning mods')
        if key in DAMAGE_HOLD:
            raise ValueError('feature HOLD: actual damage unverified')
        if not ensure_monitor():
            raise ValueError('session monitor unavailable: ' + _monitor_error)
        if key == 'walk_speed' and not ensure_ground_hook():
            raise ValueError('local animation hook unavailable')
        expire_activation()
        if _activation_request is not None:
            raise ValueError('another activation is already queued')
        if not report_live('QUEUED ' + key + ': ' + repr(selection) + 'x; ' + monitor_status()):
            return
        _activation_request = (key, selection, threading.get_ident(), time.monotonic() + 3.0)
    except Exception as exc:
        report_live('HOLD: ' + str(exc)[:160])
        if _controller is not None and _controller.records and _activation_request is None:
            request_stop('activation preflight failed', immediate=False)


def execute_activation(key, selection):
    global _controller
    # Called exclusively by monitor_tick after the explicit queued F8 action.
    if _controller is None or not _controller.records:
        sdk = sys.modules['unrealsdk']
        api = bound_session(sdk)
        _controller = Controller(lambda: current_session(api), sdk.unreal.WeakPointer,
                                 report_live, threading.get_ident)
    _controller.activate(key, selection)



def auto_allowed():
    return (getattr(globals().get('mod'), 'is_enabled', False) is True
            and auto_master.value is True and auto_consent.value is True
            and not _auto_blocked)


def set_auto_setting(option, value):
    global _auto_blocked, _auto_ground, _auto_next
    try:
        edits = dict(_auto_edits) if option is auto_master and value is False else {}
        apply({**edits, option.identifier: value})
    except Exception as exc:
        _auto_blocked = 'Settings save failed; toggle master to retry'
        if option is auto_master and value is False:
            auto_master.value = False
            _auto_edits.clear()
            _auto_ground = None
            report_live('HOLD: master off in memory; saved settings may still be on, check before restart')
        report_live('HOLD: ' + str(exc)[:120])
        return
    if option is auto_master:
        _auto_ground = None
        _auto_edits.clear()
        _auto_blocked = ''
        _auto_next = 0.0
        cancel_activation('persistent mode changed')
        _pending.clear()
        if value is True:
            ensure_monitor()
    if option is auto_consent and value is not True:
        _auto_ground = None
    _auto_next = 0.0  # a committed setting change warrants an immediate reconciliation


def queue_auto_edit(option, value):
    global _auto_edit_at
    value = normalize(option, value)
    if value == _auto_edits.get(option.identifier, option.value):
        return
    _auto_edits[option.identifier] = value
    _auto_edit_at = time.monotonic()


def flush_auto_edits(force=False):
    global _auto_blocked, _auto_next
    if not _auto_edits or (not force and time.monotonic() - _auto_edit_at < .25):
        return
    edits = dict(_auto_edits)
    _auto_edits.clear()
    try:
        apply(edits)
        _auto_next = 0.0
    except Exception as exc:
        _auto_blocked = 'Settings save failed; toggle master to retry'
        report_live('HOLD: ' + str(exc)[:120])


def pause_auto(reason):
    global _auto_blocked, _auto_ground
    _auto_ground = None
    _auto_edits.clear()
    if auto_master.value is True or _auto_owned:
        _auto_blocked = reason
        try:
            apply({auto_master.identifier: False})
        except Exception:
            # Do not allow a failed disk write to keep gameplay active this run.
            auto_master.value = False
            report_live('HOLD: master off in memory; settings save failed, check before restart')


def auto_desired():
    values = {o.identifier: o.value for o in PREVIEW}
    desired = {}
    for key, flag in AUTO_OPTIONS.items():
        if flag.value is not True:
            continue
        if key in _auto_edits:
            record = _controller.records.get(key) if _auto_owned and _controller is not None else None
            if record is not None:
                desired[key] = record['selection']
        elif values[key] != 1.0:
            desired[key] = values[key]
    return desired


def report_auto_status_change():
    # Record only changed blocking states; no per-frame report writes.
    global _auto_last_diagnostic
    status = _auto_blocked or _auto_status
    diagnostic = status if (_auto_blocked or status.startswith(('HOLD:', 'Waiting', 'Paused;'))) else ''
    if diagnostic != _auto_last_diagnostic:
        _auto_last_diagnostic = diagnostic
        if diagnostic:
            report_live('Persistent status: ' + diagnostic)


def auto_tick():
    """Camera callback only. Reconcile saved desired settings in owner-confirmed offline solo mode (R2 admission).
    No implicit legacy migration, no retry after unexpected drift or failed write.
    """
    global _controller, _auto_owned, _auto_blocked, _auto_ground, _auto_next, _auto_api, _auto_status
    now = time.monotonic()
    if _activation_request is not None:
        cancel_activation('persistent mode selected')
    if _controller is not None and (_controller.busy or _controller.fault):
        return
    if not (_controller is not None and _controller.records) and _auto_ground is None and now < _auto_next:
        return  # idle only: no owned values or queued animation to protect
    if not _auto_owned and _controller is not None and _controller.records:
        # Never adopt active manual baselines into a new automatic session.
        _controller.restore_all('switching to persistent mode')
        return
    try:
        permitted = auto_allowed() and not conflicting_mods()
        if not permitted:
            _auto_status = ('HOLD: disable overlapping tuning mods' if auto_allowed() else
                            'Paused; enable master and saved offline preference')
        hooks = sys.modules['unrealsdk'].hooks
        monitor_ok = _monitor_registered and hooks.has_hook(_MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL, _MONITOR_ID) is True
        if permitted and not monitor_ok:
            _auto_status = 'HOLD: verified camera monitor unavailable'
        permitted = permitted and monitor_ok
    except Exception:
        permitted = False
        _auto_status = 'HOLD: persistent preflight unavailable'
    if not permitted:
        _auto_next = now + .25
        _auto_ground = None
        if _auto_owned and _controller is not None and _controller.records:
            _controller.restore_all('persistent permission removed')
        if not (_controller is not None and _controller.records):
            _auto_owned = False
            _auto_api = None
        return
    # Retain full per-camera active guard; share only fresh read-only context within it.
    observed = None
    if _auto_owned and _controller is not None and _controller.records:
        if 'walk_speed' in _controller.records and now - _ground_seen > 2.0:
            _controller.restore_all('local animation callback stale')
            _auto_blocked = 'Animation stale; toggle master to retry'
            return
        try:
            observed = _controller.context()
        except Exception:
            observed = None
        if observed is None or not observed[3]:
            _auto_status = 'Waiting for eligible local solo session (R2 checks)'
            _auto_ground = None
            _controller.restore_all('persistent session no longer eligible')
            if _controller.fault:
                _auto_blocked = 'Restoration fault; exit game'
            else:
                _auto_owned = False
            return
        before = set(_controller.records)
        _controller.tick(True, observed=observed)
        if set(_controller.records) != before or _controller.fault:
            _auto_ground = None
            _auto_blocked = 'Unexpected active field change; toggle master to retry'
            return
    if now < _auto_next:
        return
    _auto_next = now + .25
    desired = auto_desired()
    if not desired and not (_controller is not None and _controller.records):
        _auto_ground = None
        _auto_owned = False
        _auto_status = ('Waiting for slider edit to save' if _auto_edits else
                        'Ready; enable a feature and select a non-1x value')
        return
    try:
        if not _auto_owned:
            if _auto_api is None:
                _auto_api = bound_session(sys.modules['unrealsdk'])
            api = _auto_api
            context = lambda: current_session(api)
            observed = context()
            if not observed[3]:
                _auto_status = 'Waiting for eligible local solo session (R2 checks); verify Offline Local Only'
                return
            _controller = Controller(context, sys.modules['unrealsdk'].unreal.WeakPointer, report_live, threading.get_ident)
            _auto_owned = True
        else:
            observed = _controller.context() if observed is None else observed
            if not observed[3]:
                _auto_status = 'Waiting for eligible local solo session (R2 checks)'
                _auto_ground = None
                _auto_owned = False
                return
    except Exception:
        _auto_status = 'Waiting for loaded solo character or compatible SDK reflection'
        _auto_next = now + 1.0  # loading screen or missing reflection: bounded retry, no writes
        return
    if _controller.stop_pending is not None:
        _controller.restore_all('persistent stop pending')
        _auto_ground = None
        _auto_blocked = 'Stopped; toggle master to retry'
        return
    _auto_status = 'Eligible solo session; reconciling saved feature settings'
    for key in tuple(_controller.records):
        if key not in desired:
            if not _controller.restore_selected(key, 'persistent feature disabled'):
                _auto_blocked = 'Restore failed; exit game'
                return
    if _auto_ground is not None:
        if desired.get('walk_speed') != _auto_ground[0]:
            _auto_ground = None
        elif now >= _auto_ground[1]:
            _auto_ground = None
            _auto_blocked = 'Animation activation expired; toggle master to retry'
            _controller.restore_all('persistent animation activation expired')
            return
    for key, selection in desired.items():
        if _controller.records.get(key, {}).get('selection') == selection:
            continue
        if key == 'walk_speed':
            if _auto_ground is None:
                if not ensure_ground_hook():
                    _auto_blocked = 'Animation hook unavailable; toggle master to retry'
                    _controller.restore_all('persistent animation hook unavailable')
                    return
                _auto_ground = (selection, now + 3.0, tuple(identity(x) for x in observed[:3]))
            continue
        if not _controller.activate(key, selection):
            _auto_ground = None
            _auto_blocked = 'Activation failed: ' + key + '; toggle master to retry'
            return
        break  # at most one non-animation activation per reconciliation interval

def enabled():
    if auto_master.value is True and auto_consent.value is True:
        ensure_monitor()
    print('[BL4 Custom] v0.7.7-experimental enabled; F8 opens menu. Persistent gameplay requires explicit opt-in.')


def disabled():
    request_stop('mod disabled', immediate=False)
    close_menu()
    print('[BL4 Custom] Disabled.')


open_key = keybind('open_custom_menu', 'F8', lambda: toggle_menu(), display_name='Open Custom Menu',
                   description='Open or close the graphical preview. Rebind in SDK console.', is_rebindable=True)
# The probe remains at top level to preserve the existing v0.1.1 JSON key.
options = [ButtonOption('open_menu', display_name='Open Graphical Menu', on_press=toggle_menu),
           ButtonOption('inspect_rewards', display_name='Inspect Reward Members (Read Only)', on_press=inspect_reward_members),
           ButtonOption('inspect_attribute_api', display_name='Attribute Compatibility Report (Read Only)', on_press=inspect_attribute_compatibility), probe]
options += [NestedOption('persistent', AUTO_SETTINGS, display_name='Persistent gameplay (experimental)')]
options += [NestedOption(key, items, display_name=name, description=DESCRIPTION)
            for key, name, items in CATEGORIES if key != 'menu']
options += [NestedOption('menu', [ButtonOption('open_from_menu', display_name='Open Graphical Menu', on_press=toggle_menu)], display_name='Custom Menu'),
            ButtonOption('reset_preview', display_name='Restore Vanilla Defaults', on_press=reset)]
mod = build_mod(options=options, hooks=[], commands=[], keybinds=[open_key], auto_enable=True,
                on_enable=enabled, on_disable=disabled)
