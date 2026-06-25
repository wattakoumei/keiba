// build 時に ../data/races/*/report.json を直読みする（同一リポのサブディレクトリ）。
// report.json が唯一の正本。ここは複製せず読むだけ（I10）。
import fs from 'node:fs';
import path from 'node:path';
import { loadScreenings } from './screening.js';

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

/** race_id("20260621-tokyo-11") or ISO date("2026-06-21") から YYYYMMDD を得る。 */
function ymdOf(report) {
  const fromId = (report.race_id || '').split('-')[0];
  if (/^\d{8}$/.test(fromId)) return fromId;
  const fromDate = (report.date || '').replace(/-/g, '');
  return /^\d{8}$/.test(fromDate) ? fromDate : null;
}

/** YYYYMMDD → "2026-06-21"。 */
export function fmtDate(ymd) {
  return /^\d{8}$/.test(ymd) ? `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}` : ymd;
}

/** 選別レースの report ディレクトリ id（romaji）を組む＝ <ymd>-<venue>-<RR0埋め>。 */
export function reportId(ymd, venue, r) {
  return `${ymd}-${venue}-${String(r).padStart(2, '0')}`;
}

/**
 * 日付(YYYYMMDD)単位に reports と screenings を束ねて date 降順で返す。
 * ① 日付一覧 と ② 日付ページ の源。
 * 各要素: { ymd, iso, reports:[report], screenings:[card], reportIds:Set }
 */
export function loadDates() {
  const reports = loadRaces();
  const screenings = loadScreenings();
  const byDate = new Map();
  const ensure = (ymd) => {
    if (!byDate.has(ymd)) byDate.set(ymd, { ymd, iso: fmtDate(ymd), reports: [], screenings: [], reportIds: new Set() });
    return byDate.get(ymd);
  };
  for (const r of reports) {
    const ymd = ymdOf(r);
    if (!ymd) continue;
    const e = ensure(ymd);
    e.reports.push(r);
    if (r.race_id) e.reportIds.add(r.race_id);
  }
  for (const s of screenings) {
    const ymd = String(s.date || '').replace(/-/g, '');
    if (!/^\d{8}$/.test(ymd)) continue;
    ensure(ymd).screenings.push(s);
  }
  const dates = [...byDate.values()];
  dates.sort((a, b) => (a.ymd < b.ymd ? 1 : a.ymd > b.ymd ? -1 : 0));
  return dates;
}
