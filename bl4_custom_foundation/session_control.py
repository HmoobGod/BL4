"""Single owner of persistent gameplay fields; fail closed on drift or lost context.
No SDK imports, background threads, raw memory, rewards or save writes.
"""
from .gameplay_fields import FEATURES, RARITY_KEYS, read_fields, target_values, identity


from .ground_speed import floor_target

# R7: explicit elemental-only experiments; general damage remains HOLD.
DAMAGE_HOLD = frozenset(('damage',))

class Controller:
    def __init__(self, context, weak_pointer, report, thread):
        self.context = context
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
        _, tokens, baseline = read_fields(key, pawn, state, pc)
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
                    expected=baseline, owned=[{v} for v in baseline], thread=self.thread())

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
        fields, tokens, values = read_fields(record['key'], pawn, state, pc)
        if tokens != record['tokens']:
            raise ValueError('reflected field identity changed')
        return fields, values, eligible and same_pawn

    def write_one(self, record, index, value, *, applying):
        fields, values, eligible = self.resolve(record)
        if applying and not eligible:
            raise ValueError('session became ineligible')
        if any(v not in allowed for v, allowed in zip(values, record['owned'], strict=True)):
            raise ValueError('unexpected foreign value; refused to overwrite')
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
            _, values, _ = self.resolve(record)
            if any(v not in allowed for v, allowed in zip(values, record['owned'], strict=True)):
                raise ValueError('unexpected foreign value; refused to overwrite')
            for i, base in enumerate(record['baseline']):
                self.write_one(record, i, base, applying=False)
            _, values, _ = self.resolve(record)
            if values != record['baseline']:
                raise ValueError('baseline readback mismatch')
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
        if not result:
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
        self.busy = True
        try:
            if key not in FEATURES or key in DAMAGE_HOLD:
                raise ValueError('feature HOLD')
            _, lo, hi = FEATURES[key]
            # Validate input even when selecting vanilla.
            target_values(key, (1.,), ((1, 'dummy', 'ZDoubleProperty'),), selection)
            if selection == 1:
                result = self.restore(key, '1x selected')
                if not result:
                    for other in tuple(self.records):
                        if other != key:
                            self.restore(other, 'another feature faulted')
                return result
            if self.stop_pending is not None:
                raise ValueError('restoration pending')
            record = self.records.get(key) or self.capture(key)
            _, values, eligible = self.resolve(record)
            # Ground animation maintenance already accepts the captured baseline
            # as an engine reset. Allow the same exact reset during a live update,
            # but never adopt a different value or a replacement object.
            baseline_reset = key == 'walk_speed' and key in self.records and values == record['baseline']
            if not eligible or (values != record['expected'] and not baseline_reset):
                raise ValueError('session or owned value changed')
            targets = (floor_target(record['baseline'], record['tokens'], selection, ground_sprinting)
                       if key == 'walk_speed' else target_values(key, record['baseline'], record['tokens'], selection))
            if values == targets and key != 'walk_speed':
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
        record = self.records.get('walk_speed')
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
            target = floor_target(record['baseline'], record['tokens'], record['selection'], sprint)
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

    def tick(self, permitted, *, observed=None):
        if self.busy or not self.records or self.fault:
            return
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
                    _, values, eligible = self.resolve(record, observed=observed)
                    if not eligible:
                        self.restore_all('session or pawn changed')
                        return
                    if values != record['expected'] and not (key == 'walk_speed' and values == record['baseline']):
                        self.restore_all('engine or another writer changed active field; no reapply')
                        return
                except Exception as exc:
                    self.restore_all('context check failed: ' + str(exc)[:100])
                    return
        finally:
            self.busy = False
