// build 時に ../data/screening/*.json を直読みする（screen-card 選別ハーネスの出力＝唯一の源）。
// schema は .claude/skills/screen-card/references/screening-model.md §6。ここは複製せず読むだけ。
// ★I1-S: これは選別レイヤーの出力（市場=団子度を隔離して使う）。買い目・金額は含まない。
import fs from 'node:fs';
import path from 'node:path';

const SCREENING_DIR = path.resolve(process.cwd(), '../data/screening');

/** data/screening/<date>-<venue>.json を全読み（壊れた/非JSONは無視）。 */
export function loadScreenings() {
  const out = [];
  if (!fs.existsSync(SCREENING_DIR)) return out;
  for (const fn of fs.readdirSync(SCREENING_DIR)) {
    if (!fn.endsWith('.json')) continue;
    try {
      const card = JSON.parse(fs.readFileSync(path.join(SCREENING_DIR, fn), 'utf-8'));
      if (card && card.date) out.push(card);
    } catch (e) {
      console.warn(`[screening] skip ${fn}: ${e.message}`);
    }
  }
  return out;
}
