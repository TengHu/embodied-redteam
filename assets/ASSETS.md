# 3D assets for the robotdog sim

| asset | source | license | used by |
|---|---|---|---|
| `menagerie_go2/` (go2.xml + assets/*.obj) | MuJoCo Menagerie `unitree_go2` (+ a `head` camera added to the base) | see `go2_LICENSE` (Unitree, BSD-3) | the live MuJoCo scene (run.py) |
| `kenney_gltf/*.glb` | Kenney Furniture Kit (kenney.nl) | CC0 | spare (three.js room, not currently wired) |
| `go2_policy/go1_joystick.onnx` | Go1 joystick locomotion policy (google-deepmind/mujoco_playground, `experimental/sim2sim/onnx/go1_policy.onnx`); runs on the Go2 body | Apache-2.0 | `locomotion.py` RLPolicy (`--policy rl`) |
| `characters/*.glb` | Kenney Blocky Characters (kenney.nl) | CC0 | spare |

The Go2 renders live in MuJoCo (both the dog's head camera and a chase camera),
so there is no baked GLB. Furniture in the scene is MuJoCo primitives; the Kenney
glTF packs are kept in case we rebuild a three.js room.
