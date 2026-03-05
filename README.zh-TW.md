# Indo-Pacific PMESII 兵推 Skill（V2.3）

[English Version](./README.md)

這個 skill 是戰略層兵推引擎，強項是「可重跑、可稽核、可追證據鏈」，不是黑箱生成器。  
設計目標對齊智庫流程：紅藍對抗、白隊裁決、ACH 推理、回合復盤、決策報告直出。

## 1. 你會得到什麼

- 雙層報告：
  - `report_exec.md`（給主管）
  - `report_analyst.md`（給分析師）
- 每回合可回放紀錄：
  - `turn_*_agent_log.json`
  - `turn_*_event_ledger.json`
  - `turn_*_story_cards.json`
- 可追溯推理鏈：
  - `evidence -> event -> adjudication -> ACH -> KJ`
- 品質閘門：
  - `verify_trace.py` 可做 hard gate / warning gate。

## 2. 不要誤解它的定位

這是「戰略政策層 + 半戰術敘事」引擎，不是戰術火力解算器。

- 可以做：戰略路徑、對抗互動、政策代價、風險門檻。
- 不做：精準命中率、真實毀傷數、機密 ISR 管線。

`fidelity_guardrail=enabled` 時，模擬交火只會輸出損耗區間（低/中/高），不會輸出精確傷亡數字。

## 3. 架構與角色（你之前要求補清楚的部分）

核心 cells：

- `Supreme Orchestrator`：任務分解、回合節奏控制。
- `Control Cell`：seed、重現性、run 索引。
- `Blue Command`：藍隊（Blue）整合 PMESII 行動方案。
- `Red Command`：紅隊（Red）整合反制與欺敵方案。
- `White Cell`：白隊（White）裁決中樞，含：
  - `White-Legal/ROE`
  - `White-Probability`
  - `White-Counterdeception`
- `Intel Cell`：蒐集、來源檢核、融合。
- `Analysis Cell`：ACH、敏感度、關鍵假設斷點。
- `Report Cell`：輸出決策版與分析版報告。

顏色意義：

- `Blue`：我方/主防禦方（預設模板中的主體）。
- `Red`：對抗方/施壓方。
- `White`：裁判方（不是參戰方）。

## 4. 回合流程（實作版，不是概念圖）

每回合固定交握：

1. `Mission Context`
2. `Blue COA`
3. `Red COA`
4. `White Adjudication`
5. `PMESII State Update`
6. `Event Ledger`（半戰術事件）
7. `Indicators + Key Judgments`
8. `Next Turn Tasking`

你在輸出中會直接看到：

- 本回合做了哪些具體事件（軍事調動、制裁、外交斡旋、資訊戰、基礎設施擾動）。
- 為何白隊做出該裁決。
- 哪些證據支持、哪些證據反對。
- ACH 哪些 cell 被拉動。

## 5. 行為者基底資料庫（SQLite）到底裝什麼

每次 `run_campaign.py` 會在輸出目錄生成：

- `actor_baseline_db.sqlite`

資料表：

- `actors`：行為者主檔（id、角色、關聯）。
- `pmesii_baseline`：各維常態帶（normal_low/high + volatility）。
- `military_baseline`：兵力結構/部署區/裝備輪廓/動員指標。
- `economic_baseline`：制裁暴露、貿易依賴、能源脆弱度。
- `diplomatic_baseline`：盟友網絡、外交通道活躍度、斡旋開放度。
- `source_registry`：來源群組、更新頻率、可靠度先驗。

重點說清楚：

- V2.3 目前是「公開來源可稽核的結構化 baseline + 參數化區間」。
- 不是完整的國家級 ORBAT 真實數據庫。
- 它是可重用基底，不必每次重抓；但若你有更高品質基線，應該覆蓋更新。

## 6. 基底偏離（baseline deviation）是什麼

`baseline_deviation_report.json` 會記錄：

- 哪個事件在何維度偏離常態帶。
- 偏離方向（高於/低於/波動突增）。
- 偏離幅度與嚴重分數（`severity_score`）。
- 連到的 `event_id` 與 `evidence_ids`。

`average_score=0.283` 的意思是：

- 本次所有偏離紀錄的平均嚴重度是 0.283（0~1 區間）。
- 屬於「有偏離但未到失控高烈度」的中低段。

## 7. 事件引擎（V2.3）

固定事件型別：

- `military_movement`
- `simulated_engagement`
- `sanction_action`
- `diplomatic_mediation`
- `info_operation`
- `infrastructure_disruption`

每筆 `TurnEvent` 固定欄位：

- `event_id`, `turn_id`, `actor`, `target`, `location`, `time_window`
- `event_type`, `action_detail`, `estimated_outcome`
- `casualty_or_loss_band`
- `pmesii_delta`, `probability`, `confidence`
- `evidence_ids`, `assumption_links`

這讓報告不再只有「參數 + 分數」，而是可讀事件鏈。

## 8. 快速啟動

### 8.1 完整 campaign（建議）

```powershell
python scripts/run_campaign.py `
  --mission in/mission.json `
  --scenario in/scenario_pack.json `
  --actor-config in/actor_config.json `
  --collection-plan in/collection_plan.json `
  --out out/run_001 `
  --baseline-mode public_auto `
  --event-granularity semi_tactical `
  --fidelity-guardrail enabled `
  --report-profile dual_layer `
  --ach-profile full `
  --term-annotation inline_glossary `
  --narrative-mode event_cards `
  --length-policy warn `
  --min-chars-exec 2000 `
  --min-chars-analyst 5000 `
  --length-counting cjk_chars
```

### 8.2 驗證品質閘門

```powershell
python scripts/verify_trace.py `
  --mission in/mission.json `
  --evidence out/run_001/evidence.json `
  --event-ledger out/run_001/event_ledger.json `
  --baseline-deviation out/run_001/baseline_deviation_report.json `
  --key-judgments out/run_001/key_judgments.json `
  --ach out/run_001/ach_detailed.json `
  --report-exec out/run_001/report_exec.md `
  --report-analyst out/run_001/report_analyst.md `
  --length-policy warn
```

## 9. 核心輸出檔案

決策與閱讀：

- `report_exec.md`
- `report_analyst.md`
- `report.md`（相容別名）
- `turn_timeline.md`
- `event_timeline.md`
- `terms_and_parameters.md`

分析與稽核：

- `ach.json`, `ach_detailed.json`
- `key_judgments.json`
- `evidence.json`
- `event_ledger.json`
- `baseline_deviation_report.json`
- `run_log.jsonl`
- `report_metrics.json`
- `quality_gate_warnings.json`
- `run_artifact.json`

逐回合回放：

- `replay_bundle/turn_*_turn_packet.json`
- `replay_bundle/turn_*_result.json`
- `replay_bundle/turn_*_state.json`
- `replay_bundle/turn_*_agent_log.json`
- `replay_bundle/turn_*_event_ledger.json`
- `replay_bundle/turn_*_story_cards.json`

## 10. 測試與 CI

本機測試：

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

CI（GitHub Actions）會跑：

- Python 3.10 / 3.11
- 全部 `unittest` 測試

## 11. 已知限制與下一步建議

限制：

- 多行為者 coalition 原生引擎尚未上線（目前是 Blue/Red 主結構）。
- baseline 目前是可稽核參數化基線，非完整全球軍事資料庫。

優先下一步：

1. 把 `actor_baseline_db` 升級為可外部匯入（CSV/SQL）模式。  
2. 增加「多行為者互動矩陣」但維持 V2.3 報告品質。  
3. 對 `collection_plan` 做來源健康度監控與自動輪替。

## 12. 參考文件

- [SKILL.md](./SKILL.md)
- [references/methodology.md](./references/methodology.md)
- [references/adjudication-rules.md](./references/adjudication-rules.md)
- [references/source-policy.md](./references/source-policy.md)
- [references/pmesii-indicator-dictionary.md](./references/pmesii-indicator-dictionary.md)
- [references/red-team-playbook.md](./references/red-team-playbook.md)
- [references/agent-handoffs.md](./references/agent-handoffs.md)
