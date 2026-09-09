"""castle.py — a big photoreal hall (Skokloster Castle, a Habitat test scan) + the dog,
nothing else. OVERLAY mode (see README 'Importing an external 3D resource'): MuJoCo carries
only a flat floor for physics; three.js draws the room GLB (assets/replica/castle.glb) and
the dog. Much larger than the apartment: ~18 x 24 m footprint, 7 m ceilings. The scan is
Z-up, so the scene declares room_up='z' and three.js rotates it upright."""

from scenes.base import Scene

_DOG = (0.0, -13.0)   # near the center of the castle footprint (see room_up note)

_MATERIALS = """\
    <material name="floormat" rgba="0.5 0.5 0.5 1"/>
"""

# physics-only floor; three.js skips drawing it (the room GLB provides the visible floor)
_WORLDBODY = """\
    <geom name="floor" type="plane" size="30 30 0.1" material="floormat"/>"""

SCENE = Scene(
    name="castle",
    dog_start=_DOG,
    target_xy=None,
    materials=_MATERIALS,
    worldbody=_WORLDBODY,
    screen_text={"control": "", "experiment": ""},
    room_glb="replica/castle.glb",
    room_up="z",
    room_indoor=True,   # roofed hall: view from inside, camera by the dog
)
