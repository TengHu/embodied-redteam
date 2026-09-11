# 3D assets for the robotdog sim

| asset | source | license | used by |
|---|---|---|---|
| `menagerie_go2/` (go2.xml + assets/*.obj) | MuJoCo Menagerie `unitree_go2` (+ a `head` camera added to the base) | see `go2_LICENSE` (Unitree, BSD-3) | the live MuJoCo scene (run.py) |
| `go2_policy/go1_joystick.onnx` | Go1 joystick locomotion policy (google-deepmind/mujoco_playground, `experimental/sim2sim/onnx/go1_policy.onnx`); runs on the Go2 body | Apache-2.0 | `locomotion.py` RLPolicy (`--policy rl`) |
| `human/mei.*` | Renderpeople "Mei" scanned human (OBJ + diffuse) | Renderpeople free sample | the `person` body, drawn by three.js OBJLoader |
| `replica/bigroom.glb` | generated living-room GLB (see scenes/living_room_approach_backflip.py) | — | the overlay room |

The Go2 renders live (MuJoCo server-side, mujoco_wasm + three.js in the browser),
so there is no baked GLB for it. Furniture is drawn from `bigroom.glb`; MuJoCo carries
matching `col_*` box colliders for physics.
