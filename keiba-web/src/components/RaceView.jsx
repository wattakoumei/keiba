import { useState, useEffect, useMemo } from 'preact/hooks';

// ---- helpers ----
const MARK_CLASS = {
  '◎': 'm-honmei', '◯': 'm-taikou', '○': 'm-taikou', '▲': 'm-tanana',
  '△': 'm-renka', '×': 'm-chui', '注': 'm-himo', '—': 'm-muted', '-': 'm-muted',
};
const FIT_CLASS = { '◎': 'fit-center', '○': 'fit-in', '△': 'fit-spot' };
const TIER_CLASS = { '本線': 'tier-honmei', '対抗': 'tier-taikou', '伏線': 'tier-fukusen' };
const TIER_STAR = { '本線': '★★★', '対抗': '★★', '伏線': '★' };

// 脚質順: 逃<先<差<追（first-match 優先）
function legRank(leg = '') {
  if (leg.includes('逃')) return 0;
  if (leg.includes('先')) return 1;
  if (leg.includes('差')) return 2;
  if (leg.includes('追')) return 3;
  return 2.5;
}

function useLocalSet(key) {
  const [set, setSet] = useState(() => new Set());
  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw) setSet(new Set(JSON.parse(raw)));
    } catch {}
  }, [key]);
  const toggle = (v) => setSet((prev) => {
    const next = new Set(prev);
    next.has(v) ? next.delete(v) : next.add(v);
    try { localStorage.setItem(key, JSON.stringify([...next])); } catch {}
    return next;
  });
  return [set, toggle];
}

export default function RaceView({ race }) {
  const pace = race.pace ?? {};
  const patterns = pace.patterns ?? [];
  const patIds = patterns.map((p) => p.id);
  const rank = race.rank ?? [];

  const [active, setActive] = useState(null); // 選択中パターン id
  const [sortMode, setSortMode] = useState('mark'); // 'mark' | 'leg'
  const [expanded, setExpanded] = useState(() => new Set());
  const [excluded, toggleExcluded] = useLocalSet(`keiba:${race.race_id}:excluded`);
  const [starred, toggleStarred] = useLocalSet(`keiba:${race.race_id}:starred`);

  const activePat = patterns.find((p) => p.id === active) || null;
  const box = (pace.box_reverse ?? []).find((b) => b.pattern === active) || null;

  const rows = useMemo(() => {
    const arr = [...rank];
    arr.sort((a, b) =>
      sortMode === 'leg'
        ? legRank(a.leg_type) - legRank(b.leg_type) || a.rank_order - b.rank_order
        : a.rank_order - b.rank_order
    );
    return arr;
  }, [rank, sortMode]);

  const toggleExpand = (no) =>
    setExpanded((prev) => {
      const n = new Set(prev);
      n.has(no) ? n.delete(no) : n.add(no);
      return n;
    });

  return (
    <div>
      {/* ===== §2 展開予想 ===== */}
      <h2>§2 展開予想（成果物1）</h2>
      {pace.verification_contract && <p class="contract">{pace.verification_contract}</p>}

      <p class="sub">パターンをタップ → 該当馬を着順表でハイライト＋段階フロー表示</p>
      <div class="chips">
        {patterns.map((p) => (
          <button
            class={`chip ${TIER_CLASS[p.tier] || ''}`}
            aria-pressed={active === p.id}
            onClick={() => setActive(active === p.id ? null : p.id)}
          >
            {p.id} {p.name} <span class="tier">{TIER_STAR[p.tier] || p.tier}</span>
          </button>
        ))}
      </div>

      {activePat && (
        <div class="panel pattern-detail">
          <div class="pd-head">
            <b>{activePat.id} {activePat.name}</b>{' '}
            <span class={`tier ${TIER_CLASS[activePat.tier] || ''}`}>{TIER_STAR[activePat.tier] || activePat.tier}</span>
          </div>
          <p class="sub">トリガー: {activePat.trigger}</p>
          <div class="flow">
            <div><span class="flow-k">序盤</span>{activePat.phase_flow?.early}</div>
            <div><span class="flow-k">中盤</span>{activePat.phase_flow?.mid}</div>
            <div><span class="flow-k">終盤</span>{activePat.phase_flow?.late}</div>
            <div><span class="flow-k">結果</span>{activePat.phase_flow?.result}</div>
          </div>
          {activePat.leg_advantage && (
            <p class="sub">脚質有利: {Object.entries(activePat.leg_advantage).map(([k, v]) => `${k}${v >= 0 ? '+' : ''}${v}`).join(' / ')}</p>
          )}
          {box && (
            <p class="sub box-line">
              {box.center?.length > 0 && <span>中心◎ {box.center.join('・')}</span>}
              {box.inside?.length > 0 && <span>圏内○ {box.inside.join('・')}</span>}
              {box.spot?.length > 0 && <span>一発△ {box.spot.join('・')}</span>}
              {box.drop?.length > 0 && <span class="drop">消し {box.drop.join('・')}</span>}
            </p>
          )}
        </div>
      )}

      {pace.shape_note && <p class="sub">{pace.shape_note}</p>}
      {pace.formation_note && <p class="sub">隊列: {pace.formation_note}</p>}
      {pace.bias_note && <p class="sub">バイアス: {pace.bias_note}</p>}
      {pace.transmission && <p class="contract">展開→着順: {pace.transmission}</p>}

      {/* ===== §3 着順予想 ===== */}
      <h2>§3 着順予想（成果物2）</h2>
      {race.rank_verification_contract && <p class="contract">{race.rank_verification_contract}</p>}

      <div class="controls">
        <span class="sub">並び:</span>
        <button class="chip small" aria-pressed={sortMode === 'mark'} onClick={() => setSortMode('mark')}>印順</button>
        <button class="chip small" aria-pressed={sortMode === 'leg'} onClick={() => setSortMode('leg')}>脚質順</button>
        {active && <button class="chip small" onClick={() => setActive(null)}>ハイライト解除（{active}）</button>}
      </div>

      <div class="scroll-x">
        <table class="rank-table">
          <thead>
            <tr><th></th><th>印</th><th>枠馬</th><th>馬名 / 騎手</th><th>展開列</th><th>展開感度</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const hitSym = active ? r.pattern_fit?.[active] : null;
              const isExcluded = excluded.has(r.no);
              const dim = (active && !hitSym) || isExcluded;
              const open = expanded.has(r.no);
              return (
                <>
                  <tr class={`row ${dim ? 'dim' : ''} ${hitSym ? 'hit ' + FIT_CLASS[hitSym] : ''} ${isExcluded ? 'excluded' : ''}`}>
                    <td><button class="exp" onClick={() => toggleExpand(r.no)} aria-label="詳細">{open ? '▾' : '▸'}</button></td>
                    <td><span class={`mark ${MARK_CLASS[r.mark] || ''}`}>{r.mark}</span></td>
                    <td class="nowrap">{r.gate}-{r.no}</td>
                    <td class="cell-horse" onClick={() => toggleExpand(r.no)}>
                      <div class="hname">{starred.has(r.no) ? '⭐ ' : ''}{r.horse}</div>
                      <div class="sub jk">{r.jockey}{r.jockey_change ? `（${r.jockey_change}）` : ''} · {r.leg_type}</div>
                    </td>
                    <td>
                      <span class="fits">
                        {patIds.filter((id) => r.pattern_fit?.[id]).map((id) => (
                          <span class={`fit ${FIT_CLASS[r.pattern_fit[id]]} ${active === id ? 'on' : ''}`}>{id}{r.pattern_fit[id]}</span>
                        ))}
                      </span>
                    </td>
                    <td class="sens">{r.pace_sensitivity}</td>
                    <td class="rowctl nowrap">
                      <button class="mini" title="注目" onClick={() => toggleStarred(r.no)}>{starred.has(r.no) ? '★' : '☆'}</button>
                      <button class="mini" title="消し" onClick={() => toggleExcluded(r.no)}>{isExcluded ? '↺' : '✕'}</button>
                    </td>
                  </tr>
                  {open && (
                    <tr class="detail-row">
                      <td colSpan={7}>
                        <div class="row-detail">
                          <div class="pc">
                            <h4>好材料</h4>
                            <ul class="pros">{(r.pros || []).map((x) => <li><span class="tag">{x.tag}</span>{x.note}</li>)}</ul>
                          </div>
                          <div class="pc">
                            <h4>懸念点</h4>
                            <ul class="cons">{(r.cons || []).map((x) => <li><span class="tag">{x.tag}</span>{x.note}</li>)}</ul>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
      <p class="sub">印 ◎本命 ◯対抗 ▲単穴 △連下 ×注意 注ヒモ。展開列 ◎中心/○圏内/△一発（圏外は非表示）。除外・注目は端末内のみ（共有されません）。</p>
    </div>
  );
}
