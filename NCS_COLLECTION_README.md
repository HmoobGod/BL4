# BL4 priority-feature data collection (development only)

Purpose: acquire the actual inventory-part/aspect, attribute and loot definitions missing from the existing PhaseLoot balance-table template. The archive is for private research on a legally installed local game. This is not an SDKMOD, does not launch BL4, does not read saves, and does not alter PAKs or install any game changes. No upstream code, game assets or Oodle DLL are included.

## Inputs and usage

1. Close the game. From your own installed copy, use the real Borderlands 4 game root (the folder containing `OakGame`). Python 3.11+ is required. Save the upstream reader as `pakncs.py` from this exact source: https://raw.githubusercontent.com/lagarrueal/borderlands4-save-editor/4e25cc3b2e540c1265f77eac7ba8b71363e012fb/tools/pakncs.py . The collector verifies the exact Git blob `55f7b3766afba4b7954e044acce055f4e1ec203a` before loading that code. Review the upstream code yourself if desired; it is an external dependency, not bundled or modified.
2. From the directory containing the collector and reader, use PowerShell (substitute your actual installation path):

```powershell
py .\collect_native_ncs.py --game "C:\Program Files (x86)\Steam\steamapps\common\Borderlands 4" --backend .\pakncs.py --output .\BL4_Native_Evidence.zip
```

If the PAK entries are compressed, find the trusted installed `oo2core_9_win64.dll` in your own game's installation and add `--oodle "C:\actual\path\oo2core_9_win64.dll"`. No DLL is loaded implicitly. If your installation has separately downloaded official patches, supply `--patch-root` with the real official patch directory (the parent of its patch-version folders). No mod directory is needed. Use a new output filename outside those source directories; existing output is not overwritten.

3. Place the resulting `BL4_Native_Evidence.zip` in the private project Drive Mods Info folder. Do not publish it. The manifest lists selected types, source PAK names, entry paths, SHA-256 and missing coverage (a missing type is not proof of its absence in the full game). ChatGPT can then reuse the existing offline decoder and reader to inspect the actual definitions. No repeated manual transfers between chats are needed.

## Limits

The collector selects only recognized `Nexus-Data-` inventory, attribute, UI stat, luck/loot configuration and resource-pool families, using base PAK names and recognized numbered official patches. Some family names are candidates; the real installation may name files differently or omit some types. No inventory-effect-to-runtime-consumer mapping is assumed. It reads the selected winning entries only; deletion markers shadow older copies. If an index cannot be read, a selected entry is ambiguous, a payload is invalid, or the PAK changes while reading, it stops rather than silently falling back. The upstream reader is reviewed at a pinned source identity but this wrapper has **not** been run on a real BL4 installation. Only synthetic tests validate collection behavior. A real installation might contain stub or unsupported archives or different naming conventions; report the exact error rather than forcing extraction. Output has a 128 MiB per-file and 512 MiB total limit.

Reference: https://book.bl4.dev/06-ncs-format.html (known NCS file types), https://book.bl4.dev/07-data-extraction.html (inventory data extraction), https://github.com/lagarrueal/borderlands4-save-editor/blob/4e25cc3b2e540c1265f77eac7ba8b71363e012fb/tools/pakncs.py (external PAK reader), https://github.com/lagarrueal/borderlands4-save-editor/blob/4e25cc3b2e540c1265f77eac7ba8b71363e012fb/tools/extract_game_data.py (upstream extraction workflow).
