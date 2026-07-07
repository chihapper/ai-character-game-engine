# Quaternius monsters (CC0 — committed)

Animated low-poly monsters by **Quaternius** (https://quaternius.com), fetched as self-contained
GLBs via poly.pizza (each model page displays "Licence: CC0 1.0"). CC0 requires no attribution —
credited anyway because the packs are excellent.

| File | Source model page | Native pack |
|---|---|---|
| `Goblin.glb` | https://poly.pizza/m/OdCOFSmEhl | standalone upload |
| `Wolf.glb`   | https://poly.pizza/m/P1gU3Qkr9r | Ultimate Animated Animals |
| `Spider.glb` | https://poly.pizza/m/yRYJiAJyiM | Easy Enemy Pack |
| `Rat.glb`    | https://poly.pizza/m/iltq5bVNaV | Easy Enemy Pack |

Animations ship EMBEDDED in each GLB (FBX2glTF export — clip names carry armature prefixes like
`CharacterArmature|...|Attack`; world3d.gd's exact→prefix→substring matcher handles them).
Typical set: Attack / Death / HitRecieve (sic) / Idle / Jump / Run / Walk.

Why these four: the two shipped slices can only field Goblins (vault) and Cinder-husks
(emberdeep — mapped to a tinted KayKit skeleton); Wolf/Spider/Rat future-proof the low-CR
beast tier for the next slice. Scale differs from KayKit — world3d.gd normalizes each model
to a target height at spawn instead of assuming the kit grid.
