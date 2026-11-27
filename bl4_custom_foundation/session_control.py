"""Single owner of persistent gameplay fields; fail closed on drift or lost context.
No SDK imports, background threads, raw memory, rewards or save writes.
"""
from time import monotonic

from .gameplay_fields import FEATURES, RARITY_KEYS, read_fields, target_values, identity, describe_fields, lifesteal_peer_context, validate_overshield, slide_scale, slide_active
from . import weapon_rates, inventory_capacity, shield_rates, gadget_rates


from .ground_speed import floor_target

# Legacy pawn-wide damage path stays excluded; damage now uses equipped weapon scope.
DAMAGE_HOLD = frozenset()
GROUND_KEYS = frozenset(('walk_speed', 'sprint'))

class Controller:
    def __init__(self, context, weak_pointer, report, thread, shield_binding=None):
        self.context = context
        self.shield_binding = shield_binding
        self.weak_pointer = weak_pointer
        self.report = report
        self.thread = thread
        self.records = {}
        self.fault = False
        self.busy = False
        self.stop_pending = None

    def log(self, message):
        return self.report(message)

    def fail(self, message):
        self.fault = True
        self.log('FAULT: ' + message + '. Exit game immediately; do not play.')

    def capture(self, key):
        pc, pawn, state, eligible = self.context()
        if not eligible:
            raise ValueError('eligible authoritative one-player session required')
        scope = weapon_rates.capture(pawn, key, self.weak_pointer) if key in weapon_rates.WEAPON_KEYS else None
        inv = inventory_capacity.capture(pc, pawn, key, self.weak_pointer) if key in inventory_capacity.KEYS else None
        shield = shield_rates.capture(pawn, key, self.weak_pointer, self.shield_binding()) if key in shield_rates.KEYS else None
        gadget = gadget_rates.capture(pawn, self.weak_pointer) if key == gadget_rates.KEY else None
        if gadget is not None:
            resolved, active = gadget_rates.resolve(pawn, gadget)
            if not active: raise ValueError('grenade gadget no longer equipped')
            _, tokens, baseline = describe_fields(resolved)
        elif shield is not None:
            resolved, active = shield_rates.resolve(pawn, shield)
            if not active: raise ValueError("shield no longer equipped")
            _, tokens, baseline = describe_fields(resolved)
        elif inv is not None:
            resolved, _ = inventory_capacity.resolve(pc, pawn, inv)
            _, tokens, baseline = describe_fields(resolved)
        elif scope is not None:
            resolved, active = weapon_rates.resolve(pawn, scope)
            if not active:
                raise ValueError('weapon no longer active')
            _, tokens, baseline = describe_fields(resolved)
        elif key == 'slide_speed':
            if not slide_active(pawn):
                raise ValueError('exact active slide required')
            slide_value, _ = slide_scale(pawn)
            _, tokens, baseline = describe_fields((slide_value,))
        else:
            _, tokens, baseline = read_fields(key, pawn, state)
        slide_base = None
        if key == 'slide_speed':
            slide_value, slide_base = slide_scale(pawn)
            if describe_fields((slide_value,))[1:] != (tokens, baseline):
                raise ValueError('slide scale changed during capture')
            slide_base = describe_fields((slide_base,))[1:]
        if key in RARITY_KEYS and any(v <= 0 for v in baseline):
            raise ValueError('positive rarity baseline required before activation')
        if key == 'legendary_weight' and baseline != (1.,):
            raise ValueError('legendary baseline must be exactly 1.0')
        # A modified value/base pair may reflect buffs or another writer; do not adopt it.
        if len(baseline) == 2 and baseline[0] != baseline[1]:
            raise ValueError('Value/BaseValue differ; baseline uncertain')
        taken = {t for record in self.records.values() for t in record['tokens']}
        if taken.intersection(tokens):
            raise ValueError('field already owned by another feature')
        return dict(key=key, pc=self.weak_pointer(pc), pawn=self.weak_pointer(pawn),
                    state=self.weak_pointer(state), pc_id=identity(pc), pawn_id=identity(pawn),
                    state_id=identity(state), tokens=tokens, baseline=baseline,
                    weapon_scope=scope, inventory_scope=inv, shield_scope=shield, gadget_scope=gadget, slide_base=slide_base, expected=baseline, owned=[{v} for v in baseline], thread=self.thread())

    def resolve(self, record, *, observed=None):
        if self.thread() != record['thread']:
            raise ValueError('wrong game hook thread')
        pc, pawn, state, eligible = self.context() if observed is None else observed
        for name, current in (('pc', pc), ('state', state)):
            old = record[name]()
            if old is None or current is None or identity(old) != record[name+'_id'] or identity(current) != record[name+'_id']:
                raise ValueError('original '+name+' no longer identifiable')
        old_pawn = record['pawn']()
        same_pawn = (old_pawn is not None and pawn is not None and identity(old_pawn) == record['pawn_id']
                     and identity(pawn) == record['pawn_id'])
        # World-owned loot can be restored on the same world if pawn changes;
        # never write a pawn-owned field to a replacement pawn or stale object.
        if record['key'] not in RARITY_KEYS and not same_pawn:
            raise ValueError('original pawn no longer identifiable')
        scope = record.get('weapon_scope')
        inv = record.get('inventory_scope')
        shield = record.get('shield_scope')
        gadget = record.get('gadget_scope')
        if gadget is not None:
            resolved, active = gadget_rates.resolve(pawn, gadget)
            fields, tokens, values = describe_fields(resolved)
            eligible = eligible and active
        elif shield is not None:
            resolved, active = shield_rates.resolve(pawn, shield)
            fields, tokens, values = describe_fields(resolved)
            eligible = eligible and active
        elif inv is not None:
            resolved, _ = inventory_capacity.resolve(pc, pawn, inv)
            fields, tokens, values = describe_fields(resolved)
        elif scope is not None:
            resolved, active = weapon_rates.resolve(pawn, scope)
            fields, tokens, values = describe_fields(resolved)
            eligible = eligible and active
        elif record['key'] == 'slide_speed':
            if eligible:
                sliding = slide_active(pawn)
                # Native predicate may synchronously change scope; recheck before reading the write target.
                pc_now, pawn_now, state_now, ok = self.context()
                if tuple(identity(o) for o in (pc_now, pawn_now, state_now)) != (record['pc_id'], record['pawn_id'], record['state_id']):
                    raise ValueError('slide session changed during predicate')
                eligible = ok and sliding
                pawn = pawn_now
            value_field, base_field = slide_scale(pawn)
            fields, tokens, values = describe_fields((value_field,))
            if describe_fields((base_field,))[1:] != record['slide_base']:
                raise ValueError('slide base changed; refused to overwrite')
        else:
            fields, tokens, values = read_fields(record['key'], pawn, state)
        if tokens != record['tokens']:
            raise ValueError('reflected field identity changed')
        return fields, values, eligible and same_pawn

    def write_one(self, record, index, value, *, applying):
        fields, values, eligible = self.resolve(record)
        if applying and not eligible:
            raise ValueError('session became ineligible')
        if applying and record['key'] in ('lifesteal_rate', 'lifesteal_fraction'):
            if self.stop_pending is not None or self.records.get(record['key']) is not record:
                raise ValueError('life-steal activation interrupted')
            if lifesteal_peer_context(record['key'], record['pawn'](), record['baseline'], (value,), record['tokens']) != record['life_context']:
                raise ValueError('life-steal rate/cap changed')
            fields, values, eligible = self.resolve(record)
            if not eligible or self.stop_pending is not None or self.records.get(record['key']) is not record:
                raise ValueError('life-steal scope lost')
        if applying and record['key'] == 'overshield_duration':
            if self.stop_pending is not None or self.records.get(record['key']) is not record:
                raise ValueError('overshield activation interrupted')
            if validate_overshield(record['pawn'](), record['baseline'], (value,)) != record['overshield_context']:
                raise ValueError('overshield base changed')
            fields, values, eligible = self.resolve(record)
            if not eligible:
                raise ValueError('overshield scope lost')
        if applying and record['key'] == 'slide_speed':
            if self.stop_pending is not None or self.records.get('slide_speed') is not record:
                raise ValueError('slide activation interrupted')
        if applying and record.get('gadget_scope') is not None:
            pc, pawn, state, ok = self.context()
            if not ok or tuple(identity(o) for o in (pc,pawn,state)) != (record['pc_id'],record['pawn_id'],record['state_id']) or record['gadget_scope'][0]().bIsUsing is not False or self.stop_pending is not None or self.records.get(record['key']) is not record:
                raise ValueError('grenade gadget busy or activation interrupted')
        if applying and record.get('shield_scope') is not None:
            pc, pawn, state, ok = self.context()
            if not ok or self.stop_pending is not None or self.records.get(record['key']) is not record or tuple(identity(o) for o in (pc,pawn,state)) != (record['pc_id'],record['pawn_id'],record['state_id']):
                raise ValueError('shield session changed before write')
        if any(v not in allowed for v, allowed in zip(values, record['owned'], strict=True)):
            raise ValueError('unexpected foreign value; refused to overwrite')
        inv = record.get('inventory_scope')
        if inv is not None:
            pc, pawn, _, eligible_now = self.context()
            _, count = inventory_capacity.resolve(pc, pawn, inv)
            if applying and not eligible_now:
                raise ValueError('inventory session became ineligible')
            inventory_capacity.validate(inv, count, value, applying=applying)
        if applying and record['key'] == 'reload':
            weapon_rates.validate_reload_floor(record['weapon_scope'], (value,))
        if values[index] != value:
            owner, field, _, _ = fields[index]
            setattr(owner, field, value)  # exact allowlisted reflected property only
        _, actual, _ = self.resolve(record)
        if actual[index] != value:
            raise ValueError('write readback mismatch')
        return actual

    def restore(self, key, reason):
        record = self.records.get(key)
        if record is None:
            return True
        try:
            _, values, eligible = self.resolve(record)
            if any(v not in allowed for v, allowed in zip(values, record['owned'], strict=True)):
                raise ValueError('unexpected foreign value; refused to overwrite')
            inv = record.get('inventory_scope')
            if inv is not None:
                pc, pawn, _, eligible_now = self.context()
                _, count = inventory_capacity.resolve(pc, pawn, inv)
                if count > record['baseline'][0] and eligible and eligible_now:
                    if not record.get('overfull_warning'):
                        self.log('HOLD ' + key + ': remove excess items before restoring; original capacity retained in record. Stay offline in original session.')
                    record['overfull_warning'] = True
                    return False
                record.pop('overfull_warning', None)
            for i, base in enumerate(record['baseline']):
                self.write_one(record, i, base, applying=False)
            _, values, _ = self.resolve(record)
            if values != record['baseline']:
                raise ValueError('baseline readback mismatch')
            if record.get('shield_scope') is not None:
                shield_rates.validate_readback(record['shield_scope'][0](), key, values[0])
                _, verified, _ = self.resolve(record)
                if verified != record['baseline']:
                    raise ValueError('shield baseline changed after getter readback')
        except Exception as exc:
            self.fail(key + ' restoration unverified (' + reason + '): ' + str(exc)[:150])
            return False
        del self.records[key]
        self.log('RESTORED ' + key + ': ' + repr(values) + ' (' + reason + ')')
        return True

    def restore_selected(self, key, reason):
        if self.fault or self.busy:
            return False
        result = self.restore(key, reason)
        if not result and self.fault:
            for other in tuple(self.records):
                if other != key:
                    self.restore(other, 'another feature faulted')
        return result

    def restore_all(self, reason):
        self.stop_pending = None
        success = True
        for key in tuple(self.records):
            success = self.restore(key, reason) and success
        return success

    def activate(self, key, selection, *, ground_sprinting=None):
        if self.busy or self.fault:
            return False
        if key in GROUND_KEYS and selection != 1 and (GROUND_KEYS - {key}).intersection(self.records):
            self.log('HOLD: restore the other ground-speed mode first')
            return False
        # Avoid compounding two unverified native ammo regeneration paths.
        if selection != 1 and ((key == 'player_ammo_regen' and weapon_rates.AMMO_KEYS.intersection(self.records)) or
                               (key in weapon_rates.AMMO_KEYS and 'player_ammo_regen' in self.records)):
            self.log('HOLD: restore other ammo regeneration path first')
            return False
        if selection != 1 and key in ('lifesteal_rate', 'lifesteal_fraction') and ({'lifesteal_rate', 'lifesteal_fraction'} - {key}).intersection(self.records):
            self.log('HOLD: restore other life-steal control first')
            return False
        self.busy = True
        try:
            if key not in FEATURES or key in DAMAGE_HOLD:
                raise ValueError('feature HOLD')
            _, lo, hi = FEATURES[key]
            # Validate input even when selecting vanilla.
            target_values(key, (1.,), ((1, 'dummy', 'ZDoubleProperty'),), selection)
            if selection == 1:
                result = self.restore(key, '1x selected')
                if not result and self.fault:
                    for other in tuple(self.records):
                        if other != key:
                            self.restore(other, 'another feature faulted')
                return result
            if self.stop_pending is not None:
                raise ValueError('restoration pending')
            record = self.records.get(key) or self.capture(key)
            record.pop('reload_watch', None)
            _, values, eligible = self.resolve(record)
            # Ground animation maintenance already accepts the captured baseline
            # as an engine reset. Allow the same exact reset during a live update,
            # but never adopt a different value or a replacement object.
            baseline_reset = key in GROUND_KEYS and key in self.records and values == record['baseline']
            if record.get('gadget_scope') is not None and record['gadget_scope'][0]().bIsUsing is not False:
                raise ValueError('wait until grenade gadget is idle')
            if not eligible or (values != record['expected'] and not baseline_reset):
                raise ValueError('session or owned value changed')
            targets = (floor_target(record['baseline'], record['tokens'], selection, ground_sprinting, sprint_only=key == 'sprint')
                       if key in GROUND_KEYS else target_values(key, record['baseline'], record['tokens'], selection))
            if record.get('inventory_scope') is not None:
                pc, pawn, _, eligible_now = self.context()
                _, count = inventory_capacity.resolve(pc, pawn, record['inventory_scope'])
                if not eligible_now:
                    raise ValueError('inventory session became ineligible')
                inventory_capacity.validate(record['inventory_scope'], count, targets[0], applying=True)
            if key in ('lifesteal_rate', 'lifesteal_fraction'):
                life_context = lifesteal_peer_context(key, record['pawn'](), record['baseline'], targets, record['tokens'])
                if key in self.records and life_context != record['life_context']:
                    raise ValueError('life-steal rate/cap changed')
                record['life_context'] = life_context
            if key == 'overshield_duration':
                overshield_context = validate_overshield(record['pawn'](), record['baseline'], targets)
                if key in self.records and overshield_context != record['overshield_context']:
                    raise ValueError('overshield base changed')
                record['overshield_context'] = overshield_context
            if record.get('weapon_scope') is not None:
                weapon_rates.validate_targets(record['weapon_scope'], targets)
            if values == targets and key not in GROUND_KEYS:
                self.log('ACTIVE ' + key + ': already ' + repr(targets) + '; no write')
                return True
            if not self.log('IN PROGRESS ' + key + ': ' + repr(values) + ' -> ' + repr(targets)):
                raise ValueError('session report unavailable')
            self.records[key] = record
            record['owned'] = [{b, old, target} for b, old, target in zip(record['baseline'], values, targets, strict=True)]
            for i, value in enumerate(targets):
                self.write_one(record, i, value, applying=True)
            _, readback, eligible = self.resolve(record)
            if readback != targets or not eligible:
                raise ValueError('post-write verification failed')
            if key == 'slide_speed' and (self.stop_pending is not None or self.records.get(key) is not record):
                raise ValueError('slide activation interrupted after write')
            if record.get('shield_scope') is not None:
                shield_rates.validate_readback(record['shield_scope'][0](), key, targets[0])
                _, checked, still_eligible = self.resolve(record)
                if not still_eligible or checked != targets or self.stop_pending is not None or self.records.get(key) is not record:
                    raise ValueError('shield scope changed after native readback')
            if key in ('lifesteal_rate', 'lifesteal_fraction') and (self.stop_pending is not None or self.records.get(key) is not record or lifesteal_peer_context(key, record['pawn'](), record['baseline'], targets, record['tokens']) != record['life_context']):
                raise ValueError('life-steal rate/cap changed after write')
            if key == 'overshield_duration' and (self.stop_pending is not None or self.records.get(key) is not record or validate_overshield(record['pawn'](), record['baseline'], targets) != record['overshield_context']):
                raise ValueError('overshield scope/base changed after write')
            record['expected'] = targets
            record['selection'] = selection
            record['owned'] = [{b, t} for b, t in zip(record['baseline'], targets, strict=True)]
            if not self.log('ACTIVE ' + key + ': baseline ' + repr(record['baseline']) + '; verified ' + repr(targets) + '; gameplay unverified'):
                self.restore_all('report unavailable')
                return False
            return True
        except Exception as exc:
            # Restore the affected field and any other active features if uncertain.
            self.log('HOLD ' + key + ': ' + str(exc)[:180])
            self.restore_all('activation/update failed')
            return False
        finally:
            self.busy = False

    def ground_frame(self, sprint, *, observed=None):
        """Maintain the owned floor on the local animation frame only; no arbitrary drift adoption."""
        record = next((self.records[k] for k in GROUND_KEYS if k in self.records), None)
        if record is None or self.busy or self.fault:
            return
        self.busy = True
        try:
            _, values, eligible = self.resolve(record, observed=observed)
            if not eligible or self.stop_pending is not None:
                self.restore_all('ground frame no longer eligible')
                return
            if values not in (record['baseline'], record['expected']):
                raise ValueError('foreign ground speed drift')
            target = floor_target(record['baseline'], record['tokens'], record['selection'], sprint, sprint_only=record['key'] == 'sprint')
            if values == target and record['expected'] == target:
                return
            previous = record['expected']
            record['owned'] = [{record['baseline'][0], previous[0], target[0]}]
            self.write_one(record, 0, target[0], applying=True)
            record['expected'] = target
            record['owned'] = [{record['baseline'][0], target[0]}]
            if previous != target and not self.log('GROUND stance target: ' + repr(target) + '; gameplay unverified'):
                self.restore_all('report unavailable')
        except Exception as exc:
            self.log('HOLD ground speed: ' + str(exc)[:150])
            self.restore_all('ground frame failed')
        finally:
            self.busy = False

    def reload_tick_values(self, record, observed):
        """Full metadata re-audit every 100 ms; live read-only checks each callback.

        Fast observations cannot authorize a write or restore. Any mismatch
        immediately falls back to the existing full resolution path.
        """
        now = monotonic()
        pc, pawn, state, eligible = observed
        witness = record.get('reload_watch')
        if witness is not None and eligible and witness[0] <= now < witness[0] + .1:
            try:
                if self.thread() != record['thread'] or any(
                    record[name]() is None or identity(record[name]()) != record[name+'_id']
                    or obj is None or identity(obj) != record[name+'_id']
                    for name,obj in (('pc',pc),('pawn',pawn),('state',state))):
                    raise ValueError('reload scope changed')
                schema, values = weapon_rates.reload_watch(pawn, record['weapon_scope'], record['tokens'])
                if schema == witness[1] and values == record['expected']:
                    return values, True
            except Exception:
                pass  # Never trust an uncertain fast observation.
        record.pop('reload_watch', None)
        _, values, eligible = self.resolve(record, observed=observed)
        if eligible:
            weapon_rates.validate_reload_floor(record['weapon_scope'], values)
            try:
                schema, checked = weapon_rates.reload_watch(pawn, record['weapon_scope'], record['tokens'])
                if checked == values:
                    record['reload_watch'] = (now, schema)
            except Exception:
                pass  # Unsupported lightweight observation retains full audit.
        return values, eligible

    def tick(self, permitted, *, observed=None, follow_weapon=False, follow_shield=False, follow_gadget=False):
        if self.busy or not self.records or self.fault:
            return
        transitioned = set()
        self.busy = True
        try:
            if self.stop_pending is not None or not permitted:
                self.restore_all(self.stop_pending or 'session permission removed')
                return
            # One fresh read-only context per callback; writes/restores always re-resolve.
            try:
                observed = self.context() if observed is None else observed
            except Exception as exc:
                self.restore_all('context check failed: ' + str(exc)[:100])
                return
            for key, record in tuple(self.records.items()):
                try:
                    light_reload = key == 'reload' and follow_weapon
                    if light_reload:
                        values, eligible = self.reload_tick_values(record, observed)
                    else:
                        _, values, eligible = self.resolve(record, observed=observed)
                    if not eligible:
                        if observed[3] and key == 'slide_speed':
                            if not self.restore(key, 'slide ended; original restored'):
                                self.restore_all('slide restoration failed')
                                return
                            transitioned.add(key)
                            continue
                        # Only persistent weapon controls may follow ordinary weapon changes.
                        # resolve already proved the original session/pawn and exact old behavior.
                        if follow_weapon and observed[3] and key in weapon_rates.WEAPON_KEYS:
                            if not self.restore(key, 'weapon transition; original restored'):
                                self.restore_all('weapon restoration failed')
                                return
                            transitioned.add(key)
                            continue
                        if follow_shield and observed[3] and key in shield_rates.KEYS:
                            if not self.restore(key, 'shield transition; original restored'):
                                self.restore_all('shield restoration failed')
                                return
                            transitioned.add(key)
                            continue
                        if follow_gadget and observed[3] and key == gadget_rates.KEY:
                            if not self.restore(key, 'grenade gadget transition; original restored'):
                                self.restore_all('grenade restoration failed')
                                return
                            transitioned.add(key)
                            continue
                        self.restore_all('session or pawn changed')
                        return
                    if key in shield_rates.KEYS:
                        shield_rates.validate_readback(record['shield_scope'][0](), key, values[0])
                    if key in ('lifesteal_rate', 'lifesteal_fraction') and lifesteal_peer_context(key, record['pawn'](), record['baseline'], values, record['tokens']) != record['life_context']:
                        raise ValueError('life-steal rate/cap changed')
                    if key == 'overshield_duration' and validate_overshield(record['pawn'](), record['baseline'], values) != record['overshield_context']:
                        raise ValueError('overshield base changed')
                    if key in weapon_rates.AMMO_KEYS:
                        weapon_rates.validate_ammo(record['weapon_scope'])
                    if key == 'reload' and not light_reload:
                        weapon_rates.validate_reload_floor(record['weapon_scope'], values)
                    if values != record['expected'] and not (key in GROUND_KEYS and values == record['baseline']):
                        self.restore_all('engine or another writer changed active field; no reapply')
                        return
                except Exception as exc:
                    self.restore_all('context check failed: ' + str(exc)[:100])
                    return
            return transitioned
        finally:
            self.busy = False
