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
REWARD_KEYS = frozenset(('progress_enemy_xp', 'progress_money', 'progress_eridium'))
GUN_TRIAL_KEY = 'native_gun_damage'
MELEE_TRIAL_KEY = 'native_melee_damage'
RELOAD_TRIAL_KEY = 'native_weapon_reload'
FIRE_RATE_TRIAL_KEY = 'native_weapon_fire_rate'
FAILED_XP_KEY = 'progress_enemy_xp'
FAILED_XP_REASON = 'XP experiment failed; disabled pending a different mechanism.'
NEW_MOVE_KEYS = frozenset(('ladder_ascend', 'ladder_descend', 'slam_height', 'ground_friction', 'braking_friction', 'slide_speed'))

TITLE = 'BL4 Custom - Community Integration v0.7.61-experimental'
DESCRIPTION = 'Individual gameplay toggles; saved selections apply in eligible offline solo sessions. Experimental tests remain isolated.'


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
                        display_name=label, description=('Experimental native earned reward trial; actual reward unverified.' if identifier in REWARD_KEYS - {FAILED_XP_KEY} else 'Preview only - reward hook not verified.'))


def toggle(identifier, label):
    return BoolOption(identifier, False, display_name=label, description=DESCRIPTION)


CATEGORIES = [
    ('combat', 'Combat', [SliderOption('damage', 1., .5, 5., step=.1, is_integer=False, display_name='Damage multiplier', description='Experimental equipped ordinary gun damage; 1x restores. Not a global damage multiplier.'), SliderOption('fire_rate', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['fire_rate'][0], description='Experimental native weapon rate; enabled feature follows supported idle weapons.'), SliderOption('reload', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['reload'][0], description='Experimental stock reload duration; enabled feature follows supported idle weapons. 1x restores.'), SliderOption('swap_time', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['swap_time'][0], description='Local native time scale candidate; individual toggle; direction of gameplay effect unverified. 1x restores.'), *[SliderOption(k, 1., .1, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Experimental weapon field; enabled feature follows supported idle weapons. Lower scales the field down. Native effect unverified. 1x restores.') for k in ('weapon_spread', 'weapon_recoil')], slider('fire_damage', 'Fire damage multiplier'), SliderOption('critical_damage', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['critical_damage'][0], description='Existing pawn default critical-hit multiplier only; does not force critical hits. Manual experimental activation; 1x restores.'), SliderOption('splash_damage', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['splash_damage'][0], description='Existing local causer splash damage only, not radius size or general damage. Isolated manual experiment; 1x restores.'),
        SliderOption('critical_chance', 1., 1., 21., step=1., is_integer=True, display_name=FEATURES['critical_chance'][0], description='Stored 1 = original; 2–21 add 1–20 percentage points to native default chance, not guaranteed crits. Manual experiment.'),
        SliderOption('splash_radius', 1., .5, 2., step=.1, is_integer=False, display_name=FEATURES['splash_radius'][0], description='Local splash coverage only; no damage magnitude or attack changes. Manual experiment; 1x restores.'),
        SliderOption('melee_cooldown', 1., .5, 2., step=.1, is_integer=False, display_name=FEATURES['melee_cooldown'][0], description='Experimental local melee cooldown scale; higher speed shortens the scale. Manual activation only; 1x restores.'),
        slider('damage_taken', 'Damage taken multiplier', minimum=0.1), slider('shock_damage', 'Shock damage multiplier'),
        slider('corrosive_damage', 'Corrosive damage multiplier'), slider('cryo_damage', 'Cryo damage multiplier'),
        slider('radiation_damage', 'Radiation damage multiplier')]),
    ('progression', 'XP and Progression', [progression_slider('progress_character_xp', 'Character XP'),
        progression_slider('progress_specialization_xp', 'Specialization XP'),
        progression_slider('progress_money', 'Money'),
        progression_slider('progress_eridium', 'Eridium'),
        progression_slider('progress_enemy_xp', 'Enemy kill XP'),
        progression_slider('progress_mission_xp', 'Mission XP')]),
    ('loot', 'Loot and Drop Rates', [slider('drops', 'Drop rate multiplier'), SliderOption('overall_loot_luck',1.,1.,10.,step=.1,is_integer=False,display_name='Loot luck (gear category)',description='Experimental gear category only; toggle ON for continuous native modifier. Not an exact drop probability.'), rarity_slider('common_weight', 'Common rarity weight'), rarity_slider('uncommon_weight', 'Uncommon rarity weight'), rarity_slider('rare_weight', 'Rare rarity weight'), rarity_slider('epic_weight', 'Epic rarity weight'), rarity_slider('legendary_weight', 'Legendary rarity weight (selected)'), rarity_slider('pearlescent_weight', 'Pearlescent rarity weight')]),
    ('inventory', 'Inventory', [SliderOption(k, 1., 1., 1000., step=1, is_integer=True, display_name=FEATURES[k][0], description='Experimental absolute slots; 1 restores captured original. Never fill above original capacity during testing.') for k in ('backpack_capacity','bank_capacity')]),
    ('movement', 'Movement', [SliderOption('sprint', 1., 1., 3., step=.1, is_integer=False, display_name='Sprint-only speed floor (reference multiplier)', description='Experimental manual mode; walking stays at original floor. Restore combined ground speed first. 1x restores.'), slider('jump', 'Jump velocity multiplier'), *[SliderOption(k, 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Local movement attribute; individual toggle; 1x restores. Actual speed/distance unverified.') for k in ('dash_speed', 'glide_speed', 'glide_air_control', 'glide_boost', 'glide_acceleration', 'glide_deceleration')], *[SliderOption(k, 1., .1, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Existing positive vault-power cost; lower may reduce consumption. 1x restores. No free energy or new jump actions.') for k in ('double_jump_cost','dash_cost','glide_cost','grapple_cost','slam_cost')], *[SliderOption(k, 1., FEATURES[k][1], FEATURES[k][2], step=.1, is_integer=False, display_name=FEATURES[k][0], description=('Only while exact native slide is active; toggle ON to follow active slides. 1x restores.' if k=='slide_speed' else 'Local movement field only; native effect unverified. 1x restores.')) for k in ('ladder_ascend','ladder_descend','slam_height','ground_friction','braking_friction','slide_speed')], SliderOption('gravity', 1., .5, 1.5, step=.1, is_integer=False, display_name='Local gravity multiplier', description='Experimental local movement only; lower gravity can increase airborne time. 1x restores.'), SliderOption('walk_speed', 1., 1., 3., step=.1, is_integer=False, display_name='Ground speed floor (reference multiplier)', description='1x restores; higher raises walk/sprint floor. Actual speed varies.')]),
    ('automation', 'Automation', [toggle('auto_reload', 'Automatic reload'), toggle('auto_loot', 'Automatic loot pickup')]),
    ('quality', 'Quality of Life', [toggle('auto_ammo', 'Automatic ammo pickup'), slider('cooldown', 'Cooldown multiplier'), slider('repair_cooldown', 'Repair-kit cooldown duration multiplier', minimum=0.1), slider('healing_received', 'Healing received multiplier'), slider('repair_duration', 'Repair-kit healing duration multiplier'), slider('repair_health', 'Repair-kit healing amount multiplier'), SliderOption('overshield_duration', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['overshield_duration'][0], description='Existing positive overshield duration only; manual activation; does not grant shields. 1x restores.'), SliderOption('lifesteal_fraction', 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES['lifesteal_fraction'][0], description='Existing positive normalized life-steal only; individual toggle. 1x restores. Restore other life-steal control first.'), *[SliderOption(k, 1., .5, 3., step=.1, is_integer=False, display_name=FEATURES[k][0], description='Experimental: existing positive native rate only; 1x restores. Weapon ammo, grenade and shield controls support persistent opt-in; player ammo regeneration and existing positive life-steal support persistent opt-in.') for k in ('ammo_regen_rate', 'ammo_regen_delay', 'lifesteal_rate', 'shield_regen_rate', 'shield_regen_delay', 'grenade_cooldown', 'player_ammo_regen')]]),
    ('enemies', 'Enemy Difficulty', [slider('enemy_health', 'Enemy health multiplier'), slider('enemy_damage', 'Enemy damage multiplier')]),
    ('menu', 'Custom Menu', [probe]),
]
PREVIEW = [o for _, _, items in CATEGORIES for o in items if o is not probe]
_PREVIEW_BY_KEY = {o.identifier: o for o in PREVIEW}
_COMPACT_OPTIONS = tuple(tuple(o for o in items if o is probe or o.identifier in ('overall_loot_luck','progress_money') or (o.identifier in FEATURES and o.identifier not in DAMAGE_HOLD)) for _, _, items in CATEGORIES)
# Explicit opt-in, separate from legacy saved preview values. Defaults stay vanilla.
auto_master = BoolOption('persistent_master', False, display_name='Internal activation gate (legacy settings)')
auto_consent = BoolOption('persistent_offline', False, display_name='I use Offline Local Only; tuning mods disabled')
MANUAL_ONLY = frozenset(('sprint', 'overshield_duration', 'critical_damage', 'critical_chance', 'splash_damage', 'splash_radius', 'melee_cooldown'))
LIFE_KEYS = frozenset(('lifesteal_rate', 'lifesteal_fraction'))
PLAYER_AMMO_KEY = 'player_ammo_regen'
AMMO_GROUP = AMMO_KEYS | {PLAYER_AMMO_KEY}
AUTO_OPTIONS = {k: BoolOption('persistent_' + k, False, display_name='Enable ' + FEATURES[k][0])
                for k in FEATURES if k not in DAMAGE_HOLD and k not in MANUAL_ONLY}
AUTOMATION_OPTIONS = {k: BoolOption('persistent_automation_'+k, False, display_name='Enable '+label)
                      for k,label in (('vacuum','continuous Loot Vacuum'),('reload','session automatic reload'),('health','continuous flesh recovery assist'),('shield','continuous shield recharge assist'),('skill_cooldown','continuous action skill cooldown assist'),('skill_duration','continuous action skill duration assist'),('double_jump','second-jump upward velocity (experimental)'))}
DOUBLE_JUMP_RATE = SliderOption('double_jump_velocity_scale', 1., .5, 2., step=.1, is_integer=False, display_name='Double-jump upward velocity multiplier (experimental)')
RELOAD_EVENT = BoolOption('persistent_reload_event_window',False,display_name='Experimental reload request timing (instead of persistent weapon values)')
_reload_event = None
_reload_event_attempted = False
_reload_event_registered = False
_reload_event_status = 'Not armed'
SHIELD_POOL_BACKEND = BoolOption('native_shield_pool_backend',False,display_name='Use native shield pool recharge instead of equipped shield fields (experimental)')
SHIELD_POOL_KEYS = {'shield_idle_rate':'shield_regen_rate','shield_idle_delay':'shield_regen_delay'}
GUN_ACTOR_BACKEND = BoolOption('native_actor_gun_backend',False,display_name='Use native actor gun formulas instead of equipped gun fields (experimental)')
NATIVE_BACKEND_KEYS = {**SHIELD_POOL_KEYS, 'gun_actor':'damage'}
AUTO_SETTINGS = [auto_master, auto_consent, RELOAD_EVENT, SHIELD_POOL_BACKEND, GUN_ACTOR_BACKEND, *AUTO_OPTIONS.values(), *AUTOMATION_OPTIONS.values(), DOUBLE_JUMP_RATE]
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
NATIVE_RATE_OPTIONS = {k: SliderOption('native_rate_selection_'+k,1.,1.,5.,step=.1,is_integer=False,display_name=label)
                       for k,label in (('health','Native passive regeneration increment (x 0.001)'),('cooldown','Native cooldown speed multiplier'),('duration','Native skill duration multiplier'),('vaultregen','Vault Power recharge speed'),('vaultdelay','Vault Power idle delay speed'),('vaultdepleted','Vault Power depleted delay speed'),('shieldpassive','Native passive shield increment (x 0.001)'))}
NATIVE_RATE_OPTIONS['gear_luck'] = _PREVIEW_BY_KEY['overall_loot_luck']
NATIVE_RATE_OPTIONS['cash'] = _PREVIEW_BY_KEY['progress_money']
NATIVE_AUTO_OPTIONS = {'native_rate_'+k: BoolOption('persistent_native_rate_'+k,False,display_name=('Enable native gear luck (experimental)' if k=='gear_luck' else 'Enable earned pickup cash (experimental)' if k=='cash' else 'Enable native '+k+' rate (experimental)')) for k in NATIVE_RATE_OPTIONS}
NATIVE_RATE_OPTIONS.update({mode:_PREVIEW_BY_KEY[key] for mode,key in NATIVE_BACKEND_KEYS.items()})
NATIVE_AUTO_OPTIONS.update({'native_rate_'+mode:AUTO_OPTIONS[key] for mode,key in NATIVE_BACKEND_KEYS.items()})
ALL = PREVIEW + [o for k,o in NATIVE_AUTO_OPTIONS.items() if k.removeprefix('native_rate_') not in NATIVE_BACKEND_KEYS] + [o for k,o in NATIVE_RATE_OPTIONS.items() if k not in ('gear_luck','cash') and k not in NATIVE_BACKEND_KEYS] + [probe] + AUTO_SETTINGS + list(VACUUM_PREFS.values()) + [VACUUM_RADIUS_PREF, VACUUM_HIGH_PREF] + list(RECOVERY_RATES.values()) + list(SKILL_ADAPTIVE.values()) + list(SKILL_RATES.values()) + list(SKILL_FOLLOW.values()) + list(SKILL_NATIVE.values()) + [CROSSFIRE_GATE]
_auto_owned = False
_auto_blocked = ''
_auto_status = 'Not active; enable a feature.'
_auto_ground = None
_auto_api = None
_auto_next = 0.0
_slide_next = 0.0
_reload_handoff = None  # (scope IDs, deadline, next attempt) only after clean transition
_auto_edits = {}
_auto_edit_at = 0.0
_auto_last_diagnostic = ''
_session_reason = ''

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
    return round(bounded) if option.identifier in CAPACITY_KEYS or option.identifier == 'critical_chance' else round(bounded, 1)


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
    # Only a successfully committed slider edit can request a native replacement.
    for mode, option in NATIVE_RATE_OPTIONS.items():
        if option.identifier not in values:
            continue
        old=next((v for o,v in previous if o is option),option.value)
        if old==option.value:
            continue
        kind='native_rate_'+mode
        lease=_automation_leases.get(kind)
        if (lease is not None and not lease.fault and feature_enabled(NATIVE_AUTO_OPTIONS[kind])
                and (lease.phase=='active' and not lease.stop_requested or lease.phase=='verify' and lease.next_selection is not None)):
            lease.next_selection=normalize(option,option.value)


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
    if key=='damage' and GUN_ACTOR_BACKEND.value is True:
        return _automation_status.get('native_rate_gun_actor','Waiting for eligible native gun formulas')
    if key in SHIELD_KEYS and SHIELD_POOL_BACKEND.value is True:
        mode=next(m for m,k in SHIELD_POOL_KEYS.items() if k==key)
        return _automation_status.get('native_rate_'+mode,'Waiting for eligible shield pool')
    if key == 'reload' and RELOAD_EVENT.value is True:
        if AUTOMATION_OPTIONS['reload'].value is True or 'reload' in _automation_leases:
            return 'HOLD: turn off automatic reload for request timing'
        return _reload_event.last_result if _reload_event is not None else _reload_event_status
    if key == 'reload' and _controller is not None and _controller.reload_wait_reason:
        return 'Waiting: ' + _controller.reload_wait_reason
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


def feature_enabled(option):
    # A legacy master-off save must never silently rearm dormant flags.
    return auto_master.value is True and option.value is True


def feature_flags():
    return (*AUTO_OPTIONS.values(), *AUTOMATION_OPTIONS.values(), *(o for k,o in NATIVE_AUTO_OPTIONS.items() if k.removeprefix('native_rate_') not in NATIVE_BACKEND_KEYS))


def set_feature_enabled(option, value):
    """Single saved UI toggle, preserving the old internal engine gate.

    On first enable, discard only dormant enable flags, not slider preferences.
    A failed disable must disarm in memory even if persistence fails.
    """
    global _auto_blocked, _auto_next, _auto_ground, _ground_retry_at, _reload_handoff
    flags = feature_flags()
    if not any(option is f for f in flags) or type(value) is not bool:
        return
    if value and (health_active() or health_fault() or automation_fault()
                  or (_controller is not None and (_controller.fault or _controller.stop_pending is not None or (not _auto_owned and _controller.records) or (not auto_master.value and _controller.records)))
                  or (not auto_master.value and _automation_leases)):
        report_live('HOLD: restore isolated experiment before enabling gameplay')
        return
    was_on = auto_master.value is True
    edits = dict(_auto_edits)
    desired = {f.identifier: feature_enabled(f) for f in flags}
    desired[option.identifier] = value
    gate = any(desired.values())
    try:
        apply({**edits, **desired, auto_master.identifier: gate})
    except Exception:
        _auto_blocked = 'Settings save failed; Restore All before retrying'
        if not value:
            # A failed OFF cannot leave an enabled lane running this session.
            option.value = False
            auto_master.value = False
            stop_automation('feature disable save failed')
            _auto_ground = None
            _reload_handoff = None
            _auto_edits.clear()
        report_live('HOLD: settings save failed; check saved toggles before restart')
        return
    _auto_edits.clear()
    _auto_next = 0.0
    if option is AUTO_OPTIONS['reload'] or gate != was_on:
        _reload_handoff = None
    if option is AUTO_OPTIONS['walk_speed'] or gate != was_on:
        _auto_ground = None
        _ground_retry_at = 0.0
    lanes = {**AUTOMATION_OPTIONS, **NATIVE_AUTO_OPTIONS}
    for kind, flag in lanes.items():
        if flag is option:
            stop_automation_lane(kind, 'gameplay toggle changed')
            if value and not automation_fault() and kind not in _automation_leases:
                _automation_attempted.discard(kind)
                _automation_status[kind] = 'Waiting for eligible session'
    if not was_on and gate:
        _auto_blocked = ('Capacity restore waiting: remove excess items' if _controller is not None and any(r.get('overfull_warning') for r in _controller.records.values()) else '')
        _automation_attempted.clear()
        cancel_activation('gameplay feature enabled')
        ensure_monitor()
    if not gate:
        stop_automation('all gameplay toggles off')
        _auto_ground = None
        _reload_handoff = None


def restore_all_ui():
    """One global action: disable all saved flags, keep selected values, restore safely."""
    global _auto_blocked, _auto_ground, _reload_handoff, _status
    flags = feature_flags()
    saved = True
    try:
        apply({**_auto_edits, **{f.identifier: False for f in flags}, auto_master.identifier: False})
    except Exception:
        saved = False
        for f in flags:
            f.value = False
        auto_master.value = False
        report_live('HOLD: all toggles off in memory; save failed, check settings before restarting')
    _auto_edits.clear()
    _auto_ground = None
    _reload_handoff = None
    _auto_blocked = 'Restore All requested'
    _pending.clear()
    request_stop('F8 restore all', immediate=True)
    _status = ('All toggles OFF; verify restoration before leaving the session.' if saved else 'SAVE FAILED: toggles OFF in memory; check settings before restarting.')


def draw_feature_toggle(ui, option):
    changed, chosen = ui.checkbox(option.display_name+'##'+option.identifier, feature_enabled(option))
    if changed:
        set_feature_enabled(option, chosen)


def native_rate_selection(ui, mode):
    option=NATIVE_RATE_OPTIONS[mode]
    edited,value=ui.slider_float(option.display_name+'##'+option.identifier,float(displayed_selection(option)),1.,5.,'%.1fx')
    if edited:
        queue_auto_edit(option,value)
    flag=NATIVE_AUTO_OPTIONS['native_rate_'+mode]
    draw_feature_toggle(ui,flag)
    ui.text(mode+' native rate: '+(_automation_status.get('native_rate_'+mode,'Waiting') if feature_enabled(flag) else 'Off'))
    return displayed_selection(option)


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
    ui.text_wrapped('Enable individual features; sliders save automatically. Isolated experimental tests require all gameplay toggles off.')
    ui.text_wrapped('Restore All BEFORE travel, character changes, or network changes. Offline Local Only only.')
    global _offline_confirmed
    changed_auto, selected_auto = ui.checkbox(auto_consent.display_name+'##'+auto_consent.identifier, auto_consent.value is True)
    if changed_auto:
        set_auto_setting(auto_consent, selected_auto)
        if not selected_auto:
            # Save failure must not leave offline permission granted in memory.
            auto_consent.value = False
            request_stop('offline confirmation withdrawn', immediate=True)
        _offline_confirmed = auto_consent.value is True
    elif auto_consent.value is True and not auto_master.value:
        # Same explicit saved offline consent used by the existing automatic path.
        # A manual experiment still requires its separate test button.
        _offline_confirmed = True
    if auto_master.value is True:
        ui.text_wrapped('Gameplay: ' + (_auto_blocked or _auto_status))
        if auto_consent.value is not True:
            ui.text_wrapped('HOLD: confirm Offline Local Only above.')
    if ui.button('Restore All'):
        restore_all_ui()
        return
    compact = False if _compact_view is None else _compact_view
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
        ui.text_wrapped('Active fields (gameplay unverified): ' + (', '.join(k + ' +' + str(r['selection']-1) + ' pp' if k == 'critical_chance' else k + ' ' + str(r.get('selection', '?')) + (' slots' if k in CAPACITY_KEYS else 'x') for k, r in _controller.records.items()) or 'None / vanilla'))
        if any(r.get('overfull_warning') for r in _controller.records.values()):
            ui.text_wrapped('CAPACITY RESTORE HOLD: remove excess items in this offline session, then restore. Do not travel, buy SDUs or exit while over capacity.')
    if any(l.record is not None for l in _automation_leases.values()) or (RELOAD_EVENT.value is True and AUTO_OPTIONS['reload'].value is True and auto_allowed()):
        ui.text_wrapped('Automation armed (native outcomes unverified).')
    if _native_overtime_used:
        ui.text_wrapped('Native timed recovery test attempted: stay offline, do not travel, and exit game after the test.')
    if health_active():
        ui.text_wrapped('Native attribute trial active or restoring; wait for verified baseline before changing character, skill or session.' if hasattr(_health_pulse,'binding') and hasattr(_health_pulse,'phase') else ('Continuous vacuum active until stopped in this session. Completed relocations are not reversed.' if getattr(_health_pulse,'continuous',False) and hasattr(_health_pulse,'categories') else 'Session repair kit armed; maximum three witnessed requests. Completed native actions are not reversed.' if getattr(_health_pulse,'continuous',False) and hasattr(_health_pulse,'cycle') else 'Experimental action armed; maximum 30 seconds. Completed native actions are not reversed.'))
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
        ui.text_wrapped('Damage slider uses equipped ordinary gun fire behavior by default, or the explicitly selected actor formula backend. Separate isolated native gun test uses the same selection (formula-witnessed actor entry first, removable weapon attribute fallback). Elemental and incoming modifiers are separate; hit effects unverified.')
    if _category == 1 and not compact:
        ui.text_wrapped('Pickup cash: continuous formula-witnessed toggle or isolated 30-second trial. Eridium: isolated trial only. XP experiment failed; XP controls are preview only. Use a backup character; earned rewards are not reversed.')
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
    if _category == 4:
        option = AUTOMATION_OPTIONS['double_jump']
        draw_feature_toggle(ui,option)
        edited, selected = ui.slider_float(DOUBLE_JUMP_RATE.display_name+'##'+DOUBLE_JUMP_RATE.identifier,float(displayed_selection(DOUBLE_JUMP_RATE)),.5,2.,'%.1fx')
        if edited: queue_auto_edit(DOUBLE_JUMP_RATE,selected)
        ui.text('double_jump: '+(_automation_status.get('double_jump','Waiting') if feature_enabled(option) else 'Off'))
        if 'Vault Power' in visible_action_panels(ui,4,('Movement','Vault Power')):
            ui.text_wrapped('Vault Power native recharge (experimental): individual persistent toggles; 1x restores. Higher delay speed shortens delay. No refill or cost changes.')
            for mode in ('vaultregen','vaultdelay','vaultdepleted'):
                native_rate_selection(ui,mode)
        ui.text_wrapped('Experimental second-jump velocity only; actual height unverified. Land before use; toggle lane to rearm after changing scale. First jump and shared goals unchanged.')
    if _category == 5:
        panels = visible_action_panels(ui, 5, ('Loot Vacuum', 'Automatic reload'))
        ui.text_wrapped('Automation: movement, elemental, rarity weights and selected recovery fields compatible. Vacuum settings save automatically and update the active lease. Reload waits for a supported loaded idle gun and reserve, including after weapon/mode swaps. Empty guns need a normal reload first; unsupported guns stop the lane. Toggle a stopped lane off/on to rearm.')
        for kind, option in AUTOMATION_OPTIONS.items():
            if kind not in ('vacuum','reload') or ('Loot Vacuum' if kind == 'vacuum' else 'Automatic reload') not in panels: continue
            draw_feature_toggle(ui,option)
            ui.text(kind+': '+(_automation_status.get(kind, 'Waiting') if feature_enabled(option) else 'Off'))
        if 'Loot Vacuum' in panels:
            ui.text_wrapped('Experimental Loot Vacuum: select categories, then arm a short test or continuous session. Gear moves into separate nearby positions for manual pickup; full placement area pauses gear only; collected gear can free reserved positions. Health pickups require missing living flesh health. Completed moves are not reversed.')
            if not health_active():
                for kind in _vacuum_filters:
                    edited, selected = ui.checkbox('Vacuum '+kind+'##vacuum_'+kind, _vacuum_filters[kind])
                    if edited:
                        _vacuum_filters[kind] = selected is True
                        queue_auto_edit(VACUUM_PREFS[kind], selected is True)
                edited, selected = ui.checkbox('Gear: legendary/pearlescent beams only##vacuum_high_gear', _vacuum_high_gear)
                if edited:
                    _vacuum_high_gear = selected is True
                    queue_auto_edit(VACUUM_HIGH_PREF, _vacuum_high_gear)
                edited, radius = ui.slider_float('Pickup radius##vacuum_radius', _vacuum_radius, 5., 100., '%.0f m')
                if edited and type(radius) in (int,float) and math.isfinite(radius):
                    _vacuum_radius = max(5., min(100., radius))
                    queue_auto_edit(VACUUM_RADIUS_PREF, _vacuum_radius)
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
        ui.text_wrapped('Continuous recovery assists: native refill pulses, not native regen-rate or recharge-delay modifiers. Stop on lost scope or ineffective refill; toggle to rearm. Already recovered health is not reversed.')
        for kind in ('health','shield','skill_cooldown','skill_duration'):
            if ('Recovery' if kind in ('health','shield') else 'Action skills') not in panels: continue
            option = AUTOMATION_OPTIONS[kind]
            draw_feature_toggle(ui,option)
            ui.text(kind+': '+(_automation_status.get(kind, 'Waiting') if feature_enabled(option) else 'Off'))
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
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Arm automatic repair kit (35% health; one request)'):
                activate_feature('repair_assist', 1.0)
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Arm session automatic repair kit (experimental)'):
                activate_feature('repair_assist_continuous', 1.0)
            ui.text_wrapped('Automatic repair kit: existing charges only; one-shot or session-only (maximum 3 requests). Session mode requires observed use, charge spent, idle, charge restored and health recovered before a new low-health episode. No retry; native acceptance unverified.')
            ui.text_wrapped('Experimental health recovery: native flesh-only refill pulse, 30-second maximum, not a native regen-rate modifier. No FFYL. Actual game compatibility unverified.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Start experimental health recovery (30 sec)'):
                activate_feature('health_pulse', 1.0)
            ui.text_wrapped('Native timed flesh experiment: one small engine-timed refill per game process. Timer cancellation/expiry unverified; stay offline, do not travel, and exit game after this test.')
            if not _native_overtime_used and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native timed flesh recovery (2 sec)'):
                activate_feature('health_overtime', 1.0)
            ui.text_wrapped('Native regeneration start/stop test: uses a constant-rate initializer and existing exact flesh or energy-shield tags; shield test requires two slow rising charge samples. Rate units and stop/expiry are unverified; share one timed attempt per process. Exit after testing.')
            if not _native_overtime_used and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native regeneration start/stop (2 sec)'):
                activate_feature('health_regen_native', 1.0)
            if not _native_overtime_used and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native shield regeneration (2 sec)'):
                activate_feature('shield_regen_native', 1.0)
            ui.text_wrapped('Native passive regeneration rate: small additive native rate, not a refill. Manual ten-second trial or separate toggle; restore before travel. Rate units and actual healing unverified. The missing-health test uses the same increment slider, but targets a separate native rate.')
            rate=native_rate_selection(ui,'health')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native passive health rate (10 sec)'):
                activate_feature('native_rate_health',rate)
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native missing-health regeneration (10 sec)'):
                activate_feature('native_rate_missing_health',rate)
            changed_backend,chosen_backend=ui.checkbox(SHIELD_POOL_BACKEND.display_name+'##'+SHIELD_POOL_BACKEND.identifier,SHIELD_POOL_BACKEND.value is True)
            if changed_backend:set_auto_setting(SHIELD_POOL_BACKEND,chosen_backend)
            ui.text_wrapped('Native shield pool backend uses the same saved recharge rate and delay sliders and toggles. Turn both off and restore before switching backend. Keep the original shield equipped.')
            ui.text_wrapped('Native shield pool recharge tests: use the existing equipped shield rate/delay speed selections, restore other modifiers first. Separate 10-second removable rate or inverse-delay experiment, not a refill. Keep the original shield equipped. Gameplay unverified.')
            for mode,key in (('shield_idle_rate','shield_regen_rate'),('shield_idle_delay','shield_regen_delay')):
                selected=displayed_selection(_PREVIEW_BY_KEY[key])
                if selected!=1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native shield pool '+mode.removeprefix('shield_idle_')+' ('+str(selected)+'x, 10 sec)'):
                    activate_feature('native_rate_'+mode,selected)
            native_rate_selection(ui,'shieldpassive')
            ui.text_wrapped('Passive shield rate is separate from idle recharge and refill; toggle ON with a selection above 1x. Actual rate units unverified.')
            ui.text_wrapped('Experimental energy shield assist: adds a small pulse only after two rising charge samples; not a native recharge delay/rate multiplier.')
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Start experimental shield assist (30 sec)'):
                activate_feature('shield_pulse', 1.0)
        if 'Action skills' in panels:
            ui.text_wrapped('Action skill assist: experimental bounded native refill, not a multiplier; excludes charge and auxiliary skills.')
            ui.text_wrapped('Native resource rates: selectable cooldown regeneration speed or inverse duration consumption (above 1x). Manual 10-second trials or individual toggle; choose native OR matching refill assist. Saved rate edits restore and verify the old modifier before applying the new rate; unsupported changes stop the lane. Restore before skill changes. Named Contagion main cooldown also has a distinct native resource route; Executable auxiliary is read-only. Exact ordinary ForgeSkill main cooldown is supported experimentally.')
            for mode in ('cooldown','duration'):
                rate=native_rate_selection(ui,mode)
                if rate>1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native skill '+mode+' rate (10 sec)'):
                    activate_feature('native_rate_'+mode,rate)
                if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Start experimental skill '+mode+' assist (30 sec)'):
                    activate_feature('skill_'+mode, 1.0)
    if _category == 8:
        ui.text_wrapped('Change the Open Custom Menu key in the SDK console Keybinds section. Default: F8.')
        ui.text('Current hotkey: ' + str(open_key.key or 'Unbound'))
    options = focused_options(ui, _category, compact, [o for o in options if o.identifier not in ('auto_reload','auto_loot')])
    for o in options:
        value = displayed_selection(o)
        label = o.display_name + '##' + o.identifier
        if (o.identifier not in FEATURES or o.identifier in DAMAGE_HOLD) and o is not probe and o.identifier not in REWARD_KEYS and o.identifier!='overall_loot_luck':
            ui.text_wrapped(o.display_name + ' — HOLD / preview only')
        if isinstance(o, BoolOption):
            edited, value = ui.checkbox(label, value)
        elif o.identifier == 'critical_chance':
            edited, bonus = ui.slider_float(label, float(value)-1., 0., 20., '+%.0f pp')
            value = round(bonus)+1. if edited else value
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
            queue_auto_edit(o, value)
        if o.identifier in AUTO_OPTIONS:
            draw_feature_toggle(ui,AUTO_OPTIONS[o.identifier])
            if o.identifier == 'reload':
                edited_event, event = ui.checkbox(RELOAD_EVENT.display_name+'##'+RELOAD_EVENT.identifier, RELOAD_EVENT.value is True)
                if edited_event: set_auto_setting(RELOAD_EVENT,event)
                if RELOAD_EVENT.value is True: ui.text_wrapped('Experimental reload request timing; automatic reload lane must be off.')
            ui.text(persistent_feature_status(o.identifier) if feature_enabled(AUTO_OPTIONS[o.identifier]) else ('Off / restoring' if _controller is not None and o.identifier in _controller.records else 'Off'))
        # Keep manual experiments next to their selection, not below all sliders.
        selected = o
        key = o.identifier
        if key in REWARD_KEYS:
            if key=='progress_money':
                flag=NATIVE_AUTO_OPTIONS['native_rate_cash']
                draw_feature_toggle(ui,flag)
                ui.text(_automation_status.get('native_rate_cash','Waiting for eligible session') if feature_enabled(flag) else 'Off / restoring' if 'native_rate_cash' in _automation_leases else 'Off')
                ui.text_wrapped('Continuous earned pickup cash requires native formula agreement; native actor gun backend must be OFF. Editing the multiplier restores first; toggle off/on to rearm. Actual awards unverified.')
            if key == FAILED_XP_KEY:
                ui.text_wrapped('Previous XP experiment did not increase earned XP; disabled pending a different mechanism.')
                continue
            if not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test earned '+selected.display_name+' (30 sec)##reward_'+key):
                activate_feature(key, displayed_selection(selected))
            continue
        if key=='overall_loot_luck':
            ui.text_wrapped('Experimental gear luck category only; not guaranteed drop rate or every luck category.')
            flag=NATIVE_AUTO_OPTIONS['native_rate_gear_luck']
            draw_feature_toggle(ui,flag)
            ui.text(_automation_status.get('native_rate_gear_luck','Waiting for eligible session') if feature_enabled(flag) else 'Off / restoring' if 'native_rate_gear_luck' in _automation_leases else 'Off')
            if displayed_selection(o)>1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native gear luck (30 sec)'):
                activate_feature('native_rate_gear_luck',displayed_selection(o))
            continue
        if key not in FEATURES or key in DAMAGE_HOLD:
            continue
        name = FEATURES[key][0]
        if key == 'reload' and displayed_selection(o)!=1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test removable native reload speed (30 sec)'):
            activate_feature(RELOAD_TRIAL_KEY,displayed_selection(o))
        if key == 'fire_rate' and displayed_selection(o)!=1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test removable native fire rate (30 sec)'):
            activate_feature(FIRE_RATE_TRIAL_KEY,displayed_selection(o))
        if key == 'damage':
            changed_backend,chosen_backend=ui.checkbox(GUN_ACTOR_BACKEND.display_name+'##'+GUN_ACTOR_BACKEND.identifier,GUN_ACTOR_BACKEND.value is True)
            if changed_backend:set_auto_setting(GUN_ACTOR_BACKEND,chosen_backend)
            ui.text_wrapped('Actor backend uses the existing Damage slider and toggle; turn damage OFF and restore before switching. All five gun-family formulas and the additive expression must agree. Native cash must be OFF. Linked companion effects possible. Actual hits unverified.')
            ui.text_wrapped('Experimental gun damage; equipped field backend by default. Apply while idle; 1x restores. Actual hit effects unverified.')
            if displayed_selection(o)!=1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native gun damage (30 sec)'):
                activate_feature(GUN_TRIAL_KEY,displayed_selection(o))
            if displayed_selection(o)!=1. and not health_fault() and not health_active() and auto_master.value is not True and ui.button('Test native melee attack damage (30 sec)'):
                activate_feature(MELEE_TRIAL_KEY,displayed_selection(o))
            ui.text_wrapped('Melee test uses the same damage selection, but requires a separate local attack attribute and matching native expression. Actual melee damage unverified.')
        if key in ('fire_damage', 'shock_damage', 'corrosive_damage', 'cryo_damage', 'radiation_damage'):
            ui.text_wrapped('Experimental elemental modifier; actual hit damage unverified. 1x restores.')
        if key == 'gravity':
            ui.text_wrapped('EXPERIMENTAL: lower gravity can increase jump height and airborne time. Not a direct jump-height multiplier. Test on a backup character; restore while grounded.')
        if key == 'sprint':
            ui.text_wrapped('Experimental sprint-only floor. Restore combined ground speed first. Manual activation only; not an exact speed multiplier.')
            if auto_master.value is True:
                ui.text('Restore All before using this isolated sprint test.')
                continue
        if key in CAPACITY_KEYS:
            ui.text_wrapped('EXPERIMENTAL: absolute slots, 1 restores original. Use a backup character; do not fill beyond original capacity. Restore before SDU purchase, travel or exit.')
        if key == 'overshield_duration':
            ui.text_wrapped('Existing positive duration and base required. Does not grant overshield or passively heal. Native timing unverified.')
        if key == 'lifesteal_fraction':
            ui.text_wrapped('Requires existing positive life-steal and unchanged rate/cap. Not passive healing. Restore the life-steal rate control first.')
        if key == 'critical_chance':
            ui.text_wrapped('Adds up to 20 percentage points to the local default critical chance field, capped at 75% total field value. Zero bonus restores. Actual chance unverified; no forced crits.')
        if key == 'melee_cooldown':
            ui.text_wrapped('Melee cooldown only; no attack, animation speed or damage change. Activate and restore between attacks. Restore other modifiers first.')
        if key == 'splash_radius':
            ui.text_wrapped('Splash radius only; may change area coverage, not damage magnitude. Restore other modifiers first. Actual effect unverified.')
        if key == 'splash_damage':
            ui.text_wrapped('Splash damage only; not radius size, direct-hit damage or a guaranteed multiplier. Restore other modifiers first.')
        if key in MANUAL_ONLY - {'sprint'}:
            ui.text_wrapped('Experimental local instance control; gameplay effect unverified. Restore before switching gear or travel.' if key == 'critical_chance' else 'Experimental local instance control; gameplay effect unverified. 1x restores. Restore before switching gear or travel.')
            if auto_master.value is True:
                ui.text('Restore All before using this isolated experiment.')
                continue
        if key in ('damage_taken', 'repair_cooldown', 'fire_damage', 'shock_damage', 'corrosive_damage', 'cryo_damage', 'radiation_damage'):
            ui.text_wrapped('EXPERIMENTAL: gameplay effect unverified. Test separately on a backup character.')
        if key in ('repair_cooldown', 'damage_taken'):
            ui.text_wrapped('1x restores baseline. ' + ('Lower duration is faster.' if key == 'repair_cooldown' else 'Lower means less damage taken.'))
        if key in AUTO_OPTIONS:
            continue
        if not (_controller is not None and _controller.fault) and ui.button('Activate / Update ' + name + '##activate_' + key):
            activate_feature(key, displayed_selection(selected))
    ui.separator()
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
             'Read-only check. Native reward trials are independent; metadata is not proof of live behavior.']
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
    lines.append('No modifier add/remove or reward-grant calls made. Earned reward effects remain unverified.')
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
    global _session_reason
    _session_reason = ''
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
    if type(players) is not int:
        _session_reason = 'player count unavailable'
    elif players != 1:
        _session_reason = 'player count is '+str(players)+' (requires exactly one)'
    elif type(standalone) is not bool:
        _session_reason = 'standalone query unavailable'
    elif pawn is None or str(pawn.Class.Name) != 'OakCharacter':
        _session_reason = 'local OakCharacter not loaded'
    elif getattr(pc, 'PlayerState', None) is None:
        _session_reason = 'local PlayerState unavailable'
    return pc, pawn, state, not _session_reason


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


def begin_native_regen(mode="flesh"):
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
    _health_pulse=NativeRegen(timed_context,u.WeakPointer,u.FGameDataHandle,api,time.monotonic,threading.get_ident,report_live,claim_native_overtime,sdk.make_struct,init_type,tag_type,u.FGbxDefPtr,cleanup_context,mode=mode)
    _health_pulse.begin()


def begin_blackboard_reward(key, selection):
    global _health_pulse
    if key == FAILED_XP_KEY:
        raise ValueError(FAILED_XP_REASON)
    from .blackboard_rewards import Binding, Trial, GunFormulaBinding, GunFormulaTrial, CashFormulaBinding, CashFormulaTrial, CashPrimaryBinding, CashPrimaryTrial, choose_cash_trial, MeleeBinding, MeleeTrial, SPECS, DEF
    if key not in REWARD_KEYS | {MELEE_TRIAL_KEY,GUN_TRIAL_KEY,RELOAD_TRIAL_KEY,FIRE_RATE_TRIAL_KEY} or health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)) or _automation_leases:
        raise ValueError('restore existing features before isolated reward trial')
    sdk=sys.modules['unrealsdk'];u=sdk.unreal
    defs=[d for d in sdk.find_all('ScriptStruct',exact=False) if d._path_name()==DEF]
    if len(defs)!=1 and key not in (GUN_TRIAL_KEY,RELOAD_TRIAL_KEY,FIRE_RATE_TRIAL_KEY):raise ValueError('native attribute definition struct unavailable')
    fs=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS]
    session=bound_session(sdk)
    def permitted():
        hooks=sdk.hooks
        return (mod.is_enabled is True and _offline_confirmed and auto_master.value is not True and not _auto_owned
                and not _automation_leases and not conflicting_mods() and _monitor_registered
                and _monitor_thread==threading.get_ident()
                and hooks.has_hook(_MONITOR_PATH,hooks.Type.POST_UNCONDITIONAL,_MONITOR_ID) is True)
    args=(lambda:current_session(session),u.WeakPointer,time.monotonic,threading.get_ident,report_live,permitted)
    if key in (RELOAD_TRIAL_KEY,FIRE_RATE_TRIAL_KEY):
        from .native_resource_rates import NativeBinding, SPECS as RATE_SPECS
        from .native_weapon_damage import make_reload_trial, make_fire_rate_trial
        native=NativeBinding([f for f in sdk.find_all('Function',exact=False) if str(f.Name) in RATE_SPECS],loot_bound,u.FGbxDefPtr,u.WrappedStruct)
        _health_pulse=(make_reload_trial if key==RELOAD_TRIAL_KEY else make_fire_rate_trial)(native,*args,selection)
        _health_pulse.begin()
        return
    if key==MELEE_TRIAL_KEY:
        binding=MeleeBinding(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct)
        _health_pulse=MeleeTrial(key,selection,binding,*args)
        _health_pulse.begin()
        return
    if key==GUN_TRIAL_KEY:
        from .native_resource_rates import NativeBinding, SPECS as RATE_SPECS
        from .native_weapon_damage import make_trial, choose_gun_trial
        def primary():
            if len(defs)!=1:raise ValueError('native actor attribute definition unavailable')
            binding=GunFormulaBinding(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct)
            return GunFormulaTrial(key,selection,binding,*args)
        def fallback():
            native=NativeBinding([f for f in sdk.find_all('Function',exact=False) if str(f.Name) in RATE_SPECS],loot_bound,u.FGbxDefPtr,u.WrappedStruct)
            return make_trial(native,*args,selection)
        _health_pulse=choose_gun_trial(primary,fallback,report_live)
        return
    binding=(CashPrimaryBinding if key=='progress_money' else Binding)(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct)
    _health_pulse=(CashPrimaryTrial if key=='progress_money' else Trial)(key,selection,binding,*args)
    if key=='progress_money':
        def alternative():
            native=CashFormulaBinding(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct)
            return CashFormulaTrial(key,selection,native,*args)
        _health_pulse=choose_cash_trial(_health_pulse,alternative)
    else:_health_pulse.begin()


def make_native_resource_rate(mode,selection,*,persistent=False):
    from .native_resource_rates import (NativeBinding, NativeRateTrial, SPECS as RATE_SPECS,
                                        TARGETS, RESOURCE_MODES, SHIELD_MODES, SHIELD_PASSIVE_MODE, LUCK_MODE, WEAPON_MODE, RELOAD_MODE, FIRE_RATE_MODE, CONTAGION_MODE, FORGE_MODE, FORGE_RESOURCE, bind_health_readers, make_local_resolver, original_pool_identity)
    from .skill_pulse import SkillPulse, bind, SPECS as POOL_SPECS, ACTION_NAMES, bind_action_percent, bind_direct_cooldown
    if mode not in TARGETS or mode in (WEAPON_MODE,RELOAD_MODE,FIRE_RATE_MODE,CONTAGION_MODE,FORGE_MODE) or health_fault() or health_active() or (not persistent and (_automation_leases or (_controller is not None and (_controller.records or _controller.fault)))):
        raise ValueError('restore active features before native resource-rate trial')
    sdk=sys.modules['unrealsdk'];u=sdk.unreal
    names=set(RATE_SPECS)|set(POOL_SPECS)|set(ACTION_NAMES)|{'GetResourcePoolValue','GetResourcePoolPercent','GetShield'}
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in names]
    binding=NativeBinding(functions,loot_bound,u.FGbxDefPtr,u.WrappedStruct)
    session=bound_session(sdk)
    def context():return current_session(session)
    def permitted():
        hooks=sdk.hooks
        if persistent:
            kind='native_rate_'+mode
            return (_monitor_thread==threading.get_ident() and native_rate_allowed(kind,trial.selection) and automation_permitted())
        return (mod.is_enabled is True and _offline_confirmed and auto_master.value is not True and not _auto_owned
                and not _automation_leases and not conflicting_mods() and _monitor_registered
                and _monitor_thread==threading.get_ident()
                and hooks.has_hook(_MONITOR_PATH,hooks.Type.POST_UNCONDITIONAL,_MONITOR_ID) is True)
    readers=None;skill=None
    shield_getter=None
    if mode=='missing_health' and persistent:raise ValueError('native rate trial is manual only')
    if mode in RESOURCE_MODES:
        readers=bind_health_readers(functions,loot_bound)
        if mode in SHIELD_MODES:
            from .shield_rates import bind as bind_shield
            shield_getter=bind_shield(functions,loot_bound)
    elif mode!=LUCK_MODE:
        ref,api=bind(functions,loot_bound,read_only=True)
        adaptive=bind_action_percent(functions,loot_bound,mode,ref)
        direct=None
        if mode=='cooldown':
            try:direct=bind_direct_cooldown(functions,loot_bound,read_only=True)
            except (ValueError,AttributeError,TypeError):pass
        skill=SkillPulse(context,u.WeakPointer,u.FGameDataHandle,u.WrappedInlineStruct,u.WrappedStruct,ref,api,
                         lambda:sdk.find_all('GbxSkill',exact=True),time.monotonic,threading.get_ident,report_live,mode,
                         adaptive_api=adaptive,read_only=True,direct_api=direct,soft_identifier=getattr(getattr(u,'ZSoftObjectProperty',None),'_get_identifier_from_array',None))
    actual_mode=mode
    if mode=='cooldown' and direct is not None:
        # Resolve layout read-only before choosing the native definition.
        # No fallback after dispatch, and no broad shared selector on named layouts.
        _,_,_,resources,_,named=skill.resolve(initial=True,refresh=True)
        if resources[0]._name.casefold()==FORGE_RESOURCE.casefold():
            actual_mode=FORGE_MODE
        elif named is not None:actual_mode=CONTAGION_MODE
    resolve=make_local_resolver(actual_mode,binding,context,u.FGameDataHandle,readers,skill,shield_getter)
    trial=NativeRateTrial(actual_mode,binding,resolve,u.WeakPointer,time.monotonic,threading.get_ident,report_live,permitted,lambda key:original_pool_identity(actual_mode,key),selection=selection,continuous=persistent)
    return trial


def begin_native_resource_rate(mode,selection):
    global _health_pulse
    _health_pulse=make_native_resource_rate(mode,selection)
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
    from .loot_vacuum import Vacuum, lazy_ammo_reader, flesh_need_reader
    if health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore active modifiers before isolated vacuum')
    sdk = sys.modules['unrealsdk']
    session = bound_session(sdk)
    if len(selection) not in (2,3):raise ValueError('invalid vacuum selection')
    categories, radius = selection[:2]
    high_gear_only = selection[2] if len(selection)==3 else False
    _health_pulse = Vacuum(lambda: current_session(session), sdk.unreal.WeakPointer, sdk.find_all,
                          sdk.make_struct, time.monotonic, threading.get_ident, report_live, categories, radius, continuous=continuous,high_gear_only=high_gear_only,ammo_reader=lazy_ammo_reader(sdk,loot_bound),health_reader=flesh_need_reader(sdk))
    _health_pulse.begin()


def begin_repair_assist(continuous=False):
    global _health_pulse
    from .repair_assist import RepairAssist, bind
    if health_fault() or health_active() or (_controller is not None and (_controller.records or _controller.fault)):
        raise ValueError('restore existing features before isolated repair kit experiment')
    sdk=sys.modules['unrealsdk']
    functions=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in ('GetRepairKit','StartUsingRepairKit')]
    getter,fn=bind(functions,loot_bound);session=bound_session(sdk)
    _health_pulse=RepairAssist(lambda:current_session(session),sdk.unreal.WeakPointer,sdk.unreal.FGameDataHandle,getter,fn,time.monotonic,threading.get_ident,report_live,lambda:_backend is None,continuous=continuous)
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
    global _offline_confirmed, _auto_blocked, _auto_ground, _reload_handoff
    _reload_handoff = None
    _offline_confirmed = False
    stop_health_pulse(reason)
    stop_automation(reason)
    if _auto_owned or auto_master.value is True:
        _auto_blocked = reason + '; Restore All, then enable the feature again'
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
_ground_retry_at = 0.0

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
    global _ground_anim_id, _ground_seen, _activation_request, _controller, _auto_ground, _auto_blocked, _ground_retry_at
    if _automation_busy or (_reload_event is not None and _reload_event.root is not None):
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
        if automation_fault():
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
                # No write occurred. Let the camera queue a fresh local animation.
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
                if 'walk_speed' not in _controller.records:
                    # A missing/ambiguous component before any dispatch is not
                    # a failed transaction. Back off this lane only. Activate
                    # still performs a completely fresh capture/write check.
                    try:
                        _controller.capture('walk_speed')
                    except (AttributeError, TypeError, ValueError) as exc:
                        _ground_retry_at = time.monotonic() + 1.0
                        report_live('HOLD ground admission; retrying: ' + str(exc)[:100])
                        return
                if not _controller.activate('walk_speed', request[1], ground_sprinting=stance):
                    _auto_blocked = 'Ground activation failed; Restore All, then enable the feature again'
                return
            _activation_request = None
            if _controller is None or not _controller.records:
                _controller = Controller(context, sdk.unreal.WeakPointer, report_live, threading.get_ident, shield_binding=shield_binding)
            _controller.activate(request[0], request[1], ground_sprinting=stance)
        elif active:
            _controller.ground_frame(stance, observed=(pc, pawn, state, eligible))
            if _auto_owned and 'walk_speed' not in _controller.records:
                _auto_blocked = 'Ground frame stopped; Restore All, then enable the feature again'
                _auto_ground = None
    except Exception as exc:
        if queued:
            if automatic:
                _auto_ground = None
                _auto_blocked = 'Ground callback failed; Restore All, then enable the feature again'
            else:
                cancel_activation('ground callback failed: ' + str(exc)[:100])
        if active:
            request_stop('ground callback failed: ' + str(exc)[:100])


def monitor_tick(*_):
    global _monitor_thread, _monitor_seen, _offline_confirmed, _activation_request
    global _monitor_registered, _monitor_error
    if _reload_event is not None and _reload_event.root is not None:
        try: _reload_event.watchdog()
        except Exception as exc:
            _reload_event.fault=True
            report_live('FAULT: reload event watchdog failed: '+str(exc)[:100]+'; exit game')
        if _reload_event.root is not None:
            return
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
        if not _reload_event_attempted and RELOAD_EVENT.value is True and AUTO_OPTIONS['reload'].value is True and auto_allowed():
            ensure_reload_event()
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
    if key == FAILED_XP_KEY:
        report_live('HOLD: ' + FAILED_XP_REASON)
        return
    try:
        if health_fault() or automation_fault() or (_controller is not None and _controller.fault):
            raise ValueError('fault latched; exit game')
        if health_active():
            raise ValueError('stop isolated health recovery first')
        if key in REWARD_KEYS | {MELEE_TRIAL_KEY,GUN_TRIAL_KEY,RELOAD_TRIAL_KEY,FIRE_RATE_TRIAL_KEY,'native_rate_gear_luck','native_rate_health','native_rate_cooldown','native_rate_duration','native_rate_missing_health','native_rate_shield_idle_rate','native_rate_shield_idle_delay','health_pulse','health_overtime','health_regen_native','shield_regen_native','shield_pulse','skill_cooldown','skill_duration','repair_assist','repair_assist_continuous','reload_assist','reload_continuous','loot_vacuum','loot_vacuum_continuous'} and _controller is not None and _controller.records:
            raise ValueError('restore active modifiers before isolated health recovery')
        if not mod.is_enabled:
            raise ValueError('mod disabled')
        if auto_master.value is True or _auto_owned or _automation_leases:
            raise ValueError('Restore All and finish restoration before manual activation')
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
        if not report_live('QUEUED ' + key + ': ' + (repr(selection-1) + ' pp; ' if key == 'critical_chance' else repr(selection) + (' slots; ' if key in CAPACITY_KEYS else 'x; ')) + monitor_status()):
            return
        _activation_request = (key, selection, threading.get_ident(), time.monotonic() + 3.0)
    except Exception as exc:
        report_live('HOLD: ' + str(exc)[:160])
        if _controller is not None and _controller.records and _activation_request is None:
            request_stop('activation preflight failed', immediate=False)


def execute_activation(key, selection):
    global _controller
    # Called exclusively by monitor_tick after the explicit queued F8 action.
    if key == FAILED_XP_KEY:
        raise ValueError(FAILED_XP_REASON)
    if key in REWARD_KEYS | {MELEE_TRIAL_KEY,GUN_TRIAL_KEY,RELOAD_TRIAL_KEY,FIRE_RATE_TRIAL_KEY}:
        begin_blackboard_reward(key, selection)
        return
    if key in ('loot_vacuum','loot_vacuum_continuous'):
        begin_loot_vacuum(selection,continuous=key=='loot_vacuum_continuous')
        return
    if key in ('repair_assist','repair_assist_continuous'):
        if selection != 1.0:raise ValueError('invalid repair kit arm selection')
        begin_repair_assist(continuous=key=='repair_assist_continuous')
        return
    if key in ('reload_assist','reload_continuous'):
        begin_reload_assist(key=='reload_continuous')
        return
    if key in ('skill_cooldown','skill_duration'):
        begin_skill_pulse(key.split('_',1)[1])
        return
    if key in ('native_rate_gear_luck','native_rate_health','native_rate_cooldown','native_rate_duration','native_rate_missing_health','native_rate_shield_idle_rate','native_rate_shield_idle_delay'):
        from .native_resource_rates import trial_amount
        mode=key.removeprefix('native_rate_')
        trial_amount(mode,selection)
        begin_native_resource_rate(mode,selection)
        return
    if key in ('health_regen_native','shield_regen_native'):
        if selection != 1.0:raise ValueError('invalid native regeneration selection')
        begin_native_regen('shield' if key=='shield_regen_native' else 'flesh')
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
    global _auto_blocked, _auto_ground, _auto_next, _ground_retry_at, _reload_handoff
    if option is GUN_ACTOR_BACKEND:
        if (AUTO_OPTIONS['damage'].value is True or 'native_rate_gun_actor' in _automation_leases
                or (_controller is not None and 'damage' in _controller.records) or health_active() or health_fault() or automation_fault()):
            report_live('HOLD: turn off Damage and verify restoration before switching backend');return
    if option is SHIELD_POOL_BACKEND:
        if (any(AUTO_OPTIONS[k].value is True for k in SHIELD_KEYS) or any('native_rate_'+m in _automation_leases for m in SHIELD_POOL_KEYS)
                or (_controller is not None and SHIELD_KEYS.intersection(_controller.records)) or health_active() or health_fault() or automation_fault()):
            report_live('HOLD: turn off both shield recharge controls and verify restoration before switching backend');return
    if option is auto_master or option is auto_consent or option is AUTO_OPTIONS['reload'] or option is RELOAD_EVENT:
        _reload_handoff = None
    try:
        edits = dict(_auto_edits) if option is auto_master and value is False else {}
        apply({**edits, option.identifier: value})
    except Exception as exc:
        _auto_blocked = 'Settings save failed; Restore All, then enable the feature again'
        if option is auto_master and value is False:
            stop_automation('master save failed')
            auto_master.value = False
            _auto_edits.clear()
            _auto_ground = None
            report_live('HOLD: gameplay off in memory; saved settings may still be on, check before restart')
        report_live('HOLD: ' + str(exc)[:120])
        return
    lane_options={**AUTOMATION_OPTIONS,**NATIVE_AUTO_OPTIONS}
    if option in lane_options.values():
        kind = next(k for k,o in lane_options.items() if o is option)
        stop_automation_lane(kind, 'automation preference changed')
        if value is True and not automation_fault() and kind not in _automation_leases:
            _automation_attempted.discard(kind)
            _automation_status[kind] = 'Waiting for eligible session'
    if option is AUTO_OPTIONS['walk_speed'] or option is auto_master:
        _ground_retry_at = 0.0
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
        _auto_blocked = 'Settings save failed; Restore All, then enable the feature again'
        report_live('HOLD: ' + str(exc)[:120])


def pause_auto(reason):
    global _auto_blocked, _auto_ground, _reload_handoff
    _reload_handoff = None
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
            report_live('HOLD: gameplay off in memory; settings save failed, check before restart')


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
    if RELOAD_EVENT.value is True:
        desired.pop('reload',None)
    if GUN_ACTOR_BACKEND.value is True or 'native_rate_gun_actor' in _automation_leases:
        desired.pop('damage',None)
    # Keep the legacy pair backend disjoint from native pool handle lifetime.
    if SHIELD_POOL_BACKEND.value is True or any('native_rate_'+m in _automation_leases for m in SHIELD_POOL_KEYS):
        desired={k:v for k,v in desired.items() if k not in SHIELD_KEYS}
    # Refuse ambiguous saved selections rather than silently choosing a winner.
    if ammo_selection_conflict(desired):
        desired = {k: v for k, v in desired.items() if k not in AMMO_GROUP}
    if LIFE_KEYS <= set(desired):
        desired = {k: v for k, v in desired.items() if k not in LIFE_KEYS}
    # A draft cannot initiate an inactive mutually exclusive modifier.
    for key in (AMMO_GROUP | LIFE_KEYS).intersection(_auto_edits):
        if not (_auto_owned and _controller is not None and key in _controller.records):
            desired.pop(key, None)
    # A native passive-rate handle may still be restoring. Do not introduce a
    # conflicting health field until its original baseline is verified.
    native_health=_automation_leases.get('native_rate_health')
    if native_health is not None and (native_health.record is not None or native_health.fault):
        desired={k:v for k,v in desired.items() if k not in LIFE_KEYS|{'healing_received'}}
    if any('native_rate_'+m in _automation_leases for m in SHIELD_POOL_KEYS):
        desired.pop('healing_received',None)
    native_shield=_automation_leases.get('native_rate_shieldpassive')
    if native_shield is not None and (native_shield.record is not None or native_shield.fault):
        desired={k:v for k,v in desired.items() if k not in SHIELD_KEYS|{'healing_received'}}
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
        _auto_blocked = 'Activation failed: slide_speed; Restore All, then enable the feature again'


def fast_reload_handoff(now, observed):
    """Retry only after verified old-weapon restoration. No steady-state SDK work."""
    global _reload_handoff, _auto_blocked, _auto_ground
    scope, deadline, due = _reload_handoff
    selection = raw_auto_desired(('reload',)).get('reload')
    if (RELOAD_EVENT.value is True or now >= deadline or not _auto_owned or not auto_allowed() or _controller.fault
            or _controller.stop_pending is not None or 'reload' in _controller.records
            or selection is None or 'reload' in _auto_edits):
        _reload_handoff = None
        return False
    if now < due:
        return False
    _reload_handoff = (scope, deadline, now + .05)
    try:
        observed = _controller.context() if observed is None else observed
        if not observed[3] or tuple(identity(x) for x in observed[:3]) != scope:
            _reload_handoff = None
            return False
        rec = _controller.capture('reload')
        if tuple(rec[k+'_id'] for k in ('pc','pawn','state')) != scope:
            _reload_handoff = None
            return False
        targets = target_values('reload', rec['baseline'], rec['tokens'], selection)
        validate_targets(rec['weapon_scope'], targets)
    except (AttributeError, TypeError, ValueError) as exc:
        _controller.note_reload_wait(exc, now)
        return False  # pending equip, unsupported gun, native floor: no writes
    if not auto_allowed() or _controller.stop_pending is not None or raw_auto_desired(('reload',)).get('reload') != selection or 'reload' in _auto_edits:
        _reload_handoff = None
        return False
    _reload_handoff = None
    if not _controller.activate('reload', selection):
        _auto_ground = None
        _auto_blocked = 'Activation failed: reload; Restore All, then enable the feature again'
    else:
        _controller.clear_reload_wait()
    return True  # at most one activation attempt per camera callback


def auto_tick():
    """Camera callback only. Reconcile saved desired settings in owner-confirmed offline solo mode (R2 admission).
    No implicit legacy migration, no retry after unexpected drift or failed write.
    """
    global _controller, _auto_owned, _auto_blocked, _auto_ground, _auto_next, _auto_api, _auto_status, _slide_next, _reload_handoff, _ground_anim_id
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
    if not (_controller is not None and _controller.records) and _auto_ground is None and now < _auto_next and slide_selection is None and _reload_handoff is None:
        return  # idle only: no owned values or queued animation to protect
    if not _auto_owned and _controller is not None and _controller.records:
        # Never adopt active manual baselines into a new automatic session.
        _controller.restore_all('switching to persistent mode')
        return
    try:
        permitted = auto_allowed() and not conflicting_mods()
        if not permitted:
            _auto_status = ('HOLD: disable overlapping tuning mods' if auto_allowed() else
                            'Paused; confirm Offline Local Only and enable a feature')
        hooks = sys.modules['unrealsdk'].hooks
        monitor_ok = _monitor_registered and hooks.has_hook(_MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL, _MONITOR_ID) is True
        if permitted and not monitor_ok:
            _auto_status = 'HOLD: verified camera monitor unavailable'
        permitted = permitted and monitor_ok
    except Exception:
        permitted = False
        _auto_status = 'HOLD: persistent preflight unavailable'
    if not permitted:
        _reload_handoff = None
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
        try:
            observed = _controller.context()
        except Exception as exc:
            observed = None
            reason = str(exc)[:120]
        else:
            reason = _session_reason
        if observed is None or not observed[3]:
            _reload_handoff = None
            _auto_status = 'Waiting for eligible local solo session: ' + (reason or 'local eligibility not established')
            _auto_ground = None
            stop_automation('persistent session no longer eligible')
            _controller.restore_all('persistent session no longer eligible')
            if _controller.fault:
                _auto_blocked = 'Restoration fault; exit game'
            else:
                _auto_owned = False
            return
        # An animation gap is not a session failure. Restore only the owned
        # ground floor; allow a fresh, positively identified animation to rearm.
        # Keep full restoration/fault behavior on failed cleanup or lost scope.
        if 'walk_speed' in _controller.records and now - _ground_seen > 2.0:
            _auto_ground = None
            if not _controller.restore_selected('walk_speed', 'local animation callback stale; waiting to rearm'):
                _auto_blocked = 'Ground restoration failed; exit game'
                return
            _auto_next = 0.0  # queue rearm without waiting for normal cadence
        before = set(_controller.records)
        transitioned = _controller.tick(True, observed=observed, follow_weapon=True, follow_shield=True, follow_gadget=True) or set()
        if set(_controller.records) != before - transitioned or _controller.fault:
            _auto_ground = None
            _auto_blocked = 'Unexpected active field change; Restore All, then enable the feature again'
            _reload_handoff = None
            return
        if 'reload' in transitioned:
            # Native reset recovery must not become an expensive sticky write loop.
            delay = .25 if _controller.reload_reset_recovered else 0.0
            _reload_handoff = (tuple(identity(x) for x in observed[:3]), now + 3.0, now + delay)
        # The old animation identity is a cheap rejection filter, not a lifetime
        # pin. Refresh only on normal reconciliation when callbacks have paused.
        # Never refresh the heartbeat here: only an actual local callback does.
        if 'walk_speed' in _controller.records and now >= _auto_next and now - _ground_seen > .25:
            try:
                pc, pawn = observed[:2]
                if identity(pc.OakCharacter) == identity(pawn):
                    anim = pawn.Mesh.GetAnimInstance()
                    if anim is not None:
                        _ground_anim_id = identity(anim)
            except (AttributeError, TypeError, ValueError):
                pass
    if _reload_handoff is not None and fast_reload_handoff(now, observed):
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
                _auto_status = 'Waiting for eligible local solo session: ' + (_session_reason or 'local eligibility not established') + '; verify Offline Local Only'
                return
            _controller = Controller(context, sys.modules['unrealsdk'].unreal.WeakPointer, report_live, threading.get_ident, shield_binding=shield_binding)
            _auto_owned = True
        else:
            observed = _controller.context() if observed is None else observed
            if not observed[3]:
                _auto_status = 'Waiting for eligible local solo session: ' + (_session_reason or 'local eligibility not established')
                _auto_ground = None
                _auto_owned = False
                return
    except Exception as exc:
        _auto_status = 'Waiting for loaded solo character or compatible SDK reflection: ' + str(exc)[:120]
        _auto_next = _slide_next = now + 1.0  # loading screen or missing reflection: bounded retry, no writes
        return
    if _controller.stop_pending is not None:
        _controller.restore_all('persistent stop pending')
        _auto_ground = None
        _auto_blocked = 'Stopped; Restore All, then enable the feature again'
        return
    _auto_status = 'Eligible solo session; reconciling saved feature settings'
    for key in tuple(_controller.records):
        if key not in desired:
            if not _controller.restore_selected(key, 'persistent feature disabled'):
                if _controller.records.get(key, {}).get('overfull_warning') and not _controller.fault:
                    _auto_blocked = 'Capacity restore waiting: remove excess items; enable features only after restoration'
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
            # Expired unused request: no ownership to clean up. Retry below.
    for key, selection in desired.items():
        if key == 'reload' and _reload_handoff is not None:
            continue  # pending bounded handoff already has its own retry cadence
        if _controller.records.get(key, {}).get('selection') == selection:
            continue
        if key == 'walk_speed':
            if now < _ground_retry_at:
                continue
            if _auto_ground is None:
                if not ensure_ground_hook():
                    _auto_status = 'Ground animation hook unavailable; other features unaffected'
                    continue
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
            except (AttributeError, TypeError, ValueError) as exc:
                if key == 'reload':
                    _controller.note_reload_wait(exc, now)
                continue
        if not _controller.activate(key, selection):
            _auto_ground = None
            _auto_blocked = 'Activation failed: ' + key + '; Restore All, then enable the feature again'
            return
        if key == 'reload':
            _controller.clear_reload_wait()
        break  # at most one non-animation activation per reconciliation interval


def automation_fault():
    return bool(_reload_event is not None and _reload_event.fault) or any(l.fault for l in _automation_leases.values())


def stop_automation_lane(kind, reason):
    lease = _automation_leases.get(kind)
    if lease is not None:
        if kind in NATIVE_AUTO_OPTIONS:
            lease.next_selection=None
        if kind not in NATIVE_AUTO_OPTIONS or (not lease.stop_requested and not lease.fault):
            lease.stop(reason)
        if not lease.fault and (kind not in NATIVE_AUTO_OPTIONS or lease.record is None):
            _automation_leases.pop(kind, None)
    _automation_status[kind] = ('Restoring native rate; wait for verification' if kind in NATIVE_AUTO_OPTIONS and lease is not None and lease.record is not None else 'Stopped: '+reason)


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


def reload_event_selection():
    if (RELOAD_EVENT.value is not True or AUTO_OPTIONS['reload'].value is not True
            or 'reload' in _auto_edits or AUTOMATION_OPTIONS['reload'].value is True
            or 'reload' in _automation_leases):
        return None
    selected = _PREVIEW_BY_KEY['reload'].value
    return selected if type(selected) in (int,float) and .5 <= selected <= 3. and selected != 1. else None


def reload_event_permitted():
    try:
        if (not _reload_event_registered or _automation_busy or _monitor_thread != threading.get_ident()
                or time.monotonic()-_monitor_seen > 2. or reload_event_selection() is None
                or not automation_permitted() or (_controller is not None and 'reload' in _controller.records)):
            return False
        if _reload_event is not None and _reload_event.root is not None and reload_event_selection() != _reload_event.root[4]:
            return False
        from .reload_assist import REQUEST
        hooks=sys.modules['unrealsdk'].hooks
        return (hooks.has_hook(REQUEST,hooks.Type.PRE,'bl4_custom_reload_window_pre') is True
                and hooks.has_hook(REQUEST,hooks.Type.POST_UNCONDITIONAL,'bl4_custom_reload_window_post') is True)
    except Exception:
        return False


def ensure_reload_event():
    global _reload_event_attempted,_reload_event_registered,_reload_event,_reload_event_status
    if _reload_event_attempted: return _reload_event_registered
    if reload_event_selection() is None: return False
    _reload_event_attempted=True
    try:
        from .reload_window import ReloadWindow,request_function
        from .reload_assist import REQUEST
        sdk=sys.modules['unrealsdk'];hooks=sdk.hooks
        request_function(sdk)
        pre,post=hooks.Type.PRE,hooks.Type.POST_UNCONDITIONAL
        ids=('bl4_custom_reload_window_pre','bl4_custom_reload_window_post')
        if any(hooks.has_hook(REQUEST,k,i) is not False for k,i in zip((pre,post),ids)):
            raise ValueError('reload request hook identity unavailable')
        # Install cleanup first. Partial registration never enables writes.
        result=hooks.add_hook(REQUEST,post,ids[1],reload_event_post)
        if type(result) is not bool or hooks.has_hook(REQUEST,post,ids[1]) is not True:
            raise ValueError('reload cleanup hook unavailable')
        result=hooks.add_hook(REQUEST,pre,ids[0],reload_event_pre)
        if type(result) is not bool or hooks.has_hook(REQUEST,pre,ids[0]) is not True:
            raise ValueError('reload pre hook unavailable')
        api=bound_session(sdk)
        _reload_event=ReloadWindow(lambda:current_session(api),sdk.unreal.WeakPointer,
                                  reload_event_permitted,threading.get_ident,lambda:time.monotonic(),report_live,
                                  lambda: tuple(t for r in (_controller.records.values() if _controller is not None else ()) for t in r['tokens']))
        _reload_event_registered=True
        _reload_event_status='Waiting for native reload request (experimental)'
        report_live('RELOAD EVENT: request hooks registered; actual callback not yet observed')
    except Exception as exc:
        _reload_event_status='HOLD: '+str(exc)[:120]
    return _reload_event_registered


def reload_event_pre(obj,args,*_):
    if _reload_event is not None:
        try: _reload_event.pre(obj,args,reload_event_selection())
        except Exception as exc: _reload_event.note('request observation failed: '+str(exc)[:100])
    # None leaves native request untouched, including its arguments and return.


def reload_event_post(obj,*_):
    if _reload_event is not None:
        try: _reload_event.post(obj)
        except Exception as exc:
            _reload_event.fault=True
            report_live('FAULT: reload event cleanup unavailable: '+str(exc)[:100]+'; exit game')


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
    counterpart={'health':'native_rate_health','shield':'native_rate_shieldpassive','skill_cooldown':'native_rate_cooldown','skill_duration':'native_rate_duration'}.get(kind)
    if counterpart and (NATIVE_AUTO_OPTIONS[counterpart].value is True or counterpart in _automation_leases):
        return 'choose native rate OR corresponding refill assist'
    if kind not in ('health', 'shield'):
        return ''
    selected = set(raw_auto_desired(SHIELD_KEYS | {'healing_received'}))
    active = set(_controller.records) if _controller is not None else set()
    if 'healing_received' in selected | active:
        return 'healing multiplier incompatible'
    if kind == 'health' and LIFE_KEYS.intersection(set(auto_desired()) | active):
        return 'native life-steal modifier incompatible with flesh assist'
    if kind == 'shield' and (SHIELD_KEYS.intersection(selected | active) or any('native_rate_'+m in _automation_leases for m in SHIELD_POOL_KEYS)):
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


def native_rate_allowed(kind,selection):
    mode=kind.removeprefix('native_rate_')
    option=NATIVE_RATE_OPTIONS[mode]
    # Preserve an active committed setting while its draft is waiting to save.
    if NATIVE_AUTO_OPTIONS[kind].value is not True or normalize(option,option.value)!=selection:
        return False
    if mode=='gun_actor':
        return (GUN_ACTOR_BACKEND.value is True and .5<=selection<=5. and selection!=1.
                and (_controller is None or 'damage' not in _controller.records)
                and NATIVE_AUTO_OPTIONS['native_rate_cash'].value is not True
                and 'native_rate_cash' not in _automation_leases)
    if mode in SHIELD_POOL_KEYS:
        active=set(_controller.records) if _controller is not None else set()
        return (SHIELD_POOL_BACKEND.value is True and .5<=selection<=3. and selection!=1.
                and not SHIELD_KEYS.intersection(active) and 'healing_received' not in set(raw_auto_desired())|active
                and AUTOMATION_OPTIONS['shield'].value is not True and 'shield' not in _automation_leases
                and NATIVE_AUTO_OPTIONS['native_rate_shieldpassive'].value is not True and 'native_rate_shieldpassive' not in _automation_leases)
    if mode!='health' and selection<=1.:return False
    if mode=='cash':
        return not ((GUN_ACTOR_BACKEND.value is True and AUTO_OPTIONS['damage'].value is True)
                    or 'native_rate_gun_actor' in _automation_leases)
    if mode in ('vaultregen','vaultdelay','vaultdepleted','gear_luck'):return True
    if mode=='shieldpassive':
        active=set(_controller.records) if _controller is not None else set()
        return not (AUTOMATION_OPTIONS['shield'].value is True or 'shield' in _automation_leases or any('native_rate_'+m in _automation_leases for m in SHIELD_POOL_KEYS) or (SHIELD_KEYS|{'healing_received'}).intersection(set(raw_auto_desired())|active))
    counterpart='health' if mode=='health' else 'skill_'+mode
    if AUTOMATION_OPTIONS[counterpart].value is True or counterpart in _automation_leases:return False
    if mode=='health':
        active=set(_controller.records) if _controller is not None else set()
        if ({'healing_received'}|LIFE_KEYS).intersection(set(raw_auto_desired())|active):return False
    return True


def make_session_cash(session,selection):
    from .blackboard_rewards import (CashPrimaryBinding,CashFormulaBinding,
        SessionCashPrimary,SessionCashGeneric,SPECS,DEF)
    sdk=sys.modules['unrealsdk'];u=sdk.unreal
    defs=[d for d in sdk.find_all('ScriptStruct',exact=False) if d._path_name()==DEF]
    if len(defs)!=1:raise ValueError('native cash definition struct unavailable')
    fs=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS]
    def permitted():
        try:
            return (_monitor_thread==threading.get_ident() and
                    feature_enabled(NATIVE_AUTO_OPTIONS['native_rate_cash']) and
                    native_rate_allowed('native_rate_cash',selection) and automation_permitted())
        except Exception:return False
    args=(lambda:current_session(session),u.WeakPointer,time.monotonic,threading.get_ident,report_live,permitted)
    # Select the primary path before admission; use generic only after a
    # read-only preflight failure. No fallback after the lane has armed.
    primary=SessionCashPrimary('progress_money',selection,CashPrimaryBinding(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct),*args)
    try:
        sample=primary.stable()
        if not primary.formula_matches(sample[7],sample[3]):raise ValueError('primary formula unavailable')
    except Exception:
        return SessionCashGeneric('progress_money',selection,CashFormulaBinding(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct),*args)
    return primary


def make_session_gun(session,selection):
    from .blackboard_rewards import GunFormulaBinding,SessionGunTrial,SPECS,DEF,GUN_MODE
    sdk=sys.modules['unrealsdk'];u=sdk.unreal
    defs=[d for d in sdk.find_all('ScriptStruct',exact=False) if d._path_name()==DEF]
    if len(defs)!=1:raise ValueError('native gun definition struct unavailable')
    fs=[f for f in sdk.find_all('Function',exact=False) if str(f.Name) in SPECS]
    def permitted():
        try:
            return (_monitor_thread==threading.get_ident() and feature_enabled(AUTO_OPTIONS['damage'])
                    and native_rate_allowed('native_rate_gun_actor',selection) and automation_permitted())
        except Exception:return False
    binding=GunFormulaBinding(fs,loot_bound,sdk.make_struct,u.FGbxDefPtr,defs[0],u.WrappedStruct)
    return SessionGunTrial(GUN_MODE,selection,binding,lambda:current_session(session),u.WeakPointer,time.monotonic,threading.get_ident,report_live,permitted)


def make_automation_lane(kind, session):
    if kind=='native_rate_gun_actor':
        option=NATIVE_RATE_OPTIONS['gun_actor']
        return make_session_gun(session,normalize(option,option.value))
    if kind=='native_rate_cash':
        option=NATIVE_RATE_OPTIONS['cash']
        return make_session_cash(session,normalize(option,option.value))
    if kind in NATIVE_AUTO_OPTIONS:
        mode=kind.removeprefix('native_rate_');option=NATIVE_RATE_OPTIONS[mode]
        return make_native_resource_rate(mode,normalize(option,option.value),persistent=True)
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
        from .loot_vacuum import Vacuum, lazy_ammo_reader, flesh_need_reader
        categories = tuple(k for k,o in VACUUM_PREFS.items() if o.value is True)
        radius = normalize(VACUUM_RADIUS_PREF,VACUUM_RADIUS_PREF.value)
        return Vacuum(context,sdk.unreal.WeakPointer,sdk.find_all,sdk.make_struct,time.monotonic,threading.get_ident,report_live,categories,radius,continuous=True,high_gear_only=VACUUM_HIGH_PREF.value is True,ammo_reader=lazy_ammo_reader(sdk,loot_bound),health_reader=flesh_need_reader(sdk))
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
    lane_options={**AUTOMATION_OPTIONS,**NATIVE_AUTO_OPTIONS}
    if not _automation_leases and (time.monotonic() < _automation_next or not any(o.value is True and k not in _automation_attempted for k,o in lane_options.items())):
        return
    _automation_busy = True
    try:
        # Drain native cleanup even after master/consent/mod disable, conflict, or peer fault.
        # Never discard a pending native handle or its delayed verification receipt.
        try:
            permitted=automation_permitted()
        except Exception:
            # A failed permission observation denies new actions, but must not
            # prevent the original handle from reaching its cleanup path.
            permitted=False
        rearmed=set()
        for kind in NATIVE_AUTO_OPTIONS:
            lease=_automation_leases.get(kind)
            if lease is None or lease.fault:continue
            if not permitted or lease.stop_requested or not native_rate_allowed(kind,lease.selection):
                pending=lease.next_selection
                if (not permitted or pending is None or not native_rate_allowed(kind,pending)
                        or not feature_enabled(NATIVE_AUTO_OPTIONS[kind])):
                    lease.next_selection=None
                original=lease.record
                if not lease.stop_requested:lease.stop('native rate permission or selection ended')
                _automation_attempted.add(kind)
                lease.tick(False)
                if lease.fault:
                    request_stop('native rate cleanup fault',immediate=False)
                    permitted=False
                elif lease.record is None:
                    pending=lease.next_selection
                    lease.next_selection=None
                    if (pending is not None and original is not None and automation_permitted()
                            and native_rate_allowed(kind,pending) and feature_enabled(NATIVE_AUTO_OPTIONS[kind])
                            and lease.rearm_verified(original,pending)):
                        rearmed.add(kind)
                        _automation_status[kind]='Edited native rate armed (gameplay unverified)'
                    else:
                        _automation_leases.pop(kind,None)
                        _automation_status[kind]='Restored / toggle lane to rearm'
                else:_automation_status[kind]='Restoring; wait for verification'
        if not permitted or not automation_permitted():
            stop_automation('permission or modifier compatibility ended')
            return
        # Each lane has its own fresh session and weak identity validation. Never share a native object across lanes.
        for kind in (*AUTOMATION_OPTIONS,*NATIVE_AUTO_OPTIONS):
            if kind in rearmed:continue
            # The legacy equipped-field backend must not incur pool admission work.
            if kind=='native_rate_gun_actor' and GUN_ACTOR_BACKEND.value is not True:
                continue
            if kind.removeprefix('native_rate_') in SHIELD_POOL_KEYS and SHIELD_POOL_BACKEND.value is not True:
                continue  # original native cleanup was handled above
            if lane_options[kind].value is not True:
                stop_automation_lane(kind,'disabled')
                continue
            # A stopped lane cannot dispatch until explicitly rearmed. A lane
            # waiting for its admission deadline also cannot dispatch yet.
            # Still check every live lease, including pending native cleanup.
            if kind not in _automation_leases and (kind in _automation_attempted or time.monotonic() < _automation_next):
                continue
            if not automation_permitted():
                stop_automation('permission ended before next lane')
                return
            if kind in NATIVE_AUTO_OPTIONS:
                lease=_automation_leases.get(kind)
                if lease is not None and lease.stop_requested:continue
                option=NATIVE_RATE_OPTIONS[kind.removeprefix('native_rate_')]
                selection=normalize(option,option.value)
                if not native_rate_allowed(kind,selection) or (lease is None and option.identifier in _auto_edits):
                    _automation_status[kind]='Waiting: native rate selection or compatibility'
                    continue
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
                elif kind in NATIVE_AUTO_OPTIONS:
                    _automation_status[kind]='Native '+lease.phase+' (gameplay unverified)'
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
                session = _auto_api if _auto_api is not None else bound_session(sys.modules['unrealsdk'])
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
    load_vacuum_preferences()
    if auto_master.value is True and not any(f.value is True for f in feature_flags()):
        auto_master.value = False  # legacy ON without any enabled features
    if auto_master.value is True and auto_consent.value is True:
        ensure_monitor()
    print('[BL4 Custom] v0.7.61-experimental enabled; F8 opens menu. Enable individual features in F8.')


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
options += [NestedOption('persistent', AUTO_SETTINGS, display_name='Saved gameplay settings (use F8)'), NestedOption('vacuum_preferences', [*VACUUM_PREFS.values(), VACUUM_RADIUS_PREF, VACUUM_HIGH_PREF], display_name='Saved vacuum preferences (no startup activation)')]
options += [NestedOption('native_rate_options', [*(o for k,o in NATIVE_RATE_OPTIONS.items() if k not in ('gear_luck','cash') and k not in NATIVE_BACKEND_KEYS),*(o for k,o in NATIVE_AUTO_OPTIONS.items() if k.removeprefix('native_rate_') not in NATIVE_BACKEND_KEYS)], display_name='Native rate selections and persistent opt-in (experimental)')]
options += [NestedOption('recovery_rates', list(RECOVERY_RATES.values()), display_name='Recovery pulse rates (experimental)'), NestedOption('adaptive_skill', [*SKILL_ADAPTIVE.values(),*SKILL_RATES.values(),*SKILL_FOLLOW.values(),*SKILL_NATIVE.values(),CROSSFIRE_GATE], display_name='Adaptive skill assist (experimental)')]
options += [NestedOption(key, items, display_name=name, description=DESCRIPTION)
            for key, name, items in CATEGORIES if key != 'menu']
options += [NestedOption('menu', [ButtonOption('open_from_menu', display_name='Open Graphical Menu', on_press=toggle_menu)], display_name='Custom Menu'),
            ButtonOption('reset_preview', display_name='Restore Vanilla Defaults', on_press=reset)]
mod = build_mod(options=options, hooks=[], commands=[], keybinds=[open_key], auto_enable=True,
                on_enable=enabled, on_disable=disabled)
