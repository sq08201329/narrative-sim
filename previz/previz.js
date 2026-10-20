import * as THREE from './lib/three.module.js';

const DATA = window.PREVIZ_DATA;
const TYPE_LABEL = {
  dialogue: '对白', inner_voice: '内心', action: '动作',
  scene_change: '场景', narration: '旁白',
};

// ---------- 场景搭建（占位几何，与创作无关） ----------
const stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(devicePixelRatio);
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x14171c);
scene.fog = new THREE.Fog(0x14171c, 12, 30);

const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 100);

scene.add(new THREE.AmbientLight(0xffffff, 0.45));
const lamp = new THREE.DirectionalLight(0xffe0b0, 1.1);
lamp.position.set(3, 6, 4);
scene.add(lamp);

const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(24, 24),
  new THREE.MeshStandardMaterial({ color: 0x3a2f26 }));
floor.rotation.x = -Math.PI / 2;
scene.add(floor);

const wall = new THREE.Mesh(
  new THREE.PlaneGeometry(24, 6),
  new THREE.MeshStandardMaterial({ color: 0x2c2620 }));
wall.position.set(0, 3, -6);
scene.add(wall);

// 两张桌子
for (const x of [-2.5, 2.5]) {
  const table = new THREE.Mesh(
    new THREE.CylinderGeometry(0.9, 0.9, 0.12, 20),
    new THREE.MeshStandardMaterial({ color: 0x5a4632 }));
  table.position.set(x, 0.75, -1);
  scene.add(table);
  const leg = new THREE.Mesh(
    new THREE.CylinderGeometry(0.08, 0.08, 0.75, 8),
    table.material);
  leg.position.set(x, 0.37, -1);
  scene.add(leg);
}
// 灯笼
for (const x of [-4, 0, 4]) {
  const l = new THREE.Mesh(
    new THREE.SphereGeometry(0.22, 12, 12),
    new THREE.MeshStandardMaterial({ color: 0xff5533, emissive: 0xaa2200 }));
  l.position.set(x, 3.6, -4);
  scene.add(l);
}

// ---------- 角色（胶囊 + 名牌） ----------
function makeNameSprite(text, color) {
  const c = document.createElement('canvas');
  c.width = 256; c.height = 64;
  const g = c.getContext('2d');
  g.font = 'bold 34px "Microsoft YaHei"';
  g.textAlign = 'center';
  g.fillStyle = color;
  g.fillText(text, 128, 44);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(c), transparent: true }));
  sp.scale.set(1.6, 0.4, 1);
  return sp;
}

const actors = {};
for (const ch of DATA.characters) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.32, 0.9, 6, 12),
    new THREE.MeshStandardMaterial({ color: new THREE.Color(ch.color) }));
  body.position.y = 0.95;
  g.add(body);
  const tag = makeNameSprite(ch.name, ch.color);
  tag.position.y = 2.1;
  g.add(tag);
  // 固定槽位：沿弧线排开
  const n = DATA.characters.length;
  const angle = (ch.slot - (n - 1) / 2) * 0.55;
  g.position.set(Math.sin(angle) * 3.2, 0, -Math.cos(angle) * 1.2 + 0.6);
  g.userData.body = body;
  scene.add(g);
  actors[ch.asset_id] = g;
}

// ---------- 机位 ----------
function cameraFor(shot, focus) {
  const f = focus ? focus.position : new THREE.Vector3(0, 1, 0);
  const head = new THREE.Vector3(f.x, 1.4, f.z);
  switch (shot) {
    case 'close_up':
      return { pos: head.clone().add(new THREE.Vector3(0.4, 0.35, 2.0)), look: head };
    case 'medium':
      return { pos: head.clone().add(new THREE.Vector3(1.2, 0.9, 3.6)), look: head };
    case 'pan':
      return { pos: new THREE.Vector3(-5.5, 2.4, 6.5), look: new THREE.Vector3(0, 1.2, 0) };
    case 'wide':
    default:
      return { pos: new THREE.Vector3(0, 3.4, 8.5), look: new THREE.Vector3(0, 1.1, 0) };
  }
}

// ---------- 播放引擎 ----------
const events = DATA.events;
let idx = 0, playing = false, t = 0, speed = 1;
const progress = document.getElementById('progress');
progress.max = events.length - 1;

document.getElementById('title').textContent =
  `${DATA.title} — ${DATA.scene ? DATA.scene.name : ''}（${events.length} 事件）`;

function focusOf(ev) {
  return ev.characters.length ? actors[ev.characters[0]] : null;
}

function show(i) {
  idx = Math.max(0, Math.min(events.length - 1, i));
  t = 0;
  const ev = events[idx];
  for (const id in actors) actors[id].userData.body.material.emissive.setHex(0);
  const focus = focusOf(ev);
  if (focus) focus.userData.body.material.emissive.setHex(0x333333);
  const cam = cameraFor(ev.camera, focus);
  camera.userData.from = camera.position.clone();
  camera.userData.to = cam.pos;
  camera.userData.look = cam.look;

  const label = TYPE_LABEL[ev.type] || ev.type;
  const who = ev.characters.map(c => DATA.characters.find(x => x.asset_id === c)?.name || c).join('、');
  document.getElementById('meta').textContent =
    `事件 ${idx + 1}/${events.length} · tick ${ev.tick} · ${ev.camera} · ${ev.duration_s}s` +
    (ev.emotion ? ` · 情绪：${ev.emotion}` : '');
  document.getElementById('subtitle').innerHTML =
    `<span class="tag t-${ev.type}">${label}</span><b>${who}</b> ${ev.content}`;
  progress.value = idx;
}

const btn = document.getElementById('play');
btn.onclick = () => { playing = !playing; btn.textContent = playing ? '⏸' : '▶'; };
document.getElementById('prev').onclick = () => show(idx - 1);
document.getElementById('next').onclick = () => show(idx + 1);
progress.oninput = () => show(+progress.value);
document.getElementById('speed').onchange = e => speed = +e.target.value;
onkeydown = e => {
  if (e.code === 'Space') { e.preventDefault(); btn.onclick(); }
  if (e.code === 'ArrowLeft') show(idx - 1);
  if (e.code === 'ArrowRight') show(idx + 1);
};

const clock = new THREE.Clock();
function loop() {
  requestAnimationFrame(loop);
  const dt = Math.min(clock.getDelta(), 0.1);
  if (playing) {
    t += dt * speed;
    if (t >= events[idx].duration_s) {
      if (idx < events.length - 1) show(idx + 1);
      else { playing = false; btn.textContent = '▶'; }
    }
  }
  // 相机缓动
  const k = 1 - Math.pow(0.02, dt);
  if (camera.userData.to) {
    camera.position.lerp(camera.userData.to, k);
    camera.lookAt(camera.userData.look);
  }
  renderer.render(scene, camera);
}

onresize = () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
};

show(0);
playing = true;
btn.textContent = '⏸';
loop();
