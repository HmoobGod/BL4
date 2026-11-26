"""Community integration: explicit solo session controls, progression HOLD."""
import math
import sys
import threading
import time
from pathlib import Path
from mods_base import BoolOption, ButtonOption, NestedOption, SliderOption, build_mod, keybind
from .gameplay_fields import FEATURES, RARITY_KEYS
from .session_control import Controller, DAMAGE_HOLD, GROUND_KEYS
from .ground_speed import is_player_animation, sprinting
from .gameplay_fields import identity, target_values, lifesteal_peer_context
from .inventory_capacity import KEYS as CAPACITY_KEYS, resolve as resolve_capacity, validate as validate_capacity
from .weapon_rates import WEAPON_KEYS, AMMO_KEYS, validate_targets
from .shield_rates import KEYS as SHIELD_KEYS, validate_readback as validate_shield_readback
from .gadget_rates import KEY as GADGET_KEY
NEW_MOVE_KEYS = frozenset(('ladder_ascend', 'ladder_descend', 'slam_height', 'ground_friction', 'braking_friction', 'slide_speed'))

TITLE = 'BL4 Custom - Community Integration v0.7.61-experimental'
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
    ('combat', 'Combat', [SliderOption('damage', 1., .5, 5., step=.1, is_integer=False, display_name='Damage multiplier', description='Experimental equipped ordinary gun damage; 1x restores. Not a global damage multiplier.'), SliderOption('fire_rate', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['fire_rate'][0], description='Experimental native weapon rate; persistent mode follows supported idle weapons.'), SliderOption('reload', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['reload'][0], description='Experimental stock reload duration; persistent mode follows supported idle weapons. 1x restores.'), SliderOption('swap_time', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['swap_time'][0], description='Local native time scale candidate; manual or persistent opt-in; direction of gameplay effect unverified. 1x restores.'), *[SliderOption(k, 1., .1, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Experimental weapon field; persistent mode follows supported idle weapons. Lower scales the field down. Native effect unverified. 1x restores.') for k in ('weapon_spread', 'weapon_recoil')], slider('fire_damage', 'Fire damage multiplier'),
        slider('damage_taken', 'Damage taken multiplier', minimum=0.1), slider('shock_damage', 'Shock damage multiplier'),
        slider('corrosive_damage', 'Corrosive damage multiplier'), slider('cryo_damage', 'Cryo damage multiplier'),
        slider('radiation_damage', 'Radiation damage multiplier')]),
    ('progression', 'XP and Progression', [progression_slider('progress_character_xp', 'Character XP'),
        progression_slider('progress_specialization_xp', 'Specialization XP'),
        progression_slider('progress_money', 'Money'),
        progression_slider('progress_eridium', 'Eridium'),
        progression_slider('progress_enemy_xp', 'Enemy kill XP'),
        progression_slider('progress_mission_xp', 'Mission XP')]),
    ('loot', 'Loot and Drop Rates', [slider('drops', 'Drop rate multiplier'), progression_slider('overall_loot_luck', 'Overall loot luck'), rarity_slider('common_weight', 'Common rarity weight'), rarity_slider('uncommon_weight', 'Uncommon rarity weight'), rarity_slider('rare_weight', 'Rare rarity weight'), rarity_slider('epic_weight', 'Epic rarity weight'), rarity_slider('legendary_weight', 'Legendary rarity weight (selected)'), rarity_slider('pearlescent_weight', 'Pearlescent rarity weight')]),
    ('inventory', 'Inventory', [SliderOption(k, 1., 1., 1000., step=1, is_integer=True, display_name=FEATURES[k][0], description='Experimental absolute slots; 1 restores captured original. Never fill above original capacity during testing.') for k in ('backpack_capacity','bank_capacity')]),
    ('movement', 'Movement', [SliderOption('sprint', 1., 1., 3., step=.1, is_integer=False, display_name='Sprint-only speed floor (reference multiplier)', description='Experimental manual mode; walking stays at original floor. Restore combined ground speed first. 1x restores.'), slider('jump', 'Jump velocity multiplier'), *[SliderOption(k, 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Local movement attribute; manual or persistent opt-in; 1x restores. Actual speed/distance unverified.') for k in ('dash_speed', 'glide_speed', 'glide_air_control', 'glide_boost', 'glide_acceleration', 'glide_deceleration')], *[SliderOption(k, 1., .1, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Existing positive vault-power cost; lower may reduce consumption. 1x restores. No free energy or new jump actions.') for k in ('double_jump_cost','dash_cost','glide_cost','grapple_cost','slam_cost')], *[SliderOption(k, 1., FEATURES[k][1], FEATURES[k][2], step=.1, is_integer=False, display_name=FEATURES[k][0], description=('Only while exact native slide is active; persistent mode recommended. 1x restores.' if k=='slide_speed' else 'Local movement field only; native effect unverified. 1x restores.')) for k in ('ladder_ascend','ladder_descend','slam_height','ground_friction','braking_friction','slide_speed')], SliderOption('gravity', 1., .5, 1.5, step=.1, is_integer=False, display_name='Local gravity multiplier', description='Experimental local movement only; lower gravity can increase airborne time. 1x restores.'), SliderOption('walk_speed', 1., 1., 3., step=.1, is_integer=False, display_name='Ground speed floor (reference multiplier)', description='1x restores; higher raises walk/sprint floor. Actual speed varies.')]),
    ('automation', 'Automation', [toggle('auto_reload', 'Automatic reload'), toggle('auto_loot', 'Automatic loot pickup')]),
    ('quality', 'Quality of Life', [toggle('auto_ammo', 'Automatic ammo pickup'), slider('cooldown', 'Cooldown multiplier'), slider('repair_cooldown', 'Repair-kit cooldown duration multiplier', minimum=0.1), slider('healing_received', 'Healing received multiplier'), slider('repair_duration', 'Repair-kit healing duration multiplier'), slider('repair_health', 'Repair-kit healing amount multiplier'), SliderOption('overshield_duration', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['overshield_duration'][0], description='Existing positive overshield duration only; manual activation; does not grant shields. 1x restores.'), SliderOption('lifesteal_fraction', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['lifesteal_fraction'][0], description='Existing positive normalized life-steal only; manual or persistent opt-in. 1x restores. Restore other life-steal control first.'), *[SliderOption(k, 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Experimental: existing positive native rate only; 1x restores. Weapon ammo, grenade and shield controls support persistent opt-in; player ammo regeneration and existing positive life-steal support persistent opt-in.') for k in ('ammo_regen_rate', 'ammo_regen_delay', 'lifesteal_rate', 'shield_regen_rate', 'shield_regen_delay', 'grenade_cooldown', 'player_ammo_regen')]]),
    ('enemies', 'Enemy Difficulty', [slider('enemy_health', 'Enemy health multiplier'), slider('enemy_damage', 'Enemy damage multiplier')]),
    ('menu', 'Custom Menu', [probe]),
]
PREVIEW = [o for _, _, items in CATEGORIES for o in items if o is not probe]
_PREVIEW_BY_KEY = {o.identifier: o for o in PREVIEW}
_COMPACT_OPTIONS = tuple(tuple(o for o in items if o is probe or (o.identifier in FEATURES and o.identifier not in DAMAGE_HOLD)) for _, _, items in CATEGORIES)
# Explicit opt-in, separate from legacy saved preview values. Defaults stay vanilla.
auto_master = BoolOption('persistent_master', False, display_name='Persistent gameplay (experimental)')
auto_consent = BoolOption('persistent_offline', False, display_name='I use Offline Local Only; tuning mods disabled')
MANUAL_ONLY = frozenset(('sprint', 'overshield_duration'))
LIFE_KEYS = frozenset(('lifesteal_rate', 'lifesteal_fraction'))
PLAYER_AMMO_KEY = 'player_ammo_regen'
AMMO_GROUP = AMMO_KEYS | {PLAYER_AMMO_KEY}
AUTO_OPTIONS = {k: BoolOption('persistent_' + k, False, display_name='Auto-enable ' + FEATURES[k][0])
                for k in FEATURES if k not in DAMAGE_HOLD and k not in MANUAL_ONLY}
AUTOMATION_OPTIONS = {k: BoolOption('persistent_automation_'+k, False, display_name='Auto-enable '+label)
                      for k,label in (('vacuum','continuous Loot Vacuum'),('reload','session automatic reload'),('health','continuous flesh recovery assist'),('shield','continuous shield recharge assist'),('skill_cooldown','continuous action skill cooldown assist'),('skill_duration','continuous action skill duration assist'),('double_jump','second-jump upward velocity (experimental)'))}
DOUBLE_JUMP_RATE = SliderOption('double_jump_velocity_scale', 1., .5, 2., step=.1, is_integer=False, display_name='Double-jump upward velocity multiplier (experimental)')
AUTO_SETTINGS = [auto_master, auto_consent, *AUTO_OPTIONS.values(), *AUTOMATION_OPTIONS.values(), DOUBLE_JUMP_RATE]
# Independent persistent lanes. Isolated manual experiments remain unchanged.
_automation_leases = {}
_automation_attempted = set()
_automation_status = {}
_automation_next = 0.0
_automation_busy = False
_JUMP_EVENT_PATH = '/Script/Engine.Character:OnJumped'
_JUMP_EVENT_ID = 'bl4_custom_second_jump_event_v0751exp'
_jump_event_attempted = False
_jump_event_owned = False
_AUTOMATION_COMPATIBLE = frozenset(('walk_speed','jump','gravity','damage_taken','healing_received','repair_cooldown','repair_duration','dash_speed','glide_speed','fire_damage','shock_damage','corrosive_damage','cryo_damage','radiation_damage','double_jump_cost','dash_cost','glide_cost','swap_time','repair_health','fire_rate','weapon_spread','weapon_recoil','reload','ammo_regen_rate','ammo_regen_delay', 'glide_air_control', 'glide_boost', 'glide_acceleration', 'glide_deceleration', 'grapple_cost', 'slam_cost')) | CAPACITY_KEYS | SHIELD_KEYS | NEW_MOVE_KEYS | {GADGET_KEY, PLAYER_AMMO_KEY} | RARITY_KEYS | LIFE_KEYS | {'damage'}
_ground_selection = next(o for o in PREVIEW if o.identifier == 'walk_speed')
VACUUM_PREFS = {k: BoolOption('vacuum_pref_'+k, False, display_name='Saved vacuum '+k) for k in ('ammo','cash','eridium','health','gear')}
VACUUM_HIGH_PREF = BoolOption('vacuum_pref_high_gear', False, display_name='Saved vacuum legendary/pearlescent beams only')
VACUUM_RADIUS_PREF = SliderOption('vacuum_pref_radius', 30., 5., 100., step=1., is_integer=False, display_name='Saved vacuum radius (m)')
RECOVERY_RATES = {k: SliderOption('recovery_rate_'+k, 1., .1, 1., step=.1, is_integer=False, display_name=k.title()+' recovery (% maximum per pulse)') for k in ('health','shield')}
SKILL_ADAPTIVE = {k: BoolOption('adaptive_'+k,False,display_name='Adaptive '+k.replace('_',' ')+' assist (native percent cross-check)') for k in ('skill_cooldown','skill_duration')}
SKILL_NATIVE = {k: BoolOption('native_refill_'+k,False,display_name='Dedicated native refill for '+k.replace('_',' ')+' (experimental)') for k in SKILL_ADAPTIVE}
CROSSFIRE_GATE = BoolOption('crossfire_duration_events',False,display_name='Cross-Fire duration: require local start/end events (experimental)')
_crossfire_hooks = None
_crossfire_attempted = False
SKILL_FOLLOW = {k: BoolOption('follow_'+k,False,display_name='Follow distinct replacement '+k.replace('_',' ')+' (experimental)') for k in SKILL_ADAPTIVE}
SKILL_RATES = {k: SliderOption('adaptive_rate_'+k,1.,1.,3.,step=.1,is_integer=False,display_name='Adaptive '+k.replace('_',' ')+' target') for k in SKILL_ADAPTIVE}
ALL = PREVIEW + [probe] + AUTO_SETTINGS + list(VACUUM_PREFS.values()) + [VACUUM_RADIUS_PREF, VACUUM_HIGH_PREF] + list(RECOVERY_RATES.values()) + list(SKILL_ADAPTIVE.values()) + list(SKILL_RATES.values()) + list(SKILL_FOLLOW.values()) + list(SKILL_NATIVE.values()) + [CROSSFIRE_GATE]
_auto_owned = False
_auto_blocked = ''
_auto_status = 'Not active; opt in to persistent gameplay.'
_auto_ground = None
_auto_api = None
_auto_next = 0.0
_slide_next = 0.0
_auto_edits = {}
_auto_edit_at = 0.0
_auto_last_diagnostic = ''

_vacuum_filters = {k: False for k in ('ammo','cash','eridium','health','gear')}
_vacuum_radius = 30.0
_vacuum_high_gear = False


def save_vacuum_preferences():
    apply({**{o.identifier: _vacuum_filters[k] for k,o in VACUUM_PREFS.items()}, VACUUM_RADIUS_PREF.identifier: _vacuum_radius, VACUUM_HIGH_PREF.identifier: _vacuum_high_gear})


def load_vacuum_preferences():
    global _vacuum_radius, _vacuum_high_gear
    for k,o in VACUUM_PREFS.items(): _vacuum_filters[k] = normalize(o,o.value)
    _vacuum_radius = normalize(VACUUM_RADIUS_PREF,VACUUM_RADIUS_PREF.value)
    _vacuum_high_gear = VACUUM_HIGH_PREF.value is True


_pending = {}
_category = 0
_status = 'No unapplied changes.'
_backend = None
_reward_summary = "Not checked. Read-only checks are available on demand."
_menu_close_ready = False
_compact_view = None  # default compact in persistent mode, full in manual mode
_focus_controls = False  # runtime-only opt-in; no change to saved gameplay options
_focus_pages = {}
_action_panels = {}  # runtime-only, independent of feature-row page
_FOCUS_PAGE_SIZE = 6


def focused_options(ui, category, compact, options):
    """Limit only category feature rows; global safety and action controls stay visible."""
    if not _focus_controls or len(options) <= _FOCUS_PAGE_SIZE:
        return options
    pages = (len(options) + _FOCUS_PAGE_SIZE - 1) // _FOCUS_PAGE_SIZE
    key = (category, compact)
    page = max(0, min(pages - 1, _focus_pages.get(key, 0)))
    if page > 0 and ui.button('Previous controls##focus_prev'):
        page -= 1
    if page < pages - 1 and ui.button('Next controls##focus_next'):
        page += 1
    _focus_pages[key] = page
    ui.text(f'Feature controls: page {page + 1} of {pages}')
    start = page * _FOCUS_PAGE_SIZE
    return options[start:start + _FOCUS_PAGE_SIZE]



def visible_action_panels(ui, category, labels):
    """When reduced rows are selected, render just one action group.

    Navigation changes only presentation; gameplay checks and global stop controls
    remain in draw/monitor_tick. Full view preserves the original layout.
    """
    if not _focus_controls:
        return frozenset(labels)
    chosen = _action_panels.get(category, labels[0])
    if chosen not in labels:
        chosen = labels[0]
    for name in labels:
        if ui.button(name + (' *' if chosen == name else '') + '##action_panel_' + str(category) + '_' + name):
            chosen = name
    _action_panels[category] = chosen
    return frozenset((chosen,))


def normalize(option, value):
    if isinstance(option, BoolOption):
        return value if type(value) is bool else option.default_value
    if type(value) not in (int, float) or not math.isfinite(value):
        return option.default_value
    bounded = max(option.min_value, min(option.max_value, value))
    return round(bounded) if option.identifier in CAPACITY_KEYS else round(bounded, 1)


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
    global _status, _vacuum_radius, _vacuum_high_gear
    for key in _vacuum_filters: _vacuum_filters[key] = False
    _vacuum_radius = 30.0
    _vacuum_high_gear = False
    pause_auto("vanilla reset requested")
    cancel_activation("vanilla reset requested")
    stop_health_pulse('vanilla reset requested')
    if health_fault():
        _status = 'Recovery fault latched; exit game immediately.'
        return
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
    if key in AMMO_GROUP and ammo_selection_conflict(raw_auto_desired(AMMO_GROUP)):
        return 'HOLD: choose player OR weapon ammo regeneration'
    if key in LIFE_KEYS and LIFE_KEYS <= set(raw_auto_desired(LIFE_KEYS)):
        return 'HOLD: choose life-steal rate OR percentage'
    if key in _auto_edits:
        return 'Saving selection...'
    selected = _PREVIEW_BY_KEY[key].value
    record = _controller.records.get(key) if _auto_owned and _controller is not None else None
    if selected == 1.0:
        return 'Restoring' if record else 'Vanilla capacity' if key in CAPACITY_KEYS else '1x / vanilla'
    if record is not None and record.get('selection') == selected:
        return 'Active: ' + str(selected) + (' slots' if key in CAPACITY_KEYS else 'x') + ' (value verified)'
    if key in LIFE_KEYS:
        return 'Waiting for supported positive life-steal effect'
    return 'Waiting for exact active slide' if key == 'slide_speed' else 'Waiting for gameplay callback'


def displayed_selection(option):
    key = option.identifier
    if key in _auto_edits:
        return _auto_edits[key]
    if key in _pending:
        return _pending[key]
    return normalize(option, option.value)


def draw():
    global _category, _status, _compact_view, _vacuum_radius, _focus_controls, _vacuum_high_gear
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
    ui.text('BL4 CUSTOM | v0.7.61-experimental')
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
    edited_focus, focus_value = ui.checkbox('Reduced feature rows (6 per page)', _focus_controls)
    if edited_focus:
        _focus_controls = bool(focus_value)
    if not compact or _loot_test_status.startswith(('HOLD', 'FAULT', 'STOP')):
        ui.text_wrapped(_loot_test_status)
    ui.text("Session monitor: " + monitor_status())
    if health_fault() or automation_fault() or (_controller is not None and _controller.fault):
        ui.text_wrapped('FAULT LATCHED: exit game immediately; do not play.')
    if _controller is not None:
        ui.text_wrapped('Active fields (gameplay unverified): ' + (', '.join(k + ' ' + str(r.get('selection', '?')) + (' slots' if k in CAPACITY_KEYS else 'x') for k, r in _controller.records.items()) or 'None / vanilla'))
        if any(r.get('overfull_warning') for r in _controller.records.values()):
            ui.text_wrapped('CAPACITY RESTORE HOLD: remove excess items in this offline session, then restore. Do not travel, buy SDUs or exit while over capacity.')
        if _controller.records and not _controller.fault and ui.button('Restore ALL active gameplay values'):
            pause_auto('F8 restore all')
            request_stop('F8 restore all', immediate=True)
    if any(l.record is not None for l in _automation_leases.values()):
        ui.text_wrapped('Persistent automation armed (native outcomes unverified).')
        if ui.button('Stop automation / Restore ALL'):
            pause_auto('F8 restore all')
            request_stop('F8 restore all', immediate=True)
    if _native_overtime_used:
        ui.text_wrapped('Native timed flesh test attempted: stay offline, do not travel, and exit game after the test.')
    if health_active():
        ui.text_wrapped('Native rate trial active or restoring; wait for verified baseline before changing character, skill or session.' if hasattr(_health_pulse,'binding') and hasattr(_health_pulse,'phase') else ('Continuous vacuum active until stopped in this session. Completed relocations are not reversed.' if getattr(_health_pulse,'continuous',False) and hasattr(_health_pulse,'categories') else 'Experimental action armed; maximum 30 seconds. Completed native actions are not reversed.'))
        if ui.button('Stop experimental action / Restore ALL'):
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
        options = _COMPACT_OPTIONS[_category]
        if not options:
            ui.text('No supported gameplay controls here; turn off Compact menu to view previews.')
    if _category == 0 and not compact:
        ui.text_wrapped('Damage applies to the equipped ordinary gun fire behavior only. Elemental and incoming modifiers are separate; actual hit effects unverified.')
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
    if _category == 4 and auto_master.value is True:
        option = AUTOMATION_OPTIONS['double_jump']
        edited, selected = ui.checkbox(option.display_name+'##'+option.identifier, option.value is True)
        if edited: set_auto_setting(option,selected)
        edited, selected = ui.slider_float(DOUBLE_JUMP_RATE.display_name+'##'+DOUBLE_JUMP_RATE.identifier,float(displayed_selection(DOUBLE_JUMP_RATE)),.5,2.,'%.1fx')
        if edited: queue_auto_edit(DOUBLE_JUMP_RATE,selected)
        ui.text('double_jump: '+_automation_status.get('double_jump','Waiting / off'))
        ui.text_wrapped('Experimental second-jump velocity only; actual height unverified. Land before use; toggle lane to rearm after changing scale. First jump and shared goals unchanged.')
    if _category == 5:
        panels = visible_action_panels(ui, 5, ('Loot Vacuum', 'Automatic reload'))
        if auto_master.value is True:
            ui.text_wrapped('Persistent automation: movement, elemental, rarity weights and selected recovery fields compatible. Save vacuum changes to update the active lease. Reload waits for a supported loaded idle gun and reserve, including after weapon/mode swaps. Empty guns need a normal reload first; unsupported guns stop the lane. Toggle a stopped lane off/on to rearm.')
            for kind, option in AUTOMATION_OPTIONS.items():
                if kind not in ('vacuum','reload') or ('Loot Vacuum' if kind == 'vacuum' else 'Automatic reload') not in panels: continue
                edited, selected = ui.checkbox(option.display_name+'##'+option.identifier, option.value is True)
                if edited: set_auto_setting(option, selected)
                ui.text(kind+': '+_automation_status.get(kind, 'Waiting / off'))
        if 'Loot Vacuum' in panels:
            ui.text_wrapped('Experimental Loot Vacuum: select categories, then arm a short test or continuous session. Gear moves into separate nearby positions for manual pickup; full placement area pauses gear only. Completed moves are not reversed.')
            if not health_active():
                for kind in _vacuum_filters:
                    edited, selected = ui.checkbox('Vacuum '+kind+'##vacuum_'+kind, _vacuum_filters[kind])
                    if edited:
                        _vacuum_filters[kind] = selected is True
                edited, selected = ui.checkbox('Gear: legendary/pearlescent beams only##vacuum_high_gear', _vacuum_high_gear)
                if edited: _vacuum_high_gear = selected is True
                edited, radius = ui.slider_float('Pickup radius##vacuum_radius', _vacuum_radius, 5., 100., '%.0f m')
                if edited and type(radius) in (int,float) and math.isfinite(radius):
                    _vacuum_radius = max(5., min(100., radius))
                if ui.button('Save vacuum preferences'):
                    try:
                        save_vacuum_preferences(); _status = 'Vacuum preferences saved; active persistent vacuum updates on gameplay callback.'
                    except Exception:
                        _status = 'Vacuum preferences save failed.'
                if ui.button('Load saved vacuum preferences'):
                    load_vacuum_preferences()
                if not health_fault() and auto_master.value is not True and ui.button('Start continuous Loot Vacuum (session only)'):
                    activate_feature('loot_vacuum_continuous', (tuple(k for k,v in _vacuum_filters.items() if v), _vacuum_radius) + ((True,) if _vacuum_high_gear else ()))
                if not health_fault() and auto_master.value is not True and ui.button('Arm experimental Loot Vacuum (30 sec)'):
                    activate_feature('loot_vacuum', (tuple(k for k,v in _vacuum_filters.items() if v), _vacuum_radius) + ((True,) if _vacuum_high_gear else ()))
        if 'Automatic reload' in panels:
            ui.text_wrapped('Experimental automatic reload: one ordinary native reload request after observed magazine depletion, within 30 seconds.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Arm experimental automatic reload (30 sec)'):
                activate_feature('reload_assist', 1.0)
            ui.text_wrapped('Continuous experiment: repeat only after observed Reloading and two positive idle samples; 30 sec, max 10 requests. Native completion compatibility unverified.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Arm continuous experimental reload (30 sec)'):
                activate_feature('reload_continuous', 1.0)
    if _category == 6:
        panels = visible_action_panels(ui, 6, ('Recovery', 'Action skills'))
        if auto_master.value is True:
            ui.text_wrapped('Continuous recovery assists: native refill pulses, not native regen-rate or recharge-delay modifiers. Stop on lost scope or ineffective refill; toggle to rearm. Already recovered health is not reversed.')
            for kind in ('health','shield','skill_cooldown','skill_duration'):
                if ('Recovery' if kind in ('health','shield') else 'Action skills') not in panels: continue
                option = AUTOMATION_OPTIONS[kind]
                edited, selected = ui.checkbox(option.display_name+'##'+option.identifier, option.value is True)
                if edited: set_auto_setting(option, selected)
                ui.text(kind+': '+_automation_status.get(kind, 'Waiting / off'))
                if kind in RECOVERY_RATES:
                    rate=RECOVERY_RATES[kind]
                    edited, selected=ui.slider_float(rate.display_name+'##'+rate.identifier, float(displayed_selection(rate)), .1,1.,'%.1f%%')
                    if edited: queue_auto_edit(rate, selected)
                if kind in SKILL_ADAPTIVE:
                    adaptive=SKILL_ADAPTIVE[kind]
                    edited,selected=ui.checkbox(adaptive.display_name+'##'+adaptive.identifier,adaptive.value is True)
                    if edited:set_auto_setting(adaptive,selected)
                    rate=SKILL_RATES[kind]
                    edited,selected=ui.slider_float(rate.display_name+'##'+rate.identifier,float(displayed_selection(rate)),1.,3.,'%.1fx')
                    if edited:queue_auto_edit(rate,selected)
                    native=SKILL_NATIVE[kind]
                    edited,selected=ui.checkbox(native.display_name+'##'+native.identifier,native.value is True)
                    if edited:set_auto_setting(native,selected)
                    if kind=='skill_duration':
                        edited,selected=ui.checkbox(CROSSFIRE_GATE.display_name+'##'+CROSSFIRE_GATE.identifier,CROSSFIRE_GATE.value is True)
                        if edited:set_auto_setting(CROSSFIRE_GATE,selected)
                    follow=SKILL_FOLLOW[kind]
                    edited,selected=ui.checkbox(follow.display_name+'##'+follow.identifier,follow.value is True)
                    if edited:set_auto_setting(follow,selected)
            if 'Action skills' in panels:
                ui.text_wrapped('Dedicated native refill requires adaptive mode, caps each addition at 1%, and checks readback. Supported named main cooldowns with charge/auxiliary pools use a separate pawn resource API; charge and auxiliary pools are not targeted. Rearm on mode changes. Native effect unverified.')
            if 'Action skills' in panels:
                ui.text_wrapped('Cross-Fire event gate: dedicated adaptive duration only; follow OFF; wait for a new activation after arming. Other skills are not admitted in this mode.')
                ui.text_wrapped('Follow skill is optional: requires two fresh observations of a distinct supported replacement; changing follow mode requires lane rearm.')
            ui.text_wrapped('Player and weapon ammo regeneration cannot overlap. If both are selected, all ammo regeneration modifiers restore until you choose one.')
            if 'Action skills' in panels:
                ui.text_wrapped('Adaptive skill mode uses observed native pool change, capped at 3% per eligible sample; 1x adds nothing. Mode change requires toggling lane to rearm. Not an exact native multiplier.')
            if 'Recovery' in panels:
                ui.text_wrapped('Native shield modifiers take priority over the shield pulse assist; flesh recovery remains independent. Restore before changing equipment if possible.')
            if 'Action skills' in panels:
                ui.text_wrapped('Skill assists: unique ordinary skills, plus supported named primary cooldowns in dedicated adaptive mode. Charge and auxiliary pools are not modified. Not exact cooldown/duration multipliers.')
        if 'Recovery' in panels:
            ui.text_wrapped('Experimental health recovery: native flesh-only refill pulse, 30-second maximum, not a native regen-rate modifier. No FFYL. Actual game compatibility unverified.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Start experimental health recovery (30 sec)'):
                activate_feature('health_pulse', 1.0)
            ui.text_wrapped('Native timed flesh experiment: one small engine-timed refill per game process. Timer cancellation/expiry unverified; stay offline, do not travel, and exit game after this test.')
            if not _native_overtime_used and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native timed flesh recovery (2 sec)'):
                activate_feature('health_overtime', 1.0)
            ui.text_wrapped('Native regeneration start/stop test: uses a distinct constant-rate initializer and existing flesh tags. Rate units and stop/expiry are unverified; share one timed attempt per process. Exit after testing.')
            if not _native_overtime_used and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native regeneration start/stop (2 sec)'):
                activate_feature('health_regen_native', 1.0)
            ui.text_wrapped('Native passive regeneration rate trial: small additive native rate, not a refill. Ten-second maximum; restore before travel. Rate units and actual healing unverified.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native passive health rate (10 sec)'):
                activate_feature('native_rate_health', 1.0)
            ui.text_wrapped('Experimental energy shield assist: adds a small pulse only after two rising charge samples; not a native recharge delay/rate multiplier.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Start experimental shield assist (30 sec)'):
                activate_feature('shield_pulse', 1.0)
        if 'Action skills' in panels:
            ui.text_wrapped('Action skill assist: experimental bounded native refill, not a multiplier; excludes charge and auxiliary skills.')
            ui.text_wrapped('Native resource-rate trials: 2x cooldown regeneration or half duration consumption, one at a time. Exact runtime property path and reversible readback required; no refill. Restore before skill changes.')
            for mode in ('cooldown','duration'):
                if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native skill '+mode+' rate (10 sec)'):
                    activate_feature('native_rate_'+mode, 1.0)
                if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Start experimental skill '+mode+' assist (30 sec)'):
                    activate_feature('skill_'+mode, 1.0)
    if _category == 8:
        ui.text_wrapped('Change the Open Custom Menu key in the SDK console Keybinds section. Default: F8.')
        ui.text('Current hotkey: ' + str(open_key.key or 'Unbound'))
    options = focused_options(ui, _category, compact, options)
    for o in options:
        value = displayed_selection(o)
        label = o.display_name + '##' + o.identifier
        if (o.identifier not in FEATURES or o.identifier in DAMAGE_HOLD) and o is not probe:
            ui.text_wrapped(o.display_name + ' — HOLD / preview only')
        if isinstance(o, BoolOption):
            edited, value = ui.checkbox(label, value)
        else:
            edited, value = ui.slider_float(label, float(value), o.min_value, o.max_value, '%.0f slots' if o.identifier in CAPACITY_KEYS else '%.1fx')
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
        if key == 'damage':
            ui.text_wrapped('Experimental equipped gun damage, not skill/melee/global damage. Apply while idle; 1x restores. Actual hit effects unverified.')
        if key in ('fire_damage', 'shock_damage', 'corrosive_damage', 'cryo_damage', 'radiation_damage'):
            ui.text_wrapped('Experimental elemental modifier; actual hit damage unverified. 1x restores.')
        if key == 'gravity':
            ui.text_wrapped('EXPERIMENTAL: lower gravity can increase jump height and airborne time. Not a direct jump-height multiplier. Test on a backup character; restore while grounded.')
        if key == 'sprint':
            ui.text_wrapped('Experimental sprint-only floor. Restore combined ground speed first. Manual activation only; not an exact speed multiplier.')
            if auto_master.value is True:
                ui.text('Disable persistent master to use sprint-only mode.')
                continue
        if key in CAPACITY_KEYS:
            ui.text_wrapped('EXPERIMENTAL: absolute slots, 1 restores original. Use a backup character; do not fill beyond original capacity. Restore before SDU purchase, travel or exit.')
        if key == 'overshield_duration':
            ui.text_wrapped('Existing positive duration and base required. Does not grant overshield or passively heal. Native timing unverified.')
        if key == 'lifesteal_fraction':
            ui.text_wrapped('Requires existing positive life-steal and unchanged rate/cap. Not passive healing. Restore the life-steal rate control first.')
        if key in MANUAL_ONLY - {'sprint'}:
            ui.text_wrapped('Experimental local instance control; gameplay effect unverified. 1x restores. Restore before switching gear or travel.')
            if auto_master.value is True:
                ui.text('Disable persistent master to use this manual experiment.')
                continue
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
    lines = ['BL4 Custom v0.7.61-experimental - read-only compatibility report',
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
_health_pulse = None
_native_overtime_used = False
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
    lines = ['BL4 Custom v0.7.61-experimental - read-only rarity diagnostic',
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
    # Extend the existing explicit report rather than add a control or polling hook.
    try:
        from .luck_categories import observe, report_lines
        session = bound_session(sys.modules['unrealsdk'])
        lines.extend(report_lines(observe(lambda: current_session(session))))
    except Exception as exc:
        lines.append('Player luck read HOLD: ' + type(exc).__name__ + ': ' + str(exc)[:200])
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
_MONITOR_ID = 'bl4_custom_legendary_session_guard_v0743exp'


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
            raise ValueError('v0.7.61-experimental monitor identifier already exists or cannot be checked; remove duplicate SDKMOD copies if present')
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
        _write_report(loot_report_path(), ['BL4 Custom v0.7.61-experimental - community session control',
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


def shield_binding():
    from .shield_rates import bind
    sdk = sys.modules['unrealsdk']
    return bind([f for f in sdk.find_all('Function', exact=False) if str(f.Name)=='GetShield'], loot_bound)


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


# Cache only candidate module *names*, never objects, enabled flags or permission.
# A new import/removal invalidates the name index, and replacement under the
# same name is read from sys.modules on every check.
_CONFLICT_NAMES = frozenset({'loottreadmill', 'rarityremover', 'damageandmore', 'bl4damageandmore',
             'resourcesandcooldowns', 'bl4resourcesandcooldowns', 'bl4playermovement',
             'squ1ggsboostingtools', 'apexmovement', 'apexspeed', 'autosprint', 'omnisprint', 'autoreload', 'bl4autoreload', 'biggerbackpack', 'biggerbackpackandbank', 'lootvacuum', 'lootmagnet', 'infinitecrossfire'})
_conflict_index = (None, ())


def conflicting_mods():
    global _conflict_index
    names = tuple(sys.modules)
    if names != _conflict_index[0]:
        candidates = tuple(name for name in names if '.' not in name and name.replace('_', '').casefold() in _CONFLICT_NAMES)
        _conflict_index = (names, candidates)
    for name in _conflict_index[1]:
        candidate = getattr(sys.modules.get(name), 'mod', None)
        if candidate is None or getattr(candidate, 'is_enabled', None) is not False:
            return True
    return False


def health_active():
    return _health_pulse is not None and _health_pulse.record is not None


def health_fault():
    return (_health_pulse is not None and _health_pulse.fault) or automation_fault()


def stop_health_pulse(reason):
    if _health_pulse is not None:
        _health_pulse.stop(reason)


def begin_health_pulse(mode='flesh'):
    global _health_pulse
    # Import only on explicit activation; no startup SDK discovery or writes.
    from .health_pulse import Pulse, bind, SPECS
    if health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore existing features before isolated health experiment')
    sdk = sys.modules['unrealsdk']
    functions = [f for f in sdk.find_all('Function', exact=False) if str(f.Name) in SPECS]
    api = bind(functions, loot_bound)
    session = bound_session(sdk)
    _health_pulse = Pulse(lambda: current_session(session), sdk.unreal.WeakPointer,
                         sdk.unreal.FGameDataHandle, api, time.monotonic, threading.get_ident, report_live, mode=mode)
    _health_pulse.begin()


def claim_native_overtime():
    global _native_overtime_used
    if _native_overtime_used:return False
    _native_overtime_used=True
    return True


def begin_native_overtime():
    global _health_pulse
    from .health_pulse import NativeOvertime, bind_overtime, SPECS, OVERTIME_NAME
    if _native_overtime_used or health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('native timed recovery unavailable; restore existing features or restart after prior attempt')
    sdk=sys.modules['unrealsdk']
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS or str(f.Name)==OVERTIME_NAME]
    api=bind_overtime(functions,loot_bound);session=bound_session(sdk)
    def timed_context():
        pc,pawn,state,eligible=current_session(session)
        hooks=sdk.hooks
        permitted=(mod.is_enabled is True and _offline_confirmed and auto_master.value is not True and not _auto_owned
                   and not conflicting_mods() and _monitor_registered
                   and hooks.has_hook(_MONITOR_PATH,hooks.Type.POST_UNCONDITIONAL,_MONITOR_ID) is True)
        return pc,pawn,state,eligible and permitted
    _health_pulse=NativeOvertime(timed_context,sdk.unreal.WeakPointer,sdk.unreal.FGameDataHandle,api,time.monotonic,threading.get_ident,report_live,claim_native_overtime)
    _health_pulse.begin()


def begin_native_regen():
    global _health_pulse
    from .health_pulse import NativeRegen, bind_regen, SPECS, REGEN_SPECS
    if _native_overtime_used or health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('native regeneration unavailable; restore existing features or restart after prior attempt')
    sdk=sys.modules['unrealsdk'];u=sdk.unreal
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS or str(f.Name) in REGEN_SPECS]
    api,init_type,tag_type=bind_regen(functions,loot_bound);session=bound_session(sdk)
    def cleanup_context():
        return current_session(session)
    def timed_context():
        pc,pawn,state,eligible=cleanup_context()
        hooks=sdk.hooks
        permitted=(mod.is_enabled is True and _offline_confirmed and auto_master.value is not True and not _auto_owned
                   and not conflicting_mods() and _monitor_registered
                   and hooks.has_hook(_MONITOR_PATH,hooks.Type.POST_UNCONDITIONAL,_MONITOR_ID) is True)
        return pc,pawn,state,eligible and permitted
    _health_pulse=NativeRegen(timed_context,u.WeakPointer,u.FGameDataHandle,api,time.monotonic,threading.get_ident,report_live,claim_native_overtime,sdk.make_struct,init_type,tag_type,u.FGbxDefPtr,cleanup_context)
    _health_pulse.begin()


def begin_native_resource_rate(mode):
    global _health_pulse
    from .native_resource_rates import (NativeBinding, NativeRateTrial, SPECS as RATE_SPECS,
                                        TARGETS, bind_health_readers, make_local_resolver, original_pool_identity)
    from .skill_pulse import SkillPulse, bind, SPECS as POOL_SPECS, ACTION_NAMES, bind_action_percent
    if mode not in TARGETS or health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore active features before native resource-rate trial')
    sdk=sys.modules['unrealsdk'];u=sdk.unreal
    names=set(RATE_SPECS)|set(POOL_SPECS)|set(ACTION_NAMES)|{'GetResourcePoolValue','GetResourcePoolPercent'}
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in names]
    binding=NativeBinding(functions,loot_bound,u.FGbxDefPtr,u.WrappedStruct)
    session=bound_session(sdk)
    def context():return current_session(session)
    def permitted():
        hooks=sdk.hooks
        return (mod.is_enabled is True and _offline_confirmed and auto_master.value is not True and not _auto_owned
                and not _automation_leases and not conflicting_mods() and _monitor_registered
                and _monitor_thread==threading.get_ident()
                and hooks.has_hook(_MONITOR_PATH,hooks.Type.POST_UNCONDITIONAL,_MONITOR_ID) is True)
    readers=None;skill=None
    if mode=='health':readers=bind_health_readers(functions,loot_bound)
    else:
        ref,api=bind(functions,loot_bound)
        adaptive=bind_action_percent(functions,loot_bound,mode,ref)
        skill=SkillPulse(context,u.WeakPointer,u.FGameDataHandle,u.WrappedInlineStruct,u.WrappedStruct,ref,api,
                         lambda:sdk.find_all('GbxSkill',exact=True),time.monotonic,threading.get_ident,report_live,mode,
                         adaptive_api=adaptive,soft_identifier=getattr(getattr(u,'ZSoftObjectProperty',None),'_get_identifier_from_array',None))
    resolve=make_local_resolver(mode,binding,context,u.FGameDataHandle,readers,skill)
    _health_pulse=NativeRateTrial(mode,binding,resolve,u.WeakPointer,time.monotonic,threading.get_ident,report_live,permitted,lambda key:original_pool_identity(mode,key))
    _health_pulse.begin()


def begin_skill_pulse(mode):
    global _health_pulse
    from .skill_pulse import SkillPulse, bind, SPECS
    if health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore existing features before isolated skill experiment')
    sdk=sys.modules['unrealsdk']; u=sdk.unreal
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS]
    ref,api=bind(functions,loot_bound); session=bound_session(sdk)
    _health_pulse=SkillPulse(lambda:current_session(session),u.WeakPointer,u.FGameDataHandle,u.WrappedInlineStruct,u.WrappedStruct,ref,api,lambda:sdk.find_all('GbxSkill',exact=True),time.monotonic,threading.get_ident,report_live,mode,soft_identifier=getattr(getattr(u,'ZSoftObjectProperty',None),'_get_identifier_from_array',None))
    _health_pulse.begin()


def begin_loot_vacuum(selection,continuous=False):
    global _health_pulse
    from .loot_vacuum import Vacuum
    if health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore active modifiers before isolated vacuum')
    sdk = sys.modules['unrealsdk']
    session = bound_session(sdk)
    if len(selection) not in (2,3):raise ValueError('invalid vacuum selection')
    categories, radius = selection[:2]
    high_gear_only = selection[2] if len(selection)==3 else False
    _health_pulse = Vacuum(lambda: current_session(session), sdk.unreal.WeakPointer, sdk.find_all,
                          sdk.make_struct, time.monotonic, threading.get_ident, report_live, categories, radius, continuous=continuous,high_gear_only=high_gear_only)
    _health_pulse.begin()


def begin_reload_assist(continuous=False):
    global _health_pulse
    from .reload_assist import ReloadAssist, bind, SPECS
    if health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore existing features before isolated reload experiment')
    sdk=sys.modules['unrealsdk']
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS or str(f.Name)=='ServerStartReloading']
    api,fn=bind(functions,loot_bound); session=bound_session(sdk)
    _health_pulse=ReloadAssist(lambda:current_session(session),sdk.unreal.WeakPointer,api,fn,time.monotonic,threading.get_ident,report_live,continuous)
    _health_pulse.begin()


def request_stop(reason, *, immediate=False):
    global _offline_confirmed, _auto_blocked, _auto_ground
    _offline_confirmed = False
    stop_health_pulse(reason)
    stop_automation(reason)
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
_GROUND_ID = 'bl4_custom_ground_speed_v0743exp'
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
    if _automation_busy or automation_fault():
        return
    request = _activation_request
    automatic = _auto_ground is not None and _auto_owned
    queued = request is not None and request[0] in GROUND_KEYS
    if automatic:
        request = ('walk_speed', _auto_ground[0], _monitor_thread, _auto_ground[1])
        queued = True
    elif _auto_owned:
        queued = False  # manual requests may never cross into automatic mode
    active = _controller is not None and bool(GROUND_KEYS.intersection(_controller.records))
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
                _controller = Controller(context, sdk.unreal.WeakPointer, report_live, threading.get_ident, shield_binding=shield_binding)
            _controller.activate(request[0], request[1], ground_sprinting=stance)
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
    if _automation_busy:
        return  # do not re-enter or change monitor identity during native dispatch
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
    if health_active():
        try:
            hooks = sys.modules['unrealsdk'].hooks
            permitted = (mod.is_enabled and _offline_confirmed and not auto_master.value and not _auto_owned
                         and not conflicting_mods() and hooks.has_hook(_MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL, _MONITOR_ID) is True)
        except Exception:
            permitted = False
        _health_pulse.tick(permitted)
        return
    if _health_pulse is not None and _health_pulse.fault:
        return
    if auto_master.value is True or _auto_owned or _automation_leases:
        auto_tick()
        report_auto_status_change()
        automation_tick()
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
        if GROUND_KEYS.intersection(_controller.records) and time.monotonic() - _ground_seen > 2.0:
            _controller.restore_all('local animation callback stale')
        else:
            _controller.tick(permitted)
        if not _controller.records or _controller.fault:
            _offline_confirmed = False
    expire_activation()
    request = _activation_request
    if request is None or request[0] in GROUND_KEYS:
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
        if health_fault() or automation_fault() or (_controller is not None and _controller.fault):
            raise ValueError('fault latched; exit game')
        execute_activation(key, selection)
    except Exception as exc:
        report_live('HOLD: game-hook execution rejected: ' + str(exc)[:160])
        if _controller is not None and _controller.records:
            request_stop('queued activation preflight failed', immediate=False)


def activate_feature(key, selection):
    global _activation_request
    try:
        if health_fault() or automation_fault() or (_controller is not None and _controller.fault):
            raise ValueError('fault latched; exit game')
        if health_active():
            raise ValueError('stop isolated health recovery first')
        if key in ('native_rate_health','native_rate_cooldown','native_rate_duration','health_pulse','health_overtime','health_regen_native','shield_pulse','skill_cooldown','skill_duration','reload_assist','reload_continuous','loot_vacuum','loot_vacuum_continuous') and _controller is not None and _controller.records:
            raise ValueError('restore active modifiers before isolated health recovery')
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
        if key in GROUND_KEYS and not ensure_ground_hook():
            raise ValueError('local animation hook unavailable')
        expire_activation()
        if _activation_request is not None:
            raise ValueError('another activation is already queued')
        if not report_live('QUEUED ' + key + ': ' + repr(selection) + (' slots; ' if key in CAPACITY_KEYS else 'x; ') + monitor_status()):
            return
        _activation_request = (key, selection, threading.get_ident(), time.monotonic() + 3.0)
    except Exception as exc:
        report_live('HOLD: ' + str(exc)[:160])
        if _controller is not None and _controller.records and _activation_request is None:
            request_stop('activation preflight failed', immediate=False)


def execute_activation(key, selection):
    global _controller
    # Called exclusively by monitor_tick after the explicit queued F8 action.
    if key in ('loot_vacuum','loot_vacuum_continuous'):
        begin_loot_vacuum(selection,continuous=key=='loot_vacuum_continuous')
        return
    if key in ('reload_assist','reload_continuous'):
        begin_reload_assist(key=='reload_continuous')
        return
    if key in ('skill_cooldown','skill_duration'):
        begin_skill_pulse(key.split('_',1)[1])
        return
    if key in ('native_rate_health','native_rate_cooldown','native_rate_duration'):
        if selection != 1.0:raise ValueError('invalid native rate trial selection')
        begin_native_resource_rate(key.rsplit('_',1)[1])
        return
    if key == 'health_regen_native':
        if selection != 1.0:raise ValueError('invalid native regeneration selection')
        begin_native_regen()
        return
    if key == 'health_overtime':
        if selection != 1.0:raise ValueError('invalid native overtime selection')
        begin_native_overtime()
        return
    if key in ('health_pulse','shield_pulse'):
        begin_health_pulse('flesh' if key=='health_pulse' else 'shield')
        return
    if _controller is None or not _controller.records:
        sdk = sys.modules['unrealsdk']
        api = bound_session(sdk)
        _controller = Controller(lambda: current_session(api), sdk.unreal.WeakPointer,
                                 report_live, threading.get_ident, shield_binding=shield_binding)
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
            stop_automation('master save failed')
            auto_master.value = False
            _auto_edits.clear()
            _auto_ground = None
            report_live('HOLD: master off in memory; saved settings may still be on, check before restart')
        report_live('HOLD: ' + str(exc)[:120])
        return
    if option in AUTOMATION_OPTIONS.values():
        kind = next(k for k,o in AUTOMATION_OPTIONS.items() if o is option)
        stop_automation_lane(kind, 'automation preference changed')
        if value is True and not automation_fault():
            _automation_attempted.discard(kind)
            _automation_status[kind] = 'Waiting for eligible session'
    if option is auto_master:
        stop_automation('persistent master changed')
        if value is True and not automation_fault():
            _automation_attempted.clear()
        if value is True:
            stop_health_pulse('persistent master enabled')
        _auto_ground = None
        _auto_edits.clear()
        _auto_blocked = ('Capacity restore waiting: remove excess items' if _controller is not None and any(r.get('overfull_warning') for r in _controller.records.values()) else '')
        _auto_next = 0.0
        cancel_activation('persistent mode changed')
        _pending.clear()
        if value is True:
            ensure_monitor()
    if option is auto_consent and value is not True:
        stop_automation("offline consent withdrawn")
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
    stop_automation(reason)
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


def raw_auto_desired(keys=None):
    desired = {}
    for key in AUTO_OPTIONS if keys is None else keys:
        flag = AUTO_OPTIONS[key]
        if flag.value is not True:
            continue
        if key in _auto_edits:
            record = _controller.records.get(key) if _auto_owned and _controller is not None else None
            if record is not None:
                desired[key] = record['selection']
            elif key in AMMO_GROUP | LIFE_KEYS and _PREVIEW_BY_KEY[key].value != 1.0:
                # Preserve committed mutually exclusive selections while a draft saves.
                desired[key] = _PREVIEW_BY_KEY[key].value
        elif _PREVIEW_BY_KEY[key].value != 1.0:
            desired[key] = _PREVIEW_BY_KEY[key].value
    return desired


def ammo_selection_conflict(desired):
    return PLAYER_AMMO_KEY in desired and bool(AMMO_KEYS.intersection(desired))


def auto_desired():
    desired = raw_auto_desired()
    # Refuse ambiguous saved selections rather than silently choosing a winner.
    if ammo_selection_conflict(desired):
        desired = {k: v for k, v in desired.items() if k not in AMMO_GROUP}
    if LIFE_KEYS <= set(desired):
        desired = {k: v for k, v in desired.items() if k not in LIFE_KEYS}
    # A draft cannot initiate an inactive mutually exclusive modifier.
    for key in (AMMO_GROUP | LIFE_KEYS).intersection(_auto_edits):
        if not (_auto_owned and _controller is not None and key in _controller.records):
            desired.pop(key, None)
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


def pending_slide_selection():
    # Only a committed, explicitly opted-in, currently inactive slide may use
    # the faster lane. Active values and edits remain on the normal schedule.
    if (not _auto_owned or _controller is None or 'slide_speed' in _controller.records
            or 'slide_speed' in _auto_edits or not auto_allowed()):
        return None
    return raw_auto_desired(('slide_speed',)).get('slide_speed')


def fast_slide_admission(selection):
    global _auto_blocked, _auto_ground
    if _controller.stop_pending is not None or pending_slide_selection() != selection:
        return
    try:
        rec = _controller.capture('slide_speed')
        _, values, eligible = _controller.resolve(rec)
        if not eligible or values != rec['expected']:
            return
        target_values('slide_speed', rec['baseline'], rec['tokens'], selection)
    except (AttributeError, TypeError, ValueError):
        return  # missing/inactive native movement: no write
    if _controller.stop_pending is not None or pending_slide_selection() != selection:
        return
    if not _controller.activate('slide_speed', selection):
        _auto_ground = None
        _auto_blocked = 'Activation failed: slide_speed; toggle master to retry'


def auto_tick():
    """Camera callback only. Reconcile saved desired settings in owner-confirmed offline solo mode (R2 admission).
    No implicit legacy migration, no retry after unexpected drift or failed write.
    """
    global _controller, _auto_owned, _auto_blocked, _auto_ground, _auto_next, _auto_api, _auto_status, _slide_next
    now = time.monotonic()
    if _activation_request is not None:
        cancel_activation('persistent mode selected')
    if _controller is not None and (_controller.busy or _controller.fault):
        return
    if automation_fault():
        if _controller is not None and _controller.records:
            _controller.restore_all("automation fault")
        return
    slide_selection = pending_slide_selection() if now >= _slide_next else None
    if not (_controller is not None and _controller.records) and _auto_ground is None and now < _auto_next and slide_selection is None:
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
            stop_automation('persistent session no longer eligible')
            _controller.restore_all('persistent session no longer eligible')
            if _controller.fault:
                _auto_blocked = 'Restoration fault; exit game'
            else:
                _auto_owned = False
            return
        before = set(_controller.records)
        transitioned = _controller.tick(True, observed=observed, follow_weapon=True, follow_shield=True, follow_gadget=True) or set()
        if set(_controller.records) != before - transitioned or _controller.fault:
            _auto_ground = None
            _auto_blocked = 'Unexpected active field change; toggle master to retry'
            return
    if now < _auto_next:
        if slide_selection is not None:
            _slide_next = now + .05
            # Never shorten the loading/reflection backoff or change the normal
            # 250ms cadence; all active monitoring and permission checks ran above.
            if _auto_next - now <= .25 and (_auto_ground is None or now < _auto_ground[1]):
                fast_slide_admission(slide_selection)
        return
    _slide_next = now + .05
    _auto_next = now + .25
    desired = auto_desired()
    if not desired and not (_controller is not None and _controller.records):
        _auto_ground = None
        _auto_owned = False
        _auto_status = ('Waiting for slider edit to save' if _auto_edits else
                        'Waiting: choose player OR weapon ammo regeneration' if ammo_selection_conflict(raw_auto_desired(AMMO_GROUP)) else
                        'Ready; automation preferences managed separately' if any(o.value is True for o in AUTOMATION_OPTIONS.values()) else 'Ready; enable a feature and select a non-1x value')
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
            _controller = Controller(context, sys.modules['unrealsdk'].unreal.WeakPointer, report_live, threading.get_ident, shield_binding=shield_binding)
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
        _auto_next = _slide_next = now + 1.0  # loading screen or missing reflection: bounded retry, no writes
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
                if _controller.records.get(key, {}).get('overfull_warning') and not _controller.fault:
                    _auto_blocked = 'Capacity restore waiting: remove excess items; toggle master only after restoration'
                    stop_automation('capacity restore waiting')
                    _controller.restore_all('capacity restore waiting')
                else:
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
        if key in CAPACITY_KEYS:
            # Invalid or not-yet-loaded inventory waits without shrinking or blocking other fields.
            try:
                rec = _controller.records.get(key) or _controller.capture(key)
                _, count = resolve_capacity(observed[0], observed[1], rec['inventory_scope'])
                targets = target_values(key, rec['baseline'], rec['tokens'], selection)
                validate_capacity(rec['inventory_scope'], count, targets[0], applying=True)
            except (AttributeError, TypeError, ValueError):
                continue
        if key in NEW_MOVE_KEYS or key in (GADGET_KEY, PLAYER_AMMO_KEY):
            # Wait for exact reflected local field or idle equipped gadget.
            try:
                rec = _controller.records.get(key) or _controller.capture(key)
                _, values, eligible = _controller.resolve(rec)
                if not eligible or values != rec['expected']:
                    continue
                if key == GADGET_KEY and rec['gadget_scope'][0]().bIsUsing is not False:
                    continue
                target_values(key, rec['baseline'], rec['tokens'], selection)
            except (AttributeError, TypeError, ValueError):
                continue
        if key in SHIELD_KEYS:
            # Wait for an ordinary energy shield without interrupting unrelated controls.
            try:
                rec = _controller.records.get(key) or _controller.capture(key)
                _, values, eligible = _controller.resolve(rec)
                if not eligible or values != rec['expected']:
                    continue
                validate_shield_readback(rec['shield_scope'][0](), key, values[0])
                target_values(key, rec['baseline'], rec['tokens'], selection)
            except (AttributeError, TypeError, ValueError):
                continue
            if 'shield' in _automation_leases:
                stop_automation_lane('shield', 'native shield modifier selected; toggle lane to rearm')
                if automation_fault():
                    _controller.restore_all('shield assist fault')
                    return
        if key in LIFE_KEYS:
            # Wait for a positive existing effect without blocking unrelated fields.
            try:
                rec = _controller.records.get(key) or _controller.capture(key)
                _, values, eligible = _controller.resolve(rec)
                if not eligible or values != rec['expected']:
                    continue
                targets = target_values(key, rec['baseline'], rec['tokens'], selection)
                peers = lifesteal_peer_context(key, rec['pawn'](), rec['baseline'], targets, rec['tokens'])
                if key in _controller.records and peers != rec['life_context']:
                    continue
            except (AttributeError, TypeError, ValueError):
                continue
            if 'health' in _automation_leases:
                stop_automation_lane('health', 'native life-steal modifier selected; toggle lane to rearm')
                if automation_fault():
                    _controller.restore_all('health assist fault')
                    return
        if key in WEAPON_KEYS:
            # Do not interrupt firing/reloading or block other controls on an unsupported gun.
            # A fresh capture is read-only; activate independently rechecks scope before writing.
            try:
                rec = _controller.records.get(key) or _controller.capture(key)
                targets = target_values(key, rec['baseline'], rec['tokens'], selection)
                validate_targets(rec['weapon_scope'], targets)
            except (AttributeError, TypeError, ValueError):
                continue
        if not _controller.activate(key, selection):
            _auto_ground = None
            _auto_blocked = 'Activation failed: ' + key + '; toggle master to retry'
            return
        break  # at most one non-animation activation per reconciliation interval


def automation_fault():
    return any(l.fault for l in _automation_leases.values())


def stop_automation_lane(kind, reason):
    lease = _automation_leases.get(kind)
    if lease is not None:
        lease.stop(reason)
        if not lease.fault:
            _automation_leases.pop(kind, None)
    _automation_status[kind] = 'Stopped: '+reason


def stop_automation(reason):
    for kind in tuple(_automation_leases):
        stop_automation_lane(kind, reason)


def automation_permitted():
    if not auto_allowed() or conflicting_mods() or health_active() or automation_fault():
        return False
    if _controller is not None and (_controller.fault or _controller.busy or _controller.stop_pending is not None):
        return False
    if _controller is not None and _controller.records and not _auto_owned:
        return False
    if _controller is not None and any(r.get('overfull_warning') for r in _controller.records.values()):
        return False
    if _controller is not None and not set(_controller.records) <= _AUTOMATION_COMPATIBLE:
        return False
    if not set(auto_desired()) <= _AUTOMATION_COMPATIBLE:
        return False
    hooks = sys.modules['unrealsdk'].hooks
    return _monitor_registered and hooks.has_hook(_MONITOR_PATH,hooks.Type.POST_UNCONDITIONAL,_MONITOR_ID) is True


def ensure_jump_event():
    """Optional early observation; missing event never disables periodic lane."""
    global _jump_event_attempted, _jump_event_owned
    if _jump_event_attempted:return _jump_event_owned
    _jump_event_attempted=True
    try:
        sdk=sys.modules['unrealsdk']; hooks=sdk.hooks; kind=hooks.Type.POST
        matches=[f for f in sdk.find_all('Function',exact=False)
                 if str(f.Name)=='OnJumped' and f._path_name()==_JUMP_EVENT_PATH]
        if len(matches)!=1:return False
        fn=matches[0]
        if fn.NumParams!=0 or tuple(fn._properties()) or fn.Outer._path_name()!='/Script/Engine.Character':return False
        if hooks.has_hook(_JUMP_EVENT_PATH,kind,_JUMP_EVENT_ID) is not False:return False
        added=hooks.add_hook(_JUMP_EVENT_PATH,kind,_JUMP_EVENT_ID,jump_event_tick)
        # SDK may report False after appending; membership and callback invocation
        # are checked without adopting a pre-existing identifier.
        _jump_event_owned=type(added) is bool and hooks.has_hook(_JUMP_EVENT_PATH,kind,_JUMP_EVENT_ID) is True
    except Exception:_jump_event_owned=False
    return _jump_event_owned


def jump_event_tick(obj,*_):
    global _automation_busy
    lease=_automation_leases.get('double_jump')
    if (not _jump_event_owned or _automation_busy or lease is None or lease.record is None
            or lease.fault or lease.busy or _monitor_thread!=threading.get_ident()
            or not auto_allowed() or AUTOMATION_OPTIONS['double_jump'].value is not True):return
    try:
        # Cheap original-actor identity gate before the more expensive native checks.
        if obj is None or identity(obj)!=lease.record[1][1]:return
        hooks=sys.modules['unrealsdk'].hooks
        if hooks.has_hook(_JUMP_EVENT_PATH,hooks.Type.POST,_JUMP_EVENT_ID) is not True:return
        if not automation_permitted():return
    except Exception:return
    _automation_busy=True
    try:
        lease.tick(True,event_pawn=obj)
        if lease.fault:
            _automation_leases['double_jump']=lease
            request_stop('double jump event native fault',immediate=False)
        elif lease.record is None:
            stop_automation_lane('double_jump','lease ended; toggle lane to rearm')
    finally:_automation_busy=False


def recovery_conflict(kind):
    if kind not in ('health', 'shield'):
        return ''
    selected = set(raw_auto_desired(SHIELD_KEYS | {'healing_received'}))
    active = set(_controller.records) if _controller is not None else set()
    if 'healing_received' in selected | active:
        return 'healing multiplier incompatible'
    if kind == 'health' and LIFE_KEYS.intersection(set(auto_desired()) | active):
        return 'native life-steal modifier incompatible with flesh assist'
    if kind == 'shield' and SHIELD_KEYS.intersection(selected | active):
        return 'native shield modifier incompatible with shield assist'
    return ''


def crossfire_hooks_live():
    if _crossfire_hooks is None:return False
    hooks=sys.modules['unrealsdk'].hooks
    return all(hooks.has_hook(path,kind,tag) is True for path,kind,tag in _crossfire_hooks[1])


def crossfire_event(obj,starting):
    lease=_automation_leases.get('skill_duration')
    if (lease is None or lease.record is None or getattr(lease,'event_class',None) is None
            or _monitor_thread!=threading.get_ident()):return
    try:
        if not crossfire_hooks_live():return
        # No SDK getters or game mutations from this callback. Start events
        # only record a witness; the normal monitor still validates scope.
        lease.observe_event(obj,starting)
    except Exception:
        lease.event_active=False;lease.event_epoch+=1


def ensure_crossfire_events():
    global _crossfire_attempted,_crossfire_hooks
    from .skill_pulse import CROSSFIRE_CLASS,CROSSFIRE_EVENTS
    sdk=sys.modules['unrealsdk'];hooks=sdk.hooks
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in CROSSFIRE_EVENTS]
    found=[]
    for name in CROSSFIRE_EVENTS:
        path=CROSSFIRE_CLASS+':'+name
        matches=[f for f in functions if f._path_name()==path]
        if len(matches)!=1:raise ValueError('Cross-Fire event missing or ambiguous')
        fn=matches[0]
        if fn.NumParams!=0 or tuple(fn._properties()) or fn.Outer._path_name()!=CROSSFIRE_CLASS:
            raise ValueError('Cross-Fire event signature mismatch')
        found.append(fn)
    owner=identity(found[0].Outer)
    if identity(found[1].Outer)!=owner:raise ValueError('Cross-Fire event owner mismatch')
    fn_ids=tuple(identity(f) for f in found)
    if _crossfire_attempted:
        if not crossfire_hooks_live() or _crossfire_hooks[0]!=owner or _crossfire_hooks[2]!=fn_ids:raise ValueError('Cross-Fire hooks unavailable; restart game')
        return owner
    specs=tuple((f._path_name(),kind,'bl4_custom_crossfire_r60_'+str(i))
                for i,(f,kind) in enumerate(zip(found,(hooks.Type.POST,hooks.Type.PRE),strict=True)))
    if any(hooks.has_hook(*spec) is not False for spec in specs):raise ValueError('Cross-Fire hook identifier conflict')
    _crossfire_attempted=True
    # A partially registered pair stays inert and is never treated as owned.
    for i,spec in enumerate(specs):
        cb=(lambda obj,*_:crossfire_event(obj,True)) if i==0 else (lambda obj,*_:crossfire_event(obj,False))
        added=hooks.add_hook(*spec,cb)
        if type(added) is not bool or hooks.has_hook(*spec) is not True:raise ValueError('Cross-Fire hook registration failed; restart game')
    _crossfire_hooks=(owner,specs,fn_ids)
    return owner


def make_automation_lane(kind, session):
    sdk = sys.modules['unrealsdk']
    adaptive_mode = kind in SKILL_ADAPTIVE and SKILL_ADAPTIVE[kind].value is True
    native_mode = kind in SKILL_NATIVE and SKILL_NATIVE[kind].value is True
    follow_mode = kind in SKILL_FOLLOW and SKILL_FOLLOW[kind].value is True
    event_mode = kind=='skill_duration' and CROSSFIRE_GATE.value is True
    jump_rate = normalize(DOUBLE_JUMP_RATE,DOUBLE_JUMP_RATE.value) if kind=='double_jump' else None
    def context():
        if kind=='double_jump' and (DOUBLE_JUMP_RATE.identifier in _auto_edits or normalize(DOUBLE_JUMP_RATE,DOUBLE_JUMP_RATE.value)!=jump_rate):
            raise ValueError('double jump scale changed; toggle lane to rearm')
        if kind=='skill_duration':
            if (CROSSFIRE_GATE.value is True)!=event_mode:raise ValueError('Cross-Fire event mode changed')
            if event_mode and not crossfire_hooks_live():raise ValueError('Cross-Fire event hooks lost')
        if kind in SKILL_ADAPTIVE:
            if (SKILL_NATIVE[kind].value is True)!=native_mode:
                raise ValueError('native refill mode changed')
            if (SKILL_FOLLOW[kind].value is True)!=follow_mode:
                raise ValueError('follow skill mode changed')
            if (SKILL_ADAPTIVE[kind].value is True)!=adaptive_mode:
                raise ValueError('adaptive mode changed')
            lease=_automation_leases.get(kind)
            if adaptive_mode and lease is not None and lease.rate!=normalize(SKILL_RATES[kind],SKILL_RATES[kind].value):
                raise ValueError('adaptive rate changed during callback')
        if AUTOMATION_OPTIONS[kind].value is not True or not automation_permitted():
            raise ValueError('persistent automation permission ended')
        conflict = recovery_conflict(kind)
        if conflict:
            raise ValueError(conflict)
        return current_session(session)
    if kind == 'double_jump':
        from .double_jump import DoubleJump
        return DoubleJump(context,sdk.unreal.WeakPointer,time.monotonic,threading.get_ident,report_live,jump_rate)
    if kind == 'vacuum':
        from .loot_vacuum import Vacuum
        categories = tuple(k for k,o in VACUUM_PREFS.items() if o.value is True)
        radius = normalize(VACUUM_RADIUS_PREF,VACUUM_RADIUS_PREF.value)
        return Vacuum(context,sdk.unreal.WeakPointer,sdk.find_all,sdk.make_struct,time.monotonic,threading.get_ident,report_live,categories,radius,continuous=True,high_gear_only=VACUUM_HIGH_PREF.value is True)
    if kind in ('health','shield'):
        from .health_pulse import Pulse, bind, SPECS
        functions = [f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS]
        api = bind(functions,loot_bound)
        return Pulse(context,sdk.unreal.WeakPointer,sdk.unreal.FGameDataHandle,api,time.monotonic,threading.get_ident,report_live,mode='flesh' if kind=='health' else 'shield',continuous=True,percent=normalize(RECOVERY_RATES[kind],RECOVERY_RATES[kind].value))
    if kind in ('skill_cooldown','skill_duration'):
        from .skill_pulse import SkillPulse, bind, SPECS, ACTION_NAMES, bind_action_percent, NATIVE_REFILL_NAMES, bind_native_refill, DIRECT_NAMES, bind_direct_cooldown
        u=sdk.unreal
        adaptive=adaptive_mode
        if native_mode and not adaptive:raise ValueError('dedicated native refill requires adaptive mode')
        functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS or (adaptive and str(f.Name) in ACTION_NAMES) or (native_mode and str(f.Name) in NATIVE_REFILL_NAMES) or (native_mode and kind=='skill_cooldown' and str(f.Name) in DIRECT_NAMES)]
        ref,api=bind(functions,loot_bound)
        mode=kind.split('_',1)[1]
        extra=bind_action_percent(functions,loot_bound,mode,ref) if adaptive else None
        native=bind_native_refill(functions,loot_bound,mode,ref) if native_mode else None
        if event_mode and (native is None or follow_mode):raise ValueError('Cross-Fire event gate requires dedicated adaptive duration and follow OFF')
        event_class=ensure_crossfire_events() if event_mode else None
        direct=None
        if native_mode and kind=='skill_cooldown':
            try:direct=bind_direct_cooldown(functions,loot_bound)
            except (ValueError,AttributeError,TypeError):pass  # ordinary dedicated path unchanged
        return SkillPulse(context,u.WeakPointer,u.FGameDataHandle,u.WrappedInlineStruct,u.WrappedStruct,ref,api,lambda:sdk.find_all('GbxSkill',exact=True),time.monotonic,threading.get_ident,report_live,mode,continuous=True,adaptive_api=extra,rate=normalize(SKILL_RATES[kind],SKILL_RATES[kind].value),soft_identifier=getattr(getattr(u,'ZSoftObjectProperty',None),'_get_identifier_from_array',None),follow=follow_mode,native_refill=native,event_class=event_class,direct_api=direct)
    if kind != 'reload': raise ValueError('unknown automation lane')
    from .reload_assist import ReloadAssist, bind, SPECS
    functions = [f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS or str(f.Name)=='ServerStartReloading']
    api,fn = bind(functions,loot_bound)
    return ReloadAssist(context,sdk.unreal.WeakPointer,api,fn,time.monotonic,threading.get_ident,report_live,True,session_mode=True)


def automation_tick():
    """Independent per-lane lifetime, after the existing modifier monitor. No implicit retry after an arm ends."""
    global _automation_busy, _automation_next
    if _automation_busy:
        return
    if not _automation_leases and not any(o.value is True and k not in _automation_attempted for k,o in AUTOMATION_OPTIONS.items()):
        return
    _automation_busy = True
    try:
        if not automation_permitted():
            stop_automation('permission or modifier compatibility ended')
            return
        # Each lane has its own fresh session and weak identity validation. Never share a native object across lanes.
        for kind in ('vacuum','reload','health','shield','skill_cooldown','skill_duration','double_jump'):
            if AUTOMATION_OPTIONS[kind].value is not True:
                stop_automation_lane(kind,'disabled')
                continue
            if not automation_permitted():
                stop_automation('permission ended before next lane')
                return
            conflict = recovery_conflict(kind)
            if conflict:
                if kind in _automation_leases:
                    stop_automation_lane(kind, conflict+'; toggle lane to rearm')
                elif kind not in _automation_attempted:
                    _automation_status[kind] = 'Waiting: '+conflict
                continue
            lease = _automation_leases.get(kind)
            if lease is not None:
                if kind == 'vacuum' and callable(getattr(lease,'update_preferences',None)):
                    args=(tuple(k for k,o in VACUUM_PREFS.items() if o.value is True), normalize(VACUUM_RADIUS_PREF,VACUUM_RADIUS_PREF.value))
                    if hasattr(lease,'high_gear_only'):lease.update_preferences(*args,high_gear_only=VACUUM_HIGH_PREF.value is True)
                    else:lease.update_preferences(*args)
                if kind in RECOVERY_RATES and callable(getattr(lease,'update_rate',None)):
                    rate=RECOVERY_RATES[kind]
                    lease.update_rate(normalize(rate,rate.value))
                if kind=='skill_duration' and (getattr(lease,'event_class',None) is not None)!=(CROSSFIRE_GATE.value is True):
                    stop_automation_lane(kind,'Cross-Fire event mode changed; toggle lane to rearm');continue
                if kind in SKILL_ADAPTIVE and hasattr(lease,'adaptive_api'):
                    if (getattr(lease,'native_refill',None) is not None)!=(SKILL_NATIVE[kind].value is True):
                        stop_automation_lane(kind,'native refill mode changed; toggle lane to rearm');continue
                    if getattr(lease,'follow',False)!=(SKILL_FOLLOW[kind].value is True):
                        stop_automation_lane(kind,'follow mode changed; toggle lane to rearm');continue
                    if (lease.adaptive_api is not None)!=(SKILL_ADAPTIVE[kind].value is True):
                        stop_automation_lane(kind,'adaptive mode changed; toggle lane to rearm');continue
                    lease.update_adaptive_rate(normalize(SKILL_RATES[kind],SKILL_RATES[kind].value))
                lease.tick(True)
                if lease.fault:
                    _automation_leases[kind] = lease  # retain late fault even after reentrant stop
                    request_stop('automation native fault',immediate=False)
                    return
                if lease.record is None:
                    stop_automation_lane(kind,'lease ended; toggle lane to rearm')
                elif kind=='reload' and hasattr(lease,'swap_paused'):
                    _automation_status[kind] = 'Waiting for supported loaded idle gun and reserve' if lease.swap_paused or lease.reserve_paused else 'Armed (gameplay unverified)'
                elif kind=='skill_duration' and getattr(lease,'event_class',None) is not None:
                    _automation_status[kind] = 'Observed Cross-Fire active (gameplay unverified)' if lease.event_active else 'Waiting for a new local Cross-Fire activation'
                elif kind in SKILL_FOLLOW and getattr(lease,'follow',False):
                    _automation_status[kind] = 'Waiting: distinct skill replacement witness' if lease.follow_candidate is not None else 'Armed (gameplay unverified)'
                continue
            if kind in _automation_attempted or time.monotonic() < _automation_next:
                continue
            _automation_next = time.monotonic()+.25
            try:
                session = bound_session(sys.modules['unrealsdk'])
                if not current_session(session)[3]:
                    continue  # wait for a loaded eligible character, without dispatch
            except Exception:
                continue
            _automation_attempted.add(kind)
            try:
                lease = make_automation_lane(kind,session)
                _automation_leases[kind] = lease
                begun = lease.begin()
                if lease.fault:
                    _automation_leases[kind] = lease
                    request_stop('automation admission fault', immediate=False)
                    return
                if not begun or _automation_leases.get(kind) is not lease or not automation_permitted():
                    lease.stop('admission ended')
                    stop_automation_lane(kind,'admission failed; toggle lane to rearm')
                else:
                    _automation_status[kind] = 'Armed (gameplay unverified)'
                    if kind=='double_jump' and lease.rate!=1.:
                        ensure_jump_event()
            except Exception as exc:
                stop_automation_lane(kind,'admission failed: '+str(exc)[:100])
    except Exception as exc:
        stop_automation('preflight failed: '+str(exc)[:100])
    finally:
        _automation_busy = False

def enabled():
    if auto_master.value is True and auto_consent.value is True:
        ensure_monitor()
    print('[BL4 Custom] v0.7.61-experimental enabled; F8 opens menu. Persistent gameplay requires explicit opt-in.')


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
options += [NestedOption('persistent', AUTO_SETTINGS, display_name='Persistent gameplay (experimental)'), NestedOption('vacuum_preferences', [*VACUUM_PREFS.values(), VACUUM_RADIUS_PREF, VACUUM_HIGH_PREF], display_name='Saved vacuum preferences (no startup activation)')]
options += [NestedOption('recovery_rates', list(RECOVERY_RATES.values()), display_name='Recovery pulse rates (experimental)'), NestedOption('adaptive_skill', [*SKILL_ADAPTIVE.values(),*SKILL_RATES.values(),*SKILL_FOLLOW.values(),*SKILL_NATIVE.values(),CROSSFIRE_GATE], display_name='Adaptive skill assist (experimental)')]
options += [NestedOption(key, items, display_name=name, description=DESCRIPTION)
            for key, name, items in CATEGORIES if key != 'menu']
options += [NestedOption('menu', [ButtonOption('open_from_menu', display_name='Open Graphical Menu', on_press=toggle_menu)], display_name='Custom Menu'),
            ButtonOption('reset_preview', display_name='Restore Vanilla Defaults', on_press=reset)]
mod = build_mod(options=options, hooks=[], commands=[], keybinds=[open_key], auto_enable=True,
                on_enable=enabled, on_disable=disabled)
