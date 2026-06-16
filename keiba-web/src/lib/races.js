// build 時に ../data/races/*/report.json を直読みする（同一リポのサブディレクトリ）。
// report.json が唯一の正本。ここは複製せず読むだけ（I10）。
import fs from 'node:fs';
import path from 'node:path';

const RACES_DIR = path.resolve(process.cwd(), '../data/races');

/** 全レースの report.json を date 降順で返す（report.json が無いディレクトリは無視）。 */
export function loadRaces() {
  const out = [];
  if (!fs.existsSync(RACES_DIR)) return out;
  for (const id of fs.readdirSync(RACES_DIR)) {
    const f = path.join(RACES_DIR, id, 'report.json');
    if (!fs.existsSync(f)) continue; // 過去レース（report.json 無し）は載せない＝新レースから
    try {
      out.push(JSON.parse(fs.readFileSync(f, 'utf-8')));
    } catch (e) {
      console.warn(`[races] skip ${id}: ${e.message}`);
    }
  }
  out.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  return out;
}
