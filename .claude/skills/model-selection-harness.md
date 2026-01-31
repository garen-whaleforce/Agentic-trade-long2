# Skill: model-selection-harness

## 目的
建立模型選擇的測試框架，評估品質、一致性、成本、時間。

## 何時使用
- 評估新模型
- 比較不同 prompt 版本
- 驗證一致性（K=5 測試）
- 選擇最佳模型組合

## 評估指標（按優先級）

### 第一優先：品質與一致性
1. **JSON Schema 合格率** >= 99%
2. **5-run flip rate** < 1%
3. **Score 標準差** < 0.03
4. **Evidence compliance** >= 95%

### 第二優先：成本
1. **batch_score** 平均 < $0.01/event
2. **full_audit** 可較高，但需控制觸發頻率

### 第三優先：時間
1. **batch_score** p95 < 3-5s
2. **full_audit** p95 < 10-15s

## Model Matrix

```yaml
# eval/model_matrix.yaml
models:
  batch_score:
    - id: gpt-4o-mini
      provider: openai
      cost_per_1k_input: 0.00015
      cost_per_1k_output: 0.0006

    - id: claude-3-haiku
      provider: anthropic
      cost_per_1k_input: 0.00025
      cost_per_1k_output: 0.00125

  full_audit:
    - id: gpt-5-mini
      provider: openai
      cost_per_1k_input: 0.0003
      cost_per_1k_output: 0.0012

    - id: claude-sonnet
      provider: anthropic
      cost_per_1k_input: 0.003
      cost_per_1k_output: 0.015

prompt_versions:
  batch_score:
    - v1.0.0
    - v1.1.0
    - v1.2.0

  full_audit:
    - v1.0.0
    - v1.1.0
```

## K=5 一致性測試

```python
async def run_consistency_test(
    event_ids: List[str],
    model: str,
    prompt_version: str,
    k: int = 5
) -> ConsistencyResult:
    """
    對每個 event 跑 K 次（不使用 cache），
    檢查 trade_candidate 是否翻盤。
    """
    results = []

    for event_id in event_ids:
        runs = []
        for i in range(k):
            # 關閉 cache，確保每次都是新呼叫
            result = await analyze_event(
                event_id=event_id,
                model=model,
                prompt_version=prompt_version,
                use_cache=False
            )
            runs.append(result)

        # 檢查一致性
        trade_decisions = [r.trade_candidate for r in runs]
        scores = [r.score for r in runs]

        is_consistent = len(set(trade_decisions)) == 1
        score_std = statistics.stdev(scores) if len(scores) > 1 else 0

        results.append({
            "event_id": event_id,
            "is_consistent": is_consistent,
            "trade_decisions": trade_decisions,
            "scores": scores,
            "score_mean": statistics.mean(scores),
            "score_std": score_std
        })

    # 計算總體 flip rate
    inconsistent_count = sum(1 for r in results if not r["is_consistent"])
    flip_rate = inconsistent_count / len(results)

    return ConsistencyResult(
        model=model,
        prompt_version=prompt_version,
        k=k,
        total_events=len(event_ids),
        inconsistent_events=inconsistent_count,
        flip_rate=flip_rate,
        avg_score_std=statistics.mean(r["score_std"] for r in results),
        details=results
    )
```

## Eval Harness

```python
# eval/eval_harness.py

async def run_model_evaluation(
    test_events: List[str],
    model_matrix: ModelMatrix,
    k_consistency: int = 5
) -> EvalResults:
    """
    對所有模型組合執行完整評估。
    """
    results = []

    for model_config in model_matrix.models:
        for prompt_version in model_matrix.prompt_versions:
            # 1. 基本測試（單次執行）
            basic_results = await run_basic_test(
                test_events, model_config, prompt_version
            )

            # 2. 一致性測試（K 次執行）
            consistency_results = await run_consistency_test(
                test_events[:50],  # 取子集做一致性測試
                model_config.id,
                prompt_version,
                k=k_consistency
            )

            # 3. 計算指標
            metrics = calculate_metrics(basic_results, consistency_results)

            results.append({
                "model": model_config.id,
                "prompt_version": prompt_version,
                "metrics": metrics
            })

    return EvalResults(results=results)
```

## Scoreboard 格式

```markdown
# Model Evaluation Scoreboard

## Test Info
- Date: 2026-01-31
- Test Events: 500
- K for consistency: 5

## Results

| Model | Prompt | JSON OK | Flip Rate | Score Std | Cost/Event | p95 Latency | Strategy Sharpe |
|-------|--------|---------|-----------|-----------|------------|-------------|-----------------|
| gpt-4o-mini | v1.2.0 | 99.8% | 0.4% | 0.018 | $0.0007 | 1.8s | 2.15 |
| gpt-4o-mini | v1.1.0 | 99.6% | 0.8% | 0.022 | $0.0007 | 1.7s | 2.08 |
| claude-3-haiku | v1.2.0 | 99.4% | 1.2% | 0.025 | $0.0009 | 2.1s | 2.02 |

## Recommendation
Based on **Quality = Consistency > Cost > Time**:
1. **Winner**: gpt-4o-mini + v1.2.0
   - Highest consistency (0.4% flip rate)
   - Lowest cost ($0.0007)
   - Best strategy performance (Sharpe 2.15)
```

## 產出 Artifacts

```
eval/
├── model_matrix.yaml           # 模型配置
├── eval_harness.py             # 評估腳本
├── results/
│   ├── eval_20260131.jsonl     # 詳細結果
│   └── scoreboard_20260131.md  # 摘要報告
```

## 驗收命令

```bash
# 執行模型評估
python -m backend.eval.eval_harness \
  --test-events data/test_events.json \
  --k-consistency 5 \
  --output eval/results/

# 產生 scoreboard
python -m backend.eval.generate_scoreboard \
  --input eval/results/eval_20260131.jsonl \
  --output eval/results/scoreboard_20260131.md
```

## 重要提醒

1. **不要用同一批資料調參和測試**
   - 調參：2017-2021
   - 驗證：2022-2023
   - 測試：2024-2025

2. **一致性測試必須關閉 cache**

3. **策略績效要用 Whaleforce API**（不可本地計算）

4. **K=5 是最低要求**，重要決策可用 K=10
