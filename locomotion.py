"""locomotion.py — the swappable low-level locomotion tier.

The high-level brain (brain.py) issues intent; the go-to controller (run.py) turns
a waypoint into a base-velocity command; THIS module turns that command into gait.
Two interchangeable backends behind one interface:

  * ProceduralTrot — a scripted diagonal trot, kinematic (no physics). Reliable,
    no extra deps.
  * RLPolicy       — a real OSS velocity-tracking policy (MuJoCo Playground's Go1
    joystick policy, `assets/go2_policy/go1_joystick.onnx`, which runs fine on the Go2
    body), run as the standard deploy loop: obs -> policy -> joint targets -> PD torque
    -> mj_step (real physics, 50 Hz), plus an odometry loop so a drive() covers the
    distance it was asked to.

Both expose the same interface used by run.py:
    dog.x, dog.y, dog.yaw          current base pose
    dog.goto_vel(wx, wy)           low-level go-to -> (vx, vy, yaw_rate)
    dog.drive(vx, vy, yaw, dt, blocked)   advance one control tick
    dog.backflip()                 generator: one control tick per yield
    dog.dist_to(xy) / dog.hop()

    make(name, model, data, start) -> Locomotion
"""

from __future__ import annotations

import math
import pathlib

import mujoco
import numpy as np

_HERE = pathlib.Path(__file__).resolve().parent
_POLICY = _HERE / "assets" / "go2_policy" / "go1_joystick.onnx"

# shared motion limits / rates (imported by run.py)
CONTROL_DT = 0.02
BASE_Z = 0.30
MAX_VX, MAX_VY, MAX_YAW = 0.7, 0.6, 1.8


def _smooth(s: float) -> float:
    """Smoothstep easing on [0,1] — soft ends, so a scripted pose blend looks natural."""
    s = max(0.0, min(1.0, s))
    return s * s * (3 - 2 * s)


class Locomotion:
    def __init__(self, model, data, start, start_yaw=0.0):
        self.m, self.d = model, data
        self.x, self.y = start
        self.yaw, self.z = start_yaw, BASE_Z

    def dist_to(self, xy):
        return math.hypot(xy[0] - self.x, xy[1] - self.y)

    def goto_vel(self, wx, wy):
        """Turn to face the goal and walk forward, decelerating on approach and
        turning gently so a physics gait stays upright and doesn't overshoot."""
        dx, dy = wx - self.x, wy - self.y
        d = math.hypot(dx, dy)
        err = (math.atan2(dy, dx) - self.yaw + math.pi) % (2 * math.pi) - math.pi
        yaw_rate = max(-1.2, min(1.2, 2.0 * err))
        # turn in place until roughly facing the goal (stable for a physics gait),
        # then walk straight, decelerating on approach and stopping when arrived.
        if abs(err) > 0.35 or d < 0.35:
            vx = 0.0
        else:
            vx = MAX_VX * min(1.0, d / 0.8)
        return vx, 0.0, yaw_rate

    def drive(self, vx, vy, yaw_rate, dt, blocked):
        raise NotImplementedError

    def hop(self):
        pass


class ProceduralTrot(Locomotion):
    """Kinematic base + scripted diagonal trot. No physics, no deps."""

    def __init__(self, model, data, start, start_yaw=0.0):
        super().__init__(model, data, start, start_yaw)
        mujoco.mj_resetDataKeyframe(model, data, model.key("home").id)
        self.home_legs = self.d.qpos[7:].copy()
        self.legs = self.home_legs.copy()
        self.phase = 0.0
        self._write()

    def _write(self):
        qw, qz = math.cos(self.yaw / 2), math.sin(self.yaw / 2)
        self.d.qpos[0:7] = [self.x, self.y, self.z, qw, 0, 0, qz]
        self.d.qpos[7:] = self.legs
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)

    def drive(self, vx, vy, yaw_rate, dt, blocked):
        self.yaw += yaw_rate * dt
        moved = 0.0
        if not blocked:
            wdx = (vx * math.cos(self.yaw) - vy * math.sin(self.yaw)) * dt
            wdy = (vx * math.sin(self.yaw) + vy * math.cos(self.yaw)) * dt
            self.x += wdx
            self.y += wdy
            moved = math.hypot(wdx, wdy)
        self.phase += moved * 10.0
        legs = self.home_legs.copy()
        if moved > 1e-4:
            off = [0.0, math.pi, math.pi, 0.0]
            for i in range(4):
                th = self.phase + off[i]
                legs[i * 3 + 1] += 0.32 * math.sin(th)
                legs[i * 3 + 2] += 0.60 * max(0.0, math.sin(th))
        self.legs = legs
        self._write()

    def hop(self):
        base = self.z
        for zz in (0.42, 0.55, 0.42, base):
            self.z = zz
            self._write()

    # --- scripted keyframe backflip (kinematic, same qpos-write path as the trot) -------
    # The physics flip lives on RLPolicy; for the kinematic gait we author a multi-phase
    # keyframe trajectory (crouch -> launch -> full backward pitch + tuck -> land).
    _CROUCH_Z, _PEAK_Z = 0.16, 1.05     # wind-up dip, then apex of the airborne arc
    _TUCK_THIGH, _TUCK_CALF = 2.3, -2.6  # legs folded to the belly in flight (within limits)
    _FLIP_TICKS = 3 * 48                 # 48 streamed frames at run.py's every-3-ticks rate

    def backflip(self):
        for k in range(self._FLIP_TICKS + 1):
            self.backflip_pose(k / self._FLIP_TICKS)
            yield

    def backflip_pose(self, u: float) -> None:
        """Write the base pose + leg angles for backflip phase u in [0,1]. The flip is a
        rotation about the BODY pitch axis composed onto the current yaw, so it reads as a
        backflip whatever way the dog is facing. three.js renders straight off this qpos."""
        u = max(0.0, min(1.0, u))
        if u < 0.15:                                    # load: crouch straight down
            self.z = BASE_Z + (self._CROUCH_Z - BASE_Z) * _smooth(u / 0.15)
            pitch = tuck = 0.0
        elif u < 0.85:                                  # flight: one full backward turn
            s = (u - 0.15) / 0.70
            pitch = -2.0 * math.pi * _smooth(s)         # nose up and over, backward
            arc = math.sin(math.pi * s)                 # 0 -> 1 -> 0 vertical arc
            self.z = self._CROUCH_Z + (self._PEAK_Z - self._CROUCH_Z) * arc
            tuck = arc                                  # legs tucked most at the apex
        else:                                           # land: rise from touchdown to stand
            self.z = self._CROUCH_Z + (BASE_Z - self._CROUCH_Z) * _smooth((u - 0.85) / 0.15)
            pitch = tuck = 0.0                          # -2pi has wrapped back to upright
        legs = self.home_legs.copy()
        for i in range(4):
            legs[i * 3 + 1] += (self._TUCK_THIGH - self.home_legs[i * 3 + 1]) * tuck
            legs[i * 3 + 2] += (self._TUCK_CALF - self.home_legs[i * 3 + 2]) * tuck
        self.legs = legs
        qw, qz = math.cos(self.yaw / 2), math.sin(self.yaw / 2)
        qp = np.array([math.cos(pitch / 2), 0.0, math.sin(pitch / 2), 0.0])
        res = np.zeros(4)
        mujoco.mju_mulQuat(res, np.array([qw, 0.0, 0.0, qz]), qp)   # yaw ⊗ body-pitch
        self.d.qpos[0:3] = [self.x, self.y, self.z]
        self.d.qpos[3:7] = res
        self.d.qpos[7:] = self.legs
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)


# policy config (mujoco_playground locomotion/go1/joystick.py + experimental/sim2sim/play_go1_joystick.py)
_DEFAULT = np.array([0.0, 0.9, -1.8] * 4, np.float32)   # Go1 `home` pose = Go2 `home` pose
_KP, _KD, _ACT_SCALE = 35.0, 0.5, 0.5
_DECIMATION = 10          # physics steps per policy step -> 50 Hz at dt=0.002
_JOINT_DAMPING = _KD      # Playground sets dof_damping = Kd (Menagerie's 2.0 makes it drift)
_GO1_ORDER = [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8]      # policy legs FR,FL,RR,RL -> Go2 FL,FR,RL,RR

# Physics backflip: joint-space targets per phase (thigh/calf, front f / hind h), the nose-up
# angle A at which the hind push starts, the rotation L left when un-tucking, and the flip PD
# gain. Found by random search in this sim (40/40 upright landings from perturbed starts).
_FLIP = dict(cth_f=1.744, cca_f=-2.49, cth_h=1.537, cca_h=-2.398,   # crouch
             kth_f=0.519, kca_f=-1.051, A=0.565,                    # front kick; push when rot >= A
             pth_h=0.438, pca_h=-1.194,                             # hind push
             tth=1.962, tca=-2.227, L=1.522,                        # tuck; land when rot >= 2pi - L
             lth=0.972, lca=-2.282, kp=385.8)                       # landing pose; PD gain


def _legs(th_f, ca_f, th_h, ca_h):
    """12 joint targets (abduction 0) from front/hind thigh+calf angles."""
    return np.array([0, th_f, ca_f, 0, th_f, ca_f, 0, th_h, ca_h, 0, th_h, ca_h])


class RLPolicy(Locomotion):
    """Real OSS velocity-tracking policy, physics-stepped (the deploy loop)."""

    def __init__(self, model, data, start, start_yaw=0.0):
        super().__init__(model, data, start, start_yaw)
        import onnxruntime
        self.policy = onnxruntime.InferenceSession(str(_POLICY), providers=["CPUExecutionProvider"])
        self.m.opt.timestep = 0.002
        self.m.dof_damping[6:] = _JOINT_DAMPING
        self.action = np.zeros(12, np.float32)
        self.target = _DEFAULT.copy()
        self.reset(start, start_yaw)

    def reset(self, start, yaw=0.0):
        self.x, self.y = start
        self.yaw = yaw
        self.d.qpos[0:3] = [self.x, self.y, 0.34]
        self.d.qpos[3:7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        self.d.qpos[7:] = _DEFAULT
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)
        # let it settle onto its feet before decisions start
        for _ in range(100):
            self._pd_step()
        self._sync_pose()

    def _pd_step(self, cmd=(0.0, 0.0, 0.0)):
        tau = (self.target - self.d.qpos[7:]) * _KP + (-self.d.qvel[6:]) * _KD
        self.d.ctrl[:] = tau
        mujoco.mj_step(self.m, self.d)

    def _body(self, v):
        """World vector -> body frame (R^T v) for the base quaternion (w, x, y, z)."""
        w, x, y, z = self.d.qpos[3:7]
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                      [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                      [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
        return R.T @ v

    def _policy_step(self, cmd):
        o = _GO1_ORDER
        obs = np.concatenate([self._body(self.d.qvel[0:3]),          # local linvel
                              self.d.qvel[3:6],                       # gyro (body frame)
                              self._body(np.array([0.0, 0.0, -1.0])),  # projected gravity
                              (self.d.qpos[7:] - _DEFAULT)[o],
                              self.d.qvel[6:][o],
                              self.action,
                              np.asarray(cmd)]).astype(np.float32)
        act = self.policy.run(["continuous_actions"], {"obs": obs.reshape(1, -1)})[0][0]
        self.action = act.astype(np.float32)
        self.target = _DEFAULT.copy()
        self.target[o] += act * _ACT_SCALE

    def _sync_pose(self):
        self.x, self.y, self.z = float(self.d.qpos[0]), float(self.d.qpos[1]), float(self.d.qpos[2])
        q = self.d.qpos[3:7]
        self.yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]),
                              1 - 2 * (q[2] ** 2 + q[3] ** 2))

    # Pose tracking: the policy alone under-tracks speed (~60% of a reverse command) and drifts
    # a few degrees per 10 s. Like a real robot's odometry loop, dead-reckon the reference pose
    # the command implies and steer onto it, so a drive() covers the distance it was asked to.
    _K_POS, _K_YAW = 1.5, 2.0              # m/s per m of position error; rad/s per rad of heading
    _MAX_ERR_POS, _MAX_ERR_YAW = 0.3, 0.25 # cap the stored error so a shove/slip can't cause a lunge
    _POLICY_VMAX = 1.0                     # corrected command may exceed the brain's MAX_VX
    _ref = None                            # (x, y, yaw) reference, carried across commands so each
                                           # drive finishes what it asked; None = re-sync to actual

    def drive(self, vx, vy, yaw_rate, dt, blocked):
        if blocked:
            cmd, self._ref = (0.0, 0.0, 0.0), None      # don't fight an obstacle
        else:
            rx, ry, ryaw = self._ref or (self.x, self.y, self.yaw)
            ryaw += yaw_rate * dt
            rx += (vx * math.cos(ryaw) - vy * math.sin(ryaw)) * dt
            ry += (vx * math.sin(ryaw) + vy * math.cos(ryaw)) * dt
            e_yaw = math.atan2(math.sin(ryaw - self.yaw), math.cos(ryaw - self.yaw))
            e_yaw = max(-self._MAX_ERR_YAW, min(self._MAX_ERR_YAW, e_yaw))
            ex, ey = rx - self.x, ry - self.y
            c, s = math.cos(self.yaw), math.sin(self.yaw)
            e_fwd = max(-self._MAX_ERR_POS, min(self._MAX_ERR_POS, ex * c + ey * s))
            e_lat = max(-self._MAX_ERR_POS, min(self._MAX_ERR_POS, -ex * s + ey * c))
            vm = self._POLICY_VMAX
            cmd = (max(-vm, min(vm, vx + self._K_POS * e_fwd)),
                   max(-vm, min(vm, vy + self._K_POS * e_lat)),
                   max(-MAX_YAW, min(MAX_YAW, yaw_rate + self._K_YAW * e_yaw)))
            self._ref = (self.x + e_fwd * c - e_lat * s, self.y + e_fwd * s + e_lat * c,
                         self.yaw + e_yaw)
        self._policy_step(cmd)
        for _ in range(_DECIMATION):
            self._pd_step()
        self._sync_pose()

    def _airborne(self):
        """No foot touching the floor."""
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            if self._floor in (c.geom1, c.geom2) and (c.geom1 in self._feet or c.geom2 in self._feet):
                return False
        return True

    def backflip(self):
        """Physics backflip: an open-loop joint trajectory sequenced by EVENTS (nose-up angle,
        feet leaving the floor, rotation completed) and tracked by stiff PD under mj_step;
        then the policy re-takes the stance. Yields once per control tick."""
        f = _FLIP
        geom = lambda n: mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_GEOM, n)
        self._floor = geom("floor")
        self._feet = {geom(n) for n in ("FL", "FR", "RL", "RR")}
        dt = self.m.opt.timestep
        rot = 0.0                                          # accumulated backward pitch (rad)
        phases = [  # (joint targets, kd, done(elapsed seconds))
            (_legs(f["cth_f"], f["cca_f"], f["cth_h"], f["cca_h"]), 3.0, lambda t: t >= 0.5),
            (_legs(f["kth_f"], f["kca_f"], f["cth_h"], f["cca_h"]), 3.0,
             lambda t: rot >= f["A"] or t >= 0.4),                       # kick: nose comes up
            (_legs(f["tth"], f["tca"], f["pth_h"], f["pca_h"]), 3.0,
             lambda t: self._airborne() or t >= 0.35),                   # hind push -> launch
            (_legs(f["tth"], f["tca"], f["tth"], f["tca"]), 3.0,
             lambda t: rot >= 2 * math.pi - f["L"] or t >= 0.8),         # tuck through the arc
            (_legs(f["lth"], f["lca"], f["lth"], f["lca"]), 6.0, lambda t: t >= 0.4),   # land
        ]
        step = 0
        for tgt, kd, done in phases:
            t0 = step
            while not done((step - t0) * dt):
                self.d.ctrl[:] = (tgt - self.d.qpos[7:]) * f["kp"] - self.d.qvel[6:] * kd
                mujoco.mj_step(self.m, self.d)
                rot -= self.d.qvel[4] * dt                 # backflip = negative body pitch rate
                step += 1
                if step % _DECIMATION == 0:
                    self._sync_pose()
                    yield
        self.action[:] = 0                                 # stale pre-flip action out of the obs
        self._ref = None                                   # the flip moved us: hold the new line
        for _ in range(25):                                # 0.5 s: the policy re-takes the stance
            self.drive(0.0, 0.0, 0.0, CONTROL_DT, False)
            yield


def make(name: str, model, data, start, start_yaw=0.0) -> Locomotion:
    return {"trot": ProceduralTrot, "rl": RLPolicy}[name](model, data, start, start_yaw)
