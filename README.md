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


## R8 (0.7.7) rarity experiment

Existing MIT Loot Treadmill source (Noah Lincke), pinned 4852b34ac82c86c3093192fb029edab495fbb63a, maps CommonModifier and UncommonModifier and uses baseline-relative fractional weights. Its profiles.py (blob 9f80f00524ed913a209a5bf837fa0c387be02129) explicitly uses zero for low rarities. https://github.com/noahlincke/bl4-loot-treadmill/blob/4852b34ac82c86c3093192fb029edab495fbb63a/LootTreadmill/profiles.py . Independent adaptation uses existing solo world-session rarity controller; common/uncommon 0–10x, rare/epic/legendary 0.1–10x, step 0.1, optional numeric entry and 1x restoration. New flags default off. Not guaranteed drop probabilities; actual gameplay and numeric binding unverified. XP/cash/Eridium/overall luck remain preview-only. No original community assets or global asset changes, no grants or saves. Local mocked regressions 274/274.


## R9 (0.7.8) pearlescent experiment

Independent optional pearlescent rarity weight, 0.1–10x with 0.1 steps, based on the MIT Loot Treadmill field mapping and baseline-relative weights at https://github.com/noahlincke/bl4-loot-treadmill/tree/4852b34ac82c86c3093192fb029edab495fbb63a/LootTreadmill . Unique reflected identity required; ambiguous/missing fields refuse activation. Existing solo-world controller, restoration and R8 settings retained. No new reward or save writes. Native availability and actual gameplay unverified. 287 mocked regressions passed locally.


## R10 (0.7.9) local gravity experiment

Independent 0.5–1.5x baseline-relative local CharacterMovement.GravityScale control, default off, existing ownership and restoration guards. Community evidence: Apache-2.0 Apex Movement by Kevin-hDev, pinned heavier_fall.py https://github.com/kevin-hDev/Mods-Borderlands-4/blob/897c99eef4cd6d91637816d101456d59f4fb920f/apex_movement/apex_movement/heavier_fall.py reports changed jump timing and height. No shared jump definition writes or upstream code copied. Lower gravity can change jump height and airborne time; not an exact height multiplier. Actual gameplay unverified. Existing progression and rarity controls unchanged. 300 local mock tests pass.
