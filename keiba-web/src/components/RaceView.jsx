import { useState, useEffect, useMemo } from 'preact/hooks';

// ---- helpers ----
const MARK_CLASS = {
  '◎': 'm-honmei', '◯': 'm-taikou', '○': 'm-taikou', '▲': 'm-tanana',
  '△': 'm-renka', '×': 'm-chui', '注': 'm-himo', '—': 'm-muted', '-': 'm-muted',
};
const FIT_CLASS = { '◎': 'fit-center', '○': 'fit-in', '△': 'fit-spot' };
const TIER_CLASS = { '本線': 'tier-honmei', '対抗': 'tier-taikou', '伏線': 'tier-fukusen' };
const TIER_STAR = { '本線': '★★★', '対抗': '★★', '伏線': '★' };
const INTENT_CLASS = { '↑↑': 'i-up2', '↑': 'i-up', '→': 'i-flat', '↓': 'i-down' };

// 脚質タイプの色（逃→先→差→追＝前→後を暖→寒で）。§2有利脚質と§3着順表で共通。
const LEG_COLOR = { '逃': 'leg-nige', '先': 'leg-senko', '差': 'leg-sashi', '追': 'leg-oikomi' };

// win_prob/place_prob (0..1) → "14.6%"。欠損は "—"。源=score_race.py の決定論出力（並びは論理が主・率は参考＝市場を見ない内在値）。
const pct = (v) => (typeof v === 'number' ? (v * 100).toFixed(1) + '%' : '—');

// 脚質文字列の 逃/先/差/追 だけ着色（"先〜好位""差・捲り" 等の他文字はそのまま）
function LegType({ text }) {
  return (
    <span class="legtype">
      {[...String(text ?? '')].map((ch) => (LEG_COLOR[ch] ? <span class={LEG_COLOR[ch]}>{ch}</span> : ch))}
    </span>
  );
}

// 脚質順: 逃<先<差<追（first-match 優先）
function legRank(leg) {
  leg = String(leg ?? '');
  if (leg.includes('逃')) return 0;
  if (leg.includes('先')) return 1;
  if (leg.includes('差')) return 2;
  if (leg.includes('追')) return 3;
  return 2.5;
}

// 有利脚質トークン: 脚質文字は type 色（§3と共通）、有利度は数値の強弱で（正=強調/負=淡）
function LegAdv({ la }) {
  if (!la) return null;
  const order = ['逃げ', '先行', '差し', '追込'];
  return (
    <span class="legadv">
      {order.filter((k) => k in la).map((k) => {
        const v = la[k];
        const adv = v > 0 ? 'pos' : v < 0 ? 'neg' : 'zero';
        return (
          <span class="la">
            <span class={LEG_COLOR[k[0]]}>{k[0]}</span>
            <span class={`adv ${adv}`}>{v > 0 ? '+' : ''}{v}</span>
          </span>
        );
      })}
    </span>
  );
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

  const boxFor = (id) => (pace.box_reverse ?? []).find((b) => b.pattern === id) || null;

  // 箱組みペア: 同一パターンで展開列◎×複勝率≥15% の2頭組。
  // 抽出条件の正本は tools/box_sim.py build_wide_pairfit_p15（閾値0.15・cap8）＝同値ミラー。閾値を変えるときは両方直す。
  // 並びだけ表示用（共通パターン数→合計複勝率。Python側の並びは馬番順＝集合は同一）。
  const pairs = useMemo(() => {
    const byKey = new Map();
    for (const p of patterns) {
      const nos = rank
        .filter((r) => r.pattern_fit?.[p.id] === '◎' && (r.place_prob ?? 0) >= 0.15)
        .map((r) => r.no)
        .sort((a, b) => a - b);
      for (let i = 0; i < nos.length; i++)
        for (let j = i + 1; j < nos.length; j++) {
          const key = `${nos[i]}-${nos[j]}`;
          if (!byKey.has(key)) byKey.set(key, { a: nos[i], b: nos[j], pats: [] });
          byKey.get(key).pats.push(p.id);
        }
    }
    const horse = Object.fromEntries(rank.map((r) => [r.no, r]));
    return [...byKey.values()]
      .sort((x, y) => (x.a - y.a) || (x.b - y.b))
      .slice(0, 8)
      .map((x) => ({ ...x, ha: horse[x.a], hb: horse[x.b],
        score: (horse[x.a]?.place_prob ?? 0) + (horse[x.b]?.place_prob ?? 0) }))
      .sort((x, y) => y.pats.length - x.pats.length || y.score - x.score);
  }, [patterns, rank]);

  // ワイド3頭BOX（pairfit三角形）: ペア候補に三角形（3頭の全3ペアが候補）が成立する時だけ place_prob 合計最大の3頭。
  // 抽出条件の正本は tools/box_sim.py build_wide_box3_tri（床0.15）＝同値ミラー。監視トラック（頑健性未達）＝表示は参考。
  const wideTri = useMemo(() => {
    const pairSet = new Set();
    for (const p of patterns) {
      const nos = rank
        .filter((r) => r.pattern_fit?.[p.id] === '◎' && (r.place_prob ?? 0) >= 0.15)
        .map((r) => r.no)
        .sort((a, b) => a - b);
      for (let i = 0; i < nos.length; i++)
        for (let j = i + 1; j < nos.length; j++) pairSet.add(`${nos[i]}-${nos[j]}`);
    }
    const nos = [...new Set([...pairSet].flatMap((k) => k.split('-').map(Number)))].sort((a, b) => a - b);
    const pp = Object.fromEntries(rank.map((r) => [r.no, r.place_prob ?? 0]));
    let best = null, bestS = -1;
    for (let i = 0; i < nos.length; i++)
      for (let j = i + 1; j < nos.length; j++)
        for (let k = j + 1; k < nos.length; k++) {
          const [a, b, c] = [nos[i], nos[j], nos[k]];
          if (pairSet.has(`${a}-${b}`) && pairSet.has(`${a}-${c}`) && pairSet.has(`${b}-${c}`)) {
            const s = pp[a] + pp[b] + pp[c];
            if (s > bestS) { bestS = s; best = [a, b, c]; }
          }
        }
    return best;
  }, [patterns, rank]);

  // 三連複の箱: エンジン複勝率(place_prob)上位4頭BOX（4点・全頭 複勝率≥20%床）。
  // 抽出条件の正本は tools/box_sim.py build_trio_box4_prob（床0.20）＝同値ミラー。閾値を変えるときは両方直す。
  const trioBox = useMemo(() => {
    const rows = rank
      .filter((r) => r.no != null && (r.place_prob ?? 0) >= 0.20)
      .sort((a, b) => (b.place_prob ?? 0) - (a.place_prob ?? 0));
    if (rows.length < 4) return null;
    const sel = rows.slice(0, 4);
    const nos = sel.map((r) => r.no);
    const combos = [];
    for (let i = 0; i < 4; i++)
      for (let j = i + 1; j < 4; j++)
        for (let k = j + 1; k < 4; k++)
          combos.push([nos[i], nos[j], nos[k]].sort((a, b) => a - b));
    combos.sort((x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2]);
    return { sel, combos };
  }, [rank]);

  const tierOf = (id) => (patterns.find((p) => p.id === id) || {}).tier;
  const circ = (no) => (no >= 1 && no <= 20 ? String.fromCharCode(0x2460 + no - 1) : `${no}`);

  const obsCoverage = race.obs_coverage ?? [];

  return (
    <div>
      {/* 観点欠落バナー: 縮退分析（web調査の欠落あり）は印・率の確度が通常より低いことを冒頭で明示（詳細表は§4） */}
      {obsCoverage.length > 0 && (
        <p class="warn-banner">
          ⚠ 調査欠落あり: 観点 <strong>{obsCoverage.map((o) => o.id).join('・')}</strong> が
          {obsCoverage.some((o) => o.status === '未取得') ? '未取得/縮退' : '縮退'}＝
          印・単勝/複勝率の確度は通常より低い（詳細は§4）
        </p>
      )}

      {/* ===== §2 展開予想（パターン表・行が操作子）===== */}
      <h2>§2 展開予想（成果物1）</h2>
      <p class="sub">行をタップ → 該当馬を着順表でハイライト＋トリガー/段階フロー/箱組みを展開</p>

      {/* 展開トリガー早見＝来そうな展開を判断する材料（先行勢の数・枠・コース形状・例年傾向・当日で動く点）。当日にティアを付け替える素 */}
      {(pace.pace_factors?.length > 0) && (
        <details class="fold pace-factors">
          <summary>展開を読む材料（来そうな展開の判断材料）</summary>
          <div class="scroll-x">
            <table class="factor-table">
              <thead><tr><th>材料</th><th>読み</th><th>当日チェック</th></tr></thead>
              <tbody>
                {pace.pace_factors.map((f) => (
                  <tr>
                    <td class="f-name">{f.factor}</td>
                    <td class="f-read">{f.reads}</td>
                    <td class="f-day sub">{f.day_check}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <div class="scroll-x">
        <table class="pace-table">
          <thead>
            <tr><th></th><th>パターン</th><th>有利脚質</th></tr>
          </thead>
          <tbody>
            {patterns.map((p) => {
              const on = active === p.id;
              const box = boxFor(p.id);
              return (
                <>
                  <tr class={`prow ${on ? 'on' : ''}`} onClick={() => setActive(on ? null : p.id)}>
                    <td><span class="exp">{on ? '▾' : '▸'}</span></td>
                    <td>
                      <span class="pname">{p.id} {p.name}</span>{' '}
                      <span class={`tier ${TIER_CLASS[p.tier] || ''}`}>{TIER_STAR[p.tier] || p.tier}</span>
                    </td>
                    <td><LegAdv la={p.leg_advantage} /></td>
                  </tr>
                  {on && (
                    <tr class="pdetail">
                      <td colSpan={3}>
                        <p class="sub">トリガー: {p.trigger}</p>
                        <div class="flow">
                          <div><span class="flow-k">序盤</span>{p.phase_flow?.early}</div>
                          <div><span class="flow-k">中盤</span>{p.phase_flow?.mid}</div>
                          <div><span class="flow-k">終盤</span>{p.phase_flow?.late}</div>
                          <div><span class="flow-k">結果</span>{p.phase_flow?.result}</div>
                        </div>
                        {(p.risers?.length > 0 || p.sinkers?.length > 0) && (
                          <p class="sub rs-line">
                            {p.risers?.length > 0 && <span class="up">浮上 {p.risers.join('・')}</span>}
                            {p.sinkers?.length > 0 && <span class="down">沈む {p.sinkers.join('・')}</span>}
                          </p>
                        )}
                        {box && (
                          <p class="sub box-line">
                            {box.center?.length > 0 && <span>中心◎ {box.center.join('・')}</span>}
                            {box.inside?.length > 0 && <span>圏内○ {box.inside.join('・')}</span>}
                            {box.spot?.length > 0 && <span>一発△ {box.spot.join('・')}</span>}
                            {box.drop?.length > 0 && <span class="drop">消し {box.drop.join('・')}</span>}
                          </p>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ===== 箱組みガイド（同時圏内ペア＝展開列の転置ビュー。I7: 券種・金額・購入は人間判断）===== */}
      <h2>箱組みガイド</h2>
      <p class="sub">
        同じ展開パターンで<strong>共に中心◎</strong>（かつ複勝率≥15%）になる2頭の組＝ワイド・連系の箱はここから組む。
        印の上位同士で組むより、<strong>同じ展開で同時に浮く2頭</strong>で組むのが箱の考え方（券種・金額・購入は人間判断）。
      </p>
      {pairs.length > 0 ? (
        <div class="scroll-x">
          <table class="pair-table">
            <thead>
              <tr><th>ペア</th><th>成立パターン</th><th>複勝率（2頭）</th></tr>
            </thead>
            <tbody>
              {pairs.map((x) => {
                const dead = excluded.has(x.a) || excluded.has(x.b);
                const dim = dead || (active && !x.pats.includes(active));
                return (
                  <tr class={`prow-pair ${dim ? 'dim' : ''}`}>
                    <td class="pair-h nowrap">
                      <span class={`mark ${MARK_CLASS[x.ha?.mark] || ''}`}>{x.ha?.mark}</span>{circ(x.a)}{x.ha?.horse}
                      <span class="pair-x">×</span>
                      <span class={`mark ${MARK_CLASS[x.hb?.mark] || ''}`}>{x.hb?.mark}</span>{circ(x.b)}{x.hb?.horse}
                    </td>
                    <td>
                      <span class="fits">
                        {x.pats.map((id) => (
                          <span class={`fit fit-center ${active === id ? 'on' : ''}`} onClick={() => setActive(active === id ? null : id)}>
                            {id}<span class={`tier ${TIER_CLASS[tierOf(id)] || ''}`}>{TIER_STAR[tierOf(id)] || ''}</span>
                          </span>
                        ))}
                      </span>
                    </td>
                    <td class="prob nowrap">{pct(x.ha?.place_prob)} × {pct(x.hb?.place_prob)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p class="sub">該当ペアなし（同一パターンで◎が2頭揃わないレース。§2の各パターンの「中心◎/圏内○」から人間判断で）。</p>
      )}

      {/* ワイド3頭BOX（三角形成立時のみ。正本=box_sim build_wide_box3_tri の同値ミラー・監視トラック） */}
      {wideTri && (
        <p class="sub">
          ワイド3頭BOX成立: <strong>{wideTri.map(circ).join('・')}</strong>（3頭の全ペアが同時圏内候補＝3点BOXで買える形。実測蓄積中の参考）
        </p>
      )}

      {/* 三連複の箱（複勝率上位4頭BOX・全頭20%床。正本=box_sim build_trio_box4_prob の同値ミラー） */}
      {trioBox && (
        <>
          <h3>三連複の箱（複勝率上位4頭BOX・全頭複勝率≥20%）</h3>
          <p class="sub">
            {trioBox.sel.map((r, i) => (
              <span class="nowrap">
                {i > 0 && ' ・ '}
                <span class={`mark ${MARK_CLASS[r.mark] || ''}`}>{r.mark}</span>{circ(r.no)}{r.horse}（{pct(r.place_prob)}）
              </span>
            ))}
            の4頭BOX＝4点。
          </p>
          <details class="fold">
            <summary>組み合わせ一覧（{trioBox.combos.length}点）</summary>
            <p class="sub">{trioBox.combos.map((t) => t.map(circ).join('')).join(' ／ ')}</p>
          </details>
        </>
      )}

      {/* ===== §3 着順予想（§2表の直下に配置＝行タップ→ハイライトを近づける）===== */}
      <h2>§3 着順予想（成果物2）</h2>

      <div class="controls">
        <span class="sub">並び:</span>
        <button class="chip small" aria-pressed={sortMode === 'mark'} onClick={() => setSortMode('mark')}>印順</button>
        <button class="chip small" aria-pressed={sortMode === 'leg'} onClick={() => setSortMode('leg')}>脚質順</button>
        {active && <button class="chip small" onClick={() => setActive(null)}>ハイライト解除（{active}）</button>}
      </div>

      <div class="scroll-x">
        <table class="rank-table">
          <thead>
            <tr><th></th><th>印</th><th>単勝</th><th>複勝</th><th>枠馬</th><th>馬名 / 騎手</th><th>展開列</th><th>展開感度</th><th></th></tr>
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
                    <td class="prob nowrap">{pct(r.win_prob)}</td>
                    <td class="prob nowrap">{pct(r.place_prob)}</td>
                    <td class="nowrap">{r.gate}-{r.no}</td>
                    <td class="cell-horse" onClick={() => toggleExpand(r.no)}>
                      <div class="hname">{starred.has(r.no) ? '⭐ ' : ''}{r.horse}{r.intent ? <span class={`intent ${INTENT_CLASS[r.intent] || 'i-flat'}`} title="勝負気配度（陣営の本気度: F追い切り+K起用+H気配。能力とは独立）">{r.intent}</span> : null}</div>
                      <div class="sub jk">{r.jockey}{r.jockey_change ? `（${r.jockey_change}）` : ''} · <LegType text={r.leg_type} /></div>
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
                      <td colSpan={9}>
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
      <p class="sub">
        印 ◎本命 ◯対抗 ▲単穴 △連下 ×注意 注ヒモ。展開列 ◎中心/○圏内/△一発（圏外は非表示）。
        脚質 <LegType text="逃" /> <LegType text="先" /> <LegType text="差" /> <LegType text="追" />。
        <strong>単勝/複勝</strong>はエンジン(score_race)の決定論値＝<strong>並びは印の論理が主</strong>・率は参考（市場を見ない内在値＝目安）。
        除外・注目は端末内のみ（共有されません）。
      </p>

      {/* 展開→着順の伝達・展開メモは §3 表の下へ（§2↔§3 のハイライト操作を近接させるため） */}
      {pace.transmission && <p class="contract bridge">展開→着順: {pace.transmission}</p>}
      {(pace.formation_note || pace.bias_note || pace.shape_note) && (
        <details class="fold inline-fold">
          <summary>展開メモ（隊列・バイアス）</summary>
          {pace.shape_note && <p class="sub">{pace.shape_note}</p>}
          {pace.formation_note && <p class="sub">隊列: {pace.formation_note}</p>}
          {pace.bias_note && <p class="sub">バイアス: {pace.bias_note}</p>}
        </details>
      )}

      {/* ===== §4 データの確かさ（観点欠落の表＝欠落がある時だけ・正本は report.obs_coverage=inject_probs 生成） ===== */}
      {(obsCoverage.length > 0 || (race.data_confidence ?? []).length > 0) && (
        <>
          <h2>§4 データの確かさ</h2>
          {obsCoverage.length > 0 && (
            <table class="coverage-table">
              <thead><tr><th>観点</th><th>内容</th><th>状態</th><th>代替</th></tr></thead>
              <tbody>
                {obsCoverage.map((o) => (
                  <tr key={o.id}>
                    <td><strong>{o.id}</strong></td>
                    <td>{o.label}</td>
                    <td class={o.status === '未取得' ? 'cov-missing' : 'cov-degraded'}>{o.status}</td>
                    <td class="sub-cell">{o.fallback}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {(race.data_confidence ?? []).map((s, i) => <p class="sub" key={i}>{s}</p>)}
        </>
      )}
    </div>
  );
}
