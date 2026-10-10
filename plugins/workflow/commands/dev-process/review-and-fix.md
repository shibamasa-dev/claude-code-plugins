---
description: AIレビュー実行→評価→修正計画→実装まで一貫して行うワークフロー
argument-hint: Optional review scope description
---

# Review and Fix Workflow

複数AgentによるAIレビューを実行し、結果を評価して適切な修正を行うワークフロー。

## Core Principles

- **コードベース確認必須**: レビューは局所観点の指摘や、アーキテクチャ戦略に沿わない指摘もあるため、必ず関連コードを確認してから判断する
- **CLAUDE.md遵守**: プロジェクトのアーキテクチャ方針・コーディング規約を最優先
- **適切な取捨選択**: 全ての指摘を鵜呑みにせず、プロジェクト文脈で妥当性を評価

---

## Phase 1: Execute Review

**Goal**: 複数Agentによる並列レビューを実行

**Actions**:
1. レビュースクリプトをバックグラウンドで実行:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/commands/dev-process/agent-review.sh [タイトル]
   ```
   - タイトルは任意（省略可）
   - 出力ファイル: `.context/review/{YYYYMMDDHHMMSS}_review[_{タイトル}_by_{agent}].md`
   - **重要**: Bashツールで以下のパラメータを指定すること
     - `run_in_background: true`
     - `dangerouslyDisableSandbox: true`
2. 非同期でレビュースクリプトからメッセージが通知されるので、スクリプトの完了を待たずに一旦終了する。

---

## Phase 2: Evaluate Review Results

**Goal**: レビュー結果を読み込み、各指摘の妥当性を評価

**Actions**:
1. Phase 1で取得したstdout出力のレビュー結果を分析
2. 各指摘について以下を確認:
   - **関連するソースコードを必ず読む**
   - CLAUDE.mdのアーキテクチャ方針との整合性
   - プロジェクト固有の事情（将来用残置コード、意図的な設計など）
   - 指摘の技術的妥当性
3. 指摘を以下に分類:
   - ✅ **採用**: プロジェクト方針に沿った有効な指摘
   - ⚠️ **要検討**: 一部妥当だが調整が必要
   - ❌ **不採用**: アーキテクチャ戦略に反する、または文脈を考慮していない

---

## Phase 3: Create Fix Plan

**Goal**: 採用する修正について計画を立案

**Actions**:
1. 採用・要検討の指摘をグルーピング（関連するファイル/機能ごと）
2. 修正の優先順位を決定:
   - 🔴 Critical: セキュリティ/データ整合性に関わる問題
   - 🟡 Important: 機能的な問題/パフォーマンス
   - 🟢 Nice-to-have: コード品質/可読性の改善
3. 修正計画ファイルを作成:
   - パス: `.context/plan/YYYYMMDDHHMMSS_fix_{概要タイトル}.md`
   - 内容:
     - 修正対象ファイル一覧
     - 各修正の詳細と理由
     - 不採用にした指摘とその理由
     - 実装順序

---

## Phase 4: Execute Fixes

**Goal**: 計画に基づき修正を実装

**Actions**:
1. 修正計画ファイルを読み込み
2. 優先順位順に修正を実施
3. プロジェクトの CLAUDE.md の規約に従う
4. 関連するテストがあれば実行確認

---

## Phase 5: Summary

**Goal**: 完了報告とドキュメント更新

**Actions**:
1. 実施した修正のサマリーを作成:
   - 修正したファイル一覧
   - 採用した指摘と対応内容
   - 不採用にした指摘とその理由
2. 修正計画ファイルに結果を追記
3. 必要に応じてCLAUDE.mdへのフィードバック提案

---

## Notes

- 修正計画は `.context/plan/` に保存される
- 迷った場合はユーザーに相談する
- アーキテクチャ方針に反する指摘は理由を明記して不採用とする
