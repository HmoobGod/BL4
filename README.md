# BL4 Custom

Borderlands 4 Python SDK gameplay tuning for Offline Local Only sessions. R5 (0.7.4) is the initial owner-tested persistent movement baseline. Four gameplay checks passed: activation, automatic movement, live speed adjustment, and restoration. Other features retain their previous test status; FPS and cross-restart persistence are not confirmed.

## Development

Run `python run_regressions.py` with Python 3.11 or later. Tests mock the game and SDK, not actual gameplay. Install packages are maintained separately from this source repository. F8 opens the menu; turn off overlapping tuning mods and enable offline consent only in Offline Local Only. Restore ALL before travel, character or network changes. Do not use gameplay modifications in public or cooperative sessions. The runtime session predicate cannot independently prove privacy.

## Provenance

See `bl4_custom_foundation/SOURCES.md` and the accompanying third-party license files for MIT and Apache-2.0 components and modified integrations. No game binaries, original game assets, SDK distributions, user saves or private gameplay reports are included. Third-party licenses apply to their respective components; this repository does not grant additional rights to third-party material.

## Experimental R6 (0.7.5)

Fire-only reflected modifier is available by explicit opt-in; actual hit damage is unverified. Other outgoing damage, XP and automation remain on HOLD. Preserve R5 on main.


## Experimental R7 (0.7.6)

Four existing MIT Squ1ggs reflected pawn elemental pairs are admitted by explicit individual opt-in: shock, corrosive, cryo and radiation. Fire retained. All new flags default off; no general damage, XP or automation admission. Actual hit effects unverified. 246 mocked regressions passed locally; no native game execution.
