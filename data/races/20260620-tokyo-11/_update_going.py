# -*- coding: utf-8 -*-
# 当日更新: 東京ダ稍重。素の能力読みは再調査せず道悪適性で並びを再評価(I5当日可変)。
import json
p='data/races/20260620-tokyo-11/report.json'
d=json.load(open(p))

# --- going 確定 ---
d['day_board']['going'][0]['value']="稍重"
d['day_board']['going'][0]['read']=("当日東京ダ稍重で確定。脚抜きは良より改善し時計は出やすい＝先行の前残り骨格(α/β)は維持しつつ、"
  "道悪適性で⑬(ホッコータルマエ重◎)・⑤(トーセンジョーダン道悪一変)・②(時計かかる方が良)が浮上、"
  "⑪(アジアエクスプレス道悪割引)・⑦(ゴールドドリーム道悪下手)は割引")

# --- header_notes / pivot ---
d['header_notes'].append("当日更新(稍重): 6/19良想定→当日東京ダ稍重で確定。前残りの骨格は維持しつつ道悪適性で個別を再評価(⑬⑤②浮上・⑪⑦割引・⑤を無印→注に格上げ)。素の能力読みは再調査せず並びのみ論理再評価(当日可変)。")
d['pivot']=d['pivot']+" 【稍重更新】前残り骨格は不変だが道悪適性で⑬②が一段強化・⑤が一発に浮上、距離不適⑪はさらに終い甘く。"

# --- rank をno索引で扱う ---
byno={r['no']:r for r in d['rank']}

# 5 フタイテンロック: 無印→注(道悪一変)
r=byno[5]
r['mark']="注"
r['pattern_fit']={"β":"△","γ":"○"}
r['pace_sensitivity']="稍重で父トーセンジョーダンの道悪適性が一変好材料＝差し台頭γ/締まったβで条件巧者として食い込み、良の高速決着なら地力不足"
r['pros']=[{"tag":"D/C/L","note":"当日稍重で父トーセンジョーダンの道悪適性が一変好材料(良では振るわず稍重以上で浮上する型)。東京ダ2100左回り(ブラジルC4着)は得意条件、昨年スレイプニル7着で条件理解あり"},
           {"tag":"E/展開","note":"差し・中団後ろで道悪巧者が浮く稍重のγ/β＝先行勢の道悪適性が乏しい分、展開の綾で食い込み余地"}]
r['cons']=[{"tag":"A/G/I","note":"平城京15着等近走大敗続きで地力面は半信半疑、7歳で上積み乏しい＝道悪一変の条件好転頼みの一発"}]

# 13 ルヴァンユニベール: ホッコータルマエ重◎で稍重ど真ん中
r=byno[13]
r['pros'].append({"tag":"D/C","note":"当日稍重は父ホッコータルマエの重◎(水含みが最良)にど真ん中＝決め手が最大化、先行勢の道悪適性が乏しい分さらに展開が向く"})
r['pace_sensitivity']=r['pace_sensitivity']+"。稍重でホッコータルマエの道悪適性が活き決め手が最大化"

# 2 クールミラボー: 稍重は時計かかる馬場で好転
r=byno[2]
r['cons'][0]={"tag":"A/I","note":"直近同コースのブリリアント8着は良で時計かからず伸びず＝当日稍重は『時計が掛かる馬場が理想』に近づき好転。ただ近走指数は下降線で勝ち切りは展開次第"}
r['pace_sensitivity']=r['pace_sensitivity'].replace("ただし速い良馬場だと決め手がやや甘く頭まで一押し","当日稍重は時計かかる馬場で好転＝決め手の甘さが薄れる")

# 14 レッドプロフェシー: ルーラーシップ道悪巧者で安泰
r=byno[14]
r['pros'].append({"tag":"D/C","note":"父ルーラーシップは道悪巧者・母父マンハッタンカフェのスタミナ＝当日稍重の消耗戦はむしろプラスで取りこぼしリスクが減る"})
r['pace_sensitivity']=r['pace_sensitivity']+"。稍重の消耗戦は道悪巧者でむしろ安泰"

# 11 ピカピカサンダー: 道悪割引が距離不適に重なる二重減点(△は維持・先行の前残り恩恵は残す)
r=byno[11]
r['cons'].append({"tag":"D/C","note":"当日稍重で父アジアエクスプレスの道悪割引が距離不適に重なり二重減点＝前は取れても終いがさらに甘くなる"})
r['pace_sensitivity']=r['pace_sensitivity']+"。稍重で道悪割引も重なり終いの甘さが増す"

# --- rank_order 再採番(⑤を注グループ=9番目へ) ---
NEW_ORDER=[14,2,13,6,15,11,10,3,5,4,1,9,12,8,7]
for i,no in enumerate(NEW_ORDER,1):
    byno[no]['rank_order']=i
d['rank']=[byno[no] for no in NEW_ORDER]

# --- box_reverse: ⑤を β spot / γ inside へ(pattern_fitと同源・矛盾させない I7) ---
for b in d['pace']['box_reverse']:
    if b['pattern']=="β":
        if 5 not in b['spot']: b['spot'].append(5)
        b['drop']=[x for x in b['drop'] if x!=5]
    if b['pattern']=="γ":
        if 5 not in b['inside']: b['inside'].insert(1,5)
        b['drop']=[x for x in b['drop'] if x!=5]

json.dump(d,open(p,'w'),ensure_ascii=False,indent=2)
print("updated going=稍重. new order:",NEW_ORDER)
