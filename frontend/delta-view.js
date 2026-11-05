// ─────────────────────────────────────────────────────────────
//  서버 데이터 → 화면 표시 변환 (화면 쪽만. 서버로 되돌리는 정렬·매칭은 없다).
//
//  1) canon_delta(7 카테고리) → 1차 탭 6분류 항목 {title, content, quote}
//     각 항목은 서버 정체성(category = 백엔드 키, entityKey, chapterNo)을 그대로 들고 다닌다.
//     화면은 이 값을 DOM data 속성에 실어 수정·삭제를 그 자리에서 PATCH/DELETE 한다.
//  2) contradictions → 2차 탭 이슈 카드
//  3) 회차 상태 라벨
//
//  수정 규칙: 사용자가 고친 content/quote 는 타입 필드를 건드리지 않고 Delta.note/quote 에만 담는다.
//  → 사람이 쓴 서술이 캐논 데이터(자료정리·시각화)를 바꾸지 않는다. 검토 메모로만 남는다.
// ─────────────────────────────────────────────────────────────

// 화면 6분류의 표시 순서(= script.js NARRATIVE_CATEGORY_ORDER)
const FE_CATEGORIES = ["worldview", "time", "space", "character", "event", "foreshadow"];

// 화면 분류 → 백엔드 canon_delta 키. "인물"만 characters + relations 둘을 받는다
// (관계는 화면에 대응 칸이 없어서 인물 아래에 함께 보여준다).
const BE_KEYS_OF = {
  worldview: ["worldview"],
  time: ["timeline"],
  space: ["spaces"],
  character: ["characters", "relations"],
  event: ["events"],
  foreshadow: ["foreshadowing"],
};

const FORESHADOW_KIND = { setup: "복선 설치", payoff: "복선 회수" };

// attrs(dict) → "키: 값" 한 줄 요약
function attrsSummary(attrs) {
  if (!attrs || typeof attrs !== "object") return "";
  return Object.entries(attrs)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
    .join(" · ");
}

const joinParts = (...parts) => parts.filter(Boolean).join(" · ");

// 백엔드 항목 → 화면에 보여줄 {title, content}. content는 note가 없을 때의 기본값.
const VIEW_OF = {
  worldview: (it) => ({ title: it.item || it.entity_key, content: it.detail || "" }),
  characters: (it) => ({
    title: it.name || it.entity_key,
    content: joinParts(it.group_name, attrsSummary(it.attrs)),
  }),
  relations: (it) => ({
    title: `${it.from_char || "?"} → ${it.to_char || "?"}`,
    content: it.relation || "",
  }),
  timeline: (it) => ({
    title: it.scene_label || it.entity_key,
    content: it.time_value || "",
  }),
  spaces: (it) => ({
    title: it.place || it.scene_label || it.entity_key,
    content: it.place ? it.scene_label || "" : joinParts(attrsSummary(it.attrs)),
  }),
  events: (it) => ({ title: it.label || it.entity_key, content: it.stage || "" }),
  foreshadowing: (it) => ({
    title: it.label || it.entity_key,
    content: FORESHADOW_KIND[it.kind] || it.kind || "",
  }),
};

/**
 * canon_delta(회차 1개) → 화면 6분류 항목.
 * @returns {{[feCategory: string]: Array<{title, content, quote, category, entityKey, chapterNo, body, baseContent}>}}
 *   category = 백엔드 카테고리(PATCH/DELETE 경로), body = 원본 항목(PATCH 는 전체 교체라 필요)
 */
export function deltaToView(canonDelta, chapterNo) {
  const out = {};
  for (const feKey of FE_CATEGORIES) {
    const items = [];
    for (const beKey of BE_KEYS_OF[feKey]) {
      for (const raw of canonDelta?.[beKey] || []) {
        const view = VIEW_OF[beKey](raw);
        items.push({
          title: view.title,
          // 사람이 고쳐 쓴 note가 있으면 그게 우선. 없으면 타입 필드에서 만든 요약.
          content: raw.note || view.content,
          quote: raw.quote || "",
          category: beKey,
          entityKey: raw.entity_key,
          chapterNo,
          body: raw,
          baseContent: view.content,
        });
      }
    }
    out[feKey] = items;
  }
  return out;
}

/**
 * 사용자가 고친 content/quote 를 PATCH 본문으로 만든다.
 * PATCH 는 항목 전체를 교체하므로 원본 body 를 그대로 깔고 note/quote 만 얹는다.
 */
export function toPatchBody(item, content, quote) {
  const { body, baseContent } = item;
  const changed = content !== baseContent;
  const updated = {
    ...body,
    note: changed ? content || null : null,
    quote: quote || null,
  };
  if (item.category === "events" && changed) updated.summary = content || null;
  if (item.category === "events" && !changed && body.summary) updated.summary = body.summary;
  return updated;
}

// ── 모순(2차) ────────────────────────────────────────────────
// 백엔드 모순 type → 화면 6분류 (캐논 6뷰와 같은 체계)
function toCategory(type) {
  const t = (type || "").toLowerCase();
  if (t.includes("foreshadow")) return "foreshadow";
  if (t.includes("character") || t.includes("relation")) return "character";
  if (t.includes("time")) return "time";
  if (t.includes("space") || t.includes("place")) return "space";
  if (t.includes("event")) return "event";
  return "worldview"; // setting/knowledge/item 등 나머지는 "세계관"으로
}

/** contradictions → 2차 탭 이슈 카드. id/chapterNo/status 는 ✓/✕ PATCH 에 쓴다. */
export function toIssues(contradictions, chapterNo, chapterTitle) {
  return (contradictions || []).map((c) => {
    const quotes = [];
    if (c.span?.quote) quotes.push({ tag: `현재 ${chapterNo}화`, text: c.span.quote });
    if (c.conflict_ref?.quote)
      quotes.push({
        tag: c.conflict_ref.chapter_no != null ? `${c.conflict_ref.chapter_no}화` : "이전 회차",
        text: c.conflict_ref.quote,
      });
    return {
      id: c.id,
      chapterNo,
      status: c.status || "pending",
      category: toCategory(c.type),
      title: chapterTitle ? `${chapterNo}화 · ${chapterTitle}` : `${chapterNo}화`,
      description: c.explanation || "",
      quotes,
    };
  });
}

// ── 회차 상태 라벨 (chapters.status 가 유일한 진실 — 화면은 보여주기만) ──
const CHAPTER_STATUS_LABELS = {
  uploaded: "분석 전",
  extracting: "추출 중",
  extracted: "1차 확인 대기",
  reviewing: "검수 중",
  reviewed: "저장 대기",
  saved: "완료",
  failed: "실패",
};

export function chapterStatusLabel(status) {
  return CHAPTER_STATUS_LABELS[status] || status || "";
}

export const isBusyStatus = (status) => status === "extracting" || status === "reviewing";
