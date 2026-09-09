"""replica_room1.py — a photoreal room (ReplicaCAD FRL apartment) + the dog, nothing
else. OVERLAY mode (see README 'Importing an external 3D resource'): MuJoCo carries only
a flat floor for physics; three.js draws the room GLB (assets/replica/room.glb) and the
dog. The room lives ONLY in three.js — it is never a MuJoCo geom."""

from scenes.base import Scene

_DOG = (1.0, 0.0)

_MATERIALS = """\
    <material name="floormat" rgba="0.5 0.5 0.5 1"/>
"""

# physics-only floor; three.js skips drawing it (the room GLB provides the visible floor)
_WORLDBODY = """\
    <geom name="floor" type="plane" size="20 20 0.1" material="floormat"/>"""

SCENE = Scene(
    name="replica_room1",
    dog_start=_DOG,
    target_xy=None,
    materials=_MATERIALS,
    worldbody=_WORLDBODY,
    screen_text={"control": "", "experiment": ""},
    room_glb="replica/room.glb",
)
