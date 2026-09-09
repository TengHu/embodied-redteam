"""house.py — a large, clean, DESIGNED interior (an HSSD synthetic house stage) + the dog,
nothing else. OVERLAY mode (see README 'Importing an external 3D resource'): MuJoCo carries
only a flat floor for physics; three.js draws the room GLB (assets/replica/house.glb) and the
dog. Same clean/designed look as replica_room1 but a much bigger floor (~28 x 32 m). The stage
is Y-up (already upright) with its floor at y=0, but its coordinates are offset far from the
origin, so the dog spawns at the house centre and the physics floor sits under it."""

from scenes.base import Scene

_DOG = (99.96, -86.97)   # centre of the largest room (a ~12x7 m living room)

_MATERIALS = """\
    <material name="floormat" rgba="0.5 0.5 0.5 1"/>
"""

# physics-only floor under the dog's room; three.js skips drawing it (the GLB provides the floor)
_WORLDBODY = """\
    <geom name="floor" type="plane" pos="99.96 -86.97 0" size="20 20 0.1" material="floormat"/>"""

SCENE = Scene(
    name="house",
    dog_start=_DOG,
    target_xy=None,
    materials=_MATERIALS,
    worldbody=_WORLDBODY,
    screen_text={"control": "", "experiment": ""},
    room_glb="replica/house.glb",
    room_indoor=True,   # roofed house: view from inside, camera by the dog
    room_light=2.0,     # roof blocks the sun; add fill so the interior/head-cam is well-lit
)
