# Progression comparison (read-only)

Independent parser for the observed uncompressed difficulty-struct layout. The original community archives are not included. This is a development tool, not a game mod or gameplay activation mechanism. No SDK/runtime changes.

`python progression_inspect.py inspect /path/to/private/presets.zip` compares raw serialized fields; `python progression_inspect.py profile --xp 2 --cash 3 --loot 4` prints a non-installable independent field intent. Raw values are not established in-game multipliers. Zero means serialized zero/default, not zero rewards. No asset writer, game file changes, or save edits. Unsupported layouts fail closed. The current parser is intentionally limited and does not verify IoStore content hashes, full package schema, current game compatibility or gameplay effects.

Community reference: Caites, Difficulty And Loot Tweaks (https://www.nexusmods.com/borderlands4/mods/1). Author requires permission before modifying/reusing files; only independent inspection code and synthetic fixtures are published. Format references: https://github.com/atenfyr/UAssetAPI/blob/master/UAssetAPI/Unversioned/FUnversionedHeader.cs ; https://github.com/atenfyr/UAssetAPI/blob/master/UAssetAPI/Unversioned/FFragment.cs ; https://github.com/trumank/retoc/blob/master/retoc/src/lib.rs. No third-party code or game assets bundled.

Run `python run_regressions.py` from repository root. Native F8 progression changes remain unavailable pending an owned reversible earned-reward path.
