// ─────────────────────────────────────────────────────────────
//  시각화 자료 "전체" — 캐논 6뷰(GET /projects/{id}/canon?view=) 렌더러.
//
//  캐논은 저장(saved)된 회차들이 쌓은 현재 설정이다. 항목마다 entity_key(회차 사이에서
//  같은 항목을 잇는 키)·source_chapter(이 버전이 들어온 회차)가 있고, 인물·공간에는 attrs 가 있다.
//  화면 스타일은 회차별 시각화(script.js 렌더러)와 같은 클래스를 쓴다.
// ─────────────────────────────────────────────────────────────

// 화면 카테고리 버튼(data-category) → 캐논 view
export const CANON_VIEW_OF = {
  worldview: "worldview",
  character: "characters",
  time: "timeline",
  space: "spaces",
  event: "events",
  foreshadow: "foreshadowing",
};

function esc(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function emptyHtml() {
  return `<p class="visual-placeholder">아직 저장된 캐논이 없어요. 회차를 검토·저장하면 채워집니다.</p>`;
}

// 출처 회차 · entity_key 한 줄
function metaRow(it, extra = "") {
  const parts = [];
  if (it.source_chapter != null) parts.push(`출처 ${it.source_chapter}화`);
  if (it.version != null && it.version > 1) parts.push(`버전 ${it.version}`);
  if (extra) parts.push(extra);
  const key = it.entity_key ? `<code class="canon-key">${esc(it.entity_key)}</code>` : "";
  return `<div class="wv-meta-row canon-meta">${esc(parts.join(" · "))}${key}</div>`;
}

function attrsList(attrs, skip = []) {
  if (!attrs || typeof attrs !== "object") return "";
  const rows = Object.entries(attrs)
    .filter(([k, v]) => !skip.includes(k) && v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `<span class="wv-trait-chip" title="${esc(k)}">${esc(Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : v)}</span>`)
    .join("");
  return rows ? `<div class="wv-chip-row"><span class="wv-chip-label">속성</span>${rows}</div>` : "";
}

function worldviewHtml(data) {
  const items = data.items || [];
  if (!items.length) return emptyHtml();
  return `<div class="issue-list">${items
    .map(
      (it) => `
      <div class="issue-card">
        <div class="issue-header"><span class="dot dot-teal"></span><span>${esc(it.item || "내용 없음")}</span></div>
        ${it.detail ? `<p class="issue-desc">${esc(it.detail)}</p>` : ""}
        ${metaRow(it)}
      </div>`
    )
    .join("")}</div>`;
}

function timelineHtml(data) {
  const items = [...(data.items || [])].sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
  if (!items.length) return emptyHtml();
  return `<div class="timeline">${items
    .map(
      (it, i) => `
      <div class="timeline-item">
        <div class="timeline-rail">
          <span class="timeline-node">${it.order_index ?? i + 1}</span>
          ${i < items.length - 1 ? `<span class="timeline-line"></span>` : ""}
        </div>
        <div class="timeline-content">
          <div class="timeline-header"><span class="timeline-expression">${esc(it.time_value || it.scene_label || "내용 없음")}</span></div>
          ${it.scene_label && it.time_value ? `<p class="issue-desc">${esc(it.scene_label)}</p>` : ""}
          ${metaRow(it)}
        </div>
      </div>`
    )
    .join("")}</div>`;
}

function spacesHtml(data) {
  const items = data.items || [];
  if (!items.length) return emptyHtml();
  return `<div class="issue-list">${items
    .map(
      (it) => `
      <div class="issue-card">
        <div class="issue-header"><span class="dot dot-green"></span><span>${esc(it.place || it.scene_label || "이름 없음")}</span></div>
        ${it.attrs?.description ? `<p class="issue-desc">${esc(it.attrs.description)}</p>` : ""}
        ${attrsList(it.attrs, ["description"])}
        ${metaRow(it, it.place && it.scene_label ? it.scene_label : "")}
      </div>`
    )
    .join("")}</div>`;
}

function eventsHtml(data) {
  const items = [...(data.items || [])].sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
  if (!items.length) return emptyHtml();
  return `<div class="issue-list">${items
    .map(
      (it) => `
      <div class="issue-card">
        <div class="issue-header"><span class="dot dot-red"></span><span>${esc(String(it.order_index ?? ""))}. ${esc(it.label || "제목 없음")}</span></div>
        ${it.stage ? `<div class="wv-meta-row">단계: ${esc(it.stage)}</div>` : ""}
        ${metaRow(it)}
      </div>`
    )
    .join("")}</div>`;
}

// 인물: 관계 그래프(노드·엣지) + 인물 카드(attrs)
function charactersHtml(data) {
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  if (!nodes.length) return emptyHtml();

  const W = 640, H = 420, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 70;
  const pos = {};
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    pos[n.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });
  const lines = edges
    .map((e) => {
      const a = pos[e.from], b = pos[e.to];
      if (!a || !b) return "";
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="canon-edge"/>
              <text x="${mx}" y="${my}" class="canon-edge-label">${esc(e.relation)}</text>`;
    })
    .join("");
  const circles = nodes
    .map((n) => {
      const p = pos[n.id];
      return `<g><title>${esc(n.entity_key || n.id)}</title>
        <circle cx="${p.x}" cy="${p.y}" r="34" class="canon-node"/>
        <text x="${p.x}" y="${p.y - 2}" class="canon-node-name">${esc(n.name)}</text>
        <text x="${p.x}" y="${p.y + 14}" class="canon-node-group">${esc(n.group || "")}</text>
      </g>`;
    })
    .join("");
  const graph = `<svg class="canon-graph" viewBox="0 0 ${W} ${H}">${lines}${circles}</svg>`;

  const nameOf = Object.fromEntries(nodes.map((n) => [n.id, n.name]));
  const cards = nodes
    .map((n) => {
      const attrs = n.attrs || {};
      const traits = (attrs.traits || []).map((t) => `<span class="wv-trait-chip">${esc(t)}</span>`).join("");
      const aliases = (attrs.aliases || []).join(", ");
      const rels = edges
        .filter((e) => e.from === n.id || e.to === n.id)
        .map((e) => {
          const other = e.from === n.id ? e.to : e.from;
          return `<span class="wv-trait-chip">${esc(nameOf[other] || other)} · ${esc(e.relation || "관계")}</span>`;
        })
        .join("");
      return `
      <div class="character-card">
        <div class="character-card-top">
          <div class="character-card-titles">
            <div class="character-name-row"><span class="character-name">${esc(n.name || "이름 없음")}</span></div>
            ${aliases ? `<div class="wv-aliases">${esc(aliases)}</div>` : ""}
            ${n.group ? `<div class="wv-aliases">${esc(n.group)}</div>` : ""}
          </div>
        </div>
        ${attrs.description ? `<p class="issue-desc">${esc(attrs.description)}</p>` : ""}
        ${traits ? `<div class="wv-chip-row"><span class="wv-chip-label">특징</span>${traits}</div>` : ""}
        ${attrsList(attrs, ["traits", "aliases", "description"])}
        ${rels ? `<div class="wv-chip-row"><span class="wv-chip-label">관계</span>${rels}</div>` : ""}
        ${metaRow(n)}
      </div>`;
    })
    .join("");

  return `${graph}<div class="character-grid">${cards}</div>`;
}

function foreshadowingHtml(data) {
  const items = data.items || [];
  if (!items.length) return emptyHtml();
  const byParent = {};
  items.forEach((it) => {
    const k = it.parent_id || "__root__";
    (byParent[k] = byParent[k] || []).push(it);
  });
  const node = (it) => {
    const kids = byParent[it.id] || [];
    return `<li>
      <span class="canon-fnode canon-fnode--${esc(it.kind)}" title="${esc(it.entity_key || "")}">
        <b>${it.kind === "setup" ? "설치" : "회수"}</b> ${esc(it.label)}
        <small>${it.source_chapter != null ? it.source_chapter + "화" : ""}</small>
      </span>
      ${kids.length ? `<ul>${kids.map(node).join("")}</ul>` : ""}
    </li>`;
  };
  const roots = byParent["__root__"] || [];
  return `<ul class="canon-ftree">${roots.map(node).join("")}</ul>`;
}

const RENDERERS = {
  worldview: worldviewHtml,
  characters: charactersHtml,
  timeline: timelineHtml,
  spaces: spacesHtml,
  events: eventsHtml,
  foreshadowing: foreshadowingHtml,
};

/** 캐논 view 응답 → HTML */
export function renderCanonView(view, data) {
  const render = RENDERERS[view];
  return render ? render(data || {}) : `<p class="visual-placeholder">준비 중인 항목이에요.</p>`;
}
