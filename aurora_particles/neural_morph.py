"""Continuous structural morphing for AURORA's neural entity.

The GLSL function is the production path. ``reference_morph_positions`` is a
small NumPy mirror used by deterministic tests and visual diagnostics; it does
not participate in the render loop or allocate per frame.
"""
from __future__ import annotations

import numpy as np


MORPH_GLSL = r"""
mat3 rotY(float a){float c=cos(a),s=sin(a);return mat3(c,0.,-s,0.,1.,0.,s,0.,c);}
mat3 rotX(float a){float c=cos(a),s=sin(a);return mat3(1.,0.,0.,0.,c,-s,0.,s,c);}
mat3 rotZ(float a){float c=cos(a),s=sin(a);return mat3(c,-s,0.,s,c,0.,0.,0.,1.);}
vec3 neuralDeform(vec3 p,float seed,float role,float path){
  float standby=uState.x, listening=uState.y, processing=uState.z, speaking=uState.w;
  float rms=uAudio.x,bass=uAudio.y,mid=uAudio.z,high=uAudio.w;
  float radius=max(length(p.xy),.001);
  float theta=atan(p.y,p.x);
  float outer=clamp(role,0.,1.);
  float core=1.0-smoothstep(.12,.48,radius);
  float slow=uTime*.24;
  float branchPhase=seed*6.2831853;
  float routeArc=sin(clamp(path,0.,1.)*3.1415927);

  /* Always-on coherent life: silhouette drift, branch sway and asymmetry. */
  float branchDrift=sin(theta*3.0+slow+p.z*2.2+branchPhase)+.52*sin(theta*5.0-slow*.71-branchPhase*.7);
  float livingScale=1.0+(.018*sin(uTime*.61)+.030*branchDrift)*(.22+.78*outer);
  p.xy*=livingScale;
  p=rotZ((.028*sin(slow*.83+theta*2.0)+.018*sin(slow*.47-theta*4.0))*outer)*p;
  p.x+=.030*sin(slow*.76+theta*2.0+p.z*2.0)*outer;
  p.y+=.024*cos(slow*.59-theta*3.0)*outer;
  p.z+=.018*sin(slow*.91+theta*2.4+seed*1.7)*(.25+.75*outer);
  vec2 routeNormal=normalize(vec2(-p.y,p.x)+vec2(.001));
  float routeSway=(.030+.034*fract(seed*17.0))*routeArc
      *sin(uTime*(.20+.16*fract(seed*11.0))+branchPhase+path*2.4);
  p.xy+=routeNormal*routeSway*(.45+.55*outer);

  /* STANDBY: compact, breathing and visibly changing its outline. */
  float idleMorph=standby*(.036*sin(uTime*.31+theta*2.0)+.024*cos(uTime*.19-theta*5.0));
  p.xy*=1.0+idleMorph*(.30+.70*outer);
  p.x*=1.0+standby*.045*sin(uTime*.27);
  p.y*=1.0-standby*.038*sin(uTime*.27);
  p*=1.0-standby*.105*outer;

  /* LISTENING: the whole body gathers around a moving point of attention. */
  float listenPull=listening*(.115+.105*rms+.055*bass);
  vec2 attention=vec2(.055*sin(uTime*.53),.035*cos(uTime*.41));
  p.xy=mix(p.xy,attention+p.xy*(.70-.12*outer),listenPull*(.52+.48*outer));
  p.xy*=1.0-listening*(.085+.075*rms)*(.30+.70*outer);
  p.x*=1.0-listening*(.18+.055*mid);
  p.y*=1.0+listening*(.040+.025*bass);
  p*=1.0-listening*core*(.10+.07*rms);
  p=rotZ(listening*outer*(.055*sin(theta*4.0-uTime*.46+branchPhase)-.035))*p;
  p.xy-=routeNormal*listening*routeArc*(.018+.036*rms)*(.35+.65*path);

  /* PROCESSING: compact convergence with a coherent internal re-route. */
  float thinkWave=sin(theta*4.0+uTime*.72)+.45*cos(theta*7.0-uTime*.39);
  p.xy*=1.0-processing*(.075+.060*outer);
  p=rotZ(processing*(.075+.105*outer)*thinkWave)*p;
  p.x+=processing*.040*sin(theta*3.0+uTime*.63)*(outer-core*.3);
  p.y+=processing*.045*cos(theta*2.0-uTime*.51)*(outer-core*.2);
  p.z+=processing*.060*sin(theta*3.0+uTime*.58)*outer;
  p.xy+=routeNormal*processing*routeArc*.055*sin(uTime*.64+branchPhase+path*4.0);

  /* SPEAKING: radial petal openings and an expressive, audio-driven corona. */
  float petal=.5+.5*sin(theta*6.0-uTime*.34+p.z*2.0);
  float speakOpen=speaking*(.100+.060*outer+.055*rms+.030*bass+.045*petal*outer);
  p.xy*=1.0+speakOpen;
  p.x*=1.0+speaking*(.105+.055*petal);
  p.y*=1.0+speaking*(.165+.075*(1.0-petal));
  p.xy+=normalize(p.xy+vec2(.001))*speaking*outer*(.030+.075*rms)*petal;
  p.xy+=routeNormal*speaking*routeArc*(.035+.055*mid)
      *sin(uTime*(.32+.22*fract(seed*9.0))+branchPhase+path*3.0);
  p*=1.0+speaking*core*(.075+.090*rms);
  p=rotZ(speaking*outer*.070*sin(theta*5.0+uTime*.57))*p;
  p.y/=1.0+speaking*.28*abs(p.y);

  /* Audio detail stays secondary to the structural gesture. */
  vec3 radial=normalize(p+vec3(.001));
  float stateCurl=processing*(.030+.075*mid)+listening*.025*mid+speaking*.038*mid;
  p+=vec3(-p.y,p.x,sin(theta*3.0+uTime*.8)*.22)*stateCurl*(.25+.75*outer);
  p+=radial*high*(.005+.014*outer)*sin(uTime*7.0+seed*73.0);
  p=rotY(uTime*(.016+.020*processing))*rotX(sin(uTime*.19)*.050)*p;
  p=p*.78+vec3(0.,.075+speaking*.070,0.);
  p.x/=max(.56,uAspect);
  return p;
}
"""


def reference_morph_positions(
    positions: np.ndarray,
    roles: np.ndarray,
    state: tuple[float, float, float, float],
    audio: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    *,
    time_seconds: float = 0.0,
) -> np.ndarray:
    """CPU reference for structural assertions, excluding camera projection."""
    p = np.asarray(positions, dtype=np.float64).copy()
    outer = np.clip(np.asarray(roles, dtype=np.float64), 0.0, 1.0)
    standby, listening, processing, speaking = map(float, state)
    rms, bass, mid, _high = map(float, audio)
    radius = np.maximum(np.linalg.norm(p[:, :2], axis=1), .001)
    theta = np.arctan2(p[:, 1], p[:, 0])
    core = 1.0 - np.clip((radius - .12) / .36, 0.0, 1.0) ** 2 * (3.0 - 2.0 * np.clip((radius - .12) / .36, 0.0, 1.0))
    slow = time_seconds * .24

    branch_drift = np.sin(theta * 3.0 + slow + p[:, 2] * 2.2) + .52 * np.sin(theta * 5.0 - slow * .71)
    living_scale = 1.0 + (.018 * np.sin(time_seconds * .61) + .030 * branch_drift) * (.22 + .78 * outer)
    p[:, :2] *= living_scale[:, None]
    angle = (.028 * np.sin(slow * .83 + theta * 2.0) + .018 * np.sin(slow * .47 - theta * 4.0)) * outer
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    x, y = p[:, 0].copy(), p[:, 1].copy()
    p[:, 0], p[:, 1] = cos_a * x - sin_a * y, sin_a * x + cos_a * y
    p[:, 0] += .030 * np.sin(slow * .76 + theta * 2.0 + p[:, 2] * 2.0) * outer
    p[:, 1] += .024 * np.cos(slow * .59 - theta * 3.0) * outer

    idle = standby * (.036 * np.sin(time_seconds * .31 + theta * 2.0) + .024 * np.cos(time_seconds * .19 - theta * 5.0))
    p[:, :2] *= (1.0 + idle * (.30 + .70 * outer))[:, None]
    p[:, 0] *= 1.0 + standby * .045 * np.sin(time_seconds * .27)
    p[:, 1] *= 1.0 - standby * .038 * np.sin(time_seconds * .27)
    p *= (1.0 - standby * .105 * outer)[:, None]

    pull = listening * (.115 + .105 * rms + .055 * bass)
    attention = np.array((.055 * np.sin(time_seconds * .53), .035 * np.cos(time_seconds * .41)))
    gathered = attention + p[:, :2] * (.70 - .12 * outer)[:, None]
    mix = pull * (.52 + .48 * outer)
    p[:, :2] = p[:, :2] * (1.0 - mix[:, None]) + gathered * mix[:, None]
    p[:, :2] *= (1.0 - listening * (.085 + .075 * rms) * (.30 + .70 * outer))[:, None]
    p[:, 0] *= 1.0 - listening * (.18 + .055 * mid)
    p[:, 1] *= 1.0 + listening * (.040 + .025 * bass)
    p *= (1.0 - listening * core * (.10 + .07 * rms))[:, None]

    think = np.sin(theta * 4.0 + time_seconds * .72) + .45 * np.cos(theta * 7.0 - time_seconds * .39)
    p[:, :2] *= (1.0 - processing * (.075 + .060 * outer))[:, None]
    angle = processing * (.075 + .105 * outer) * think
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    x, y = p[:, 0].copy(), p[:, 1].copy()
    p[:, 0], p[:, 1] = cos_a * x - sin_a * y, sin_a * x + cos_a * y

    petal = .5 + .5 * np.sin(theta * 6.0 - time_seconds * .34 + p[:, 2] * 2.0)
    opening = speaking * (.100 + .060 * outer + .055 * rms + .030 * bass + .045 * petal * outer)
    p[:, :2] *= (1.0 + opening)[:, None]
    p[:, 0] *= 1.0 + speaking * (.105 + .055 * petal)
    p[:, 1] *= 1.0 + speaking * (.165 + .075 * (1.0 - petal))
    p[:, 1] /= 1.0 + speaking * .28 * np.abs(p[:, 1])
    return p.astype(np.float32)
