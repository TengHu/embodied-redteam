"""apartment.py — a large furnished apartment (Habitat 'apartment_1' scan) + the dog,
nothing else. OVERLAY mode (see README 'Importing an external 3D resource'): MuJoCo carries
only a flat floor for physics; three.js draws the room GLB (assets/replica/apartment_1.glb)
and the dog. A real photoreal apartment with a living room, ~8 x 11 m footprint. The scan is
Z-up, so the scene declares room_up='z' and three.js rotates it upright."""

from scenes.base import Scene

_DOG = (3.0, -2.8)   # near the center of the apartment footprint (tuned to the living room)

_MATERIALS = """\
    <material name="floormat" rgba="0.5 0.5 0.5 1"/>
"""

# physics-only floor; three.js skips drawing it (the room GLB provides the visible floor)
_WORLDBODY = """\
    <geom name="floor" type="plane" size="20 20 0.1" material="floormat"/>"""

SCENE = Scene(
    name="apartment",
    dog_start=_DOG,
    target_xy=None,
    materials=_MATERIALS,
    worldbody=_WORLDBODY,
    screen_text={"control": "", "experiment": ""},
    room_glb="replica/apartment_1.glb",
    room_up="z",
    room_light=2.5,   # the scan is a dim capture; brighten it (isolated to this scene)
    room_indoor=True,   # roofed interior: view from inside, camera by the dog
)
