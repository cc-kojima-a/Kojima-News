# Kojima News v2

デイリーマーケットニュースの自動生成システム。

毎朝 JST 9:00 に GitHub Actions で自動実行し、天気・株式市場・暗号資産の情報を収集、OpenAI API (GPT-5.2 Responses API) で要約・分析を行い、HTML ページとして蓄積します。

## 機能

### 天気情報
- 品川区大井町 / 渋谷区渋谷駅の2地点
- Open-Meteo API（無料、APIキー不要）

### 株式市場
- 主要指数: 日経平均、TOPIX、S&P 500、NASDAQ、ダウ平均
- 株式ニュース: Reuters Business、CNBC Top News
- yfinance（APIキー不要）

### 暗号資産
- 国内ニュース: CoinPost、NADA NEWS、COINTELEGRAPH Japan
- 海外ニュース: Bitcoin.com News、CoinDesk、Decrypt
- 主要通貨価格: BTC, ETH, XRP, SOL, BNB, ADA, DOGE
- CoinGecko API（無料、APIキー不要）

### AI 要約・分析
- GPT-5.2 Responses API（Reasoning モード）
- マーケット全体サマリー
- ニュースのカテゴリ分類（市場動向、規制・政策、プロジェクト・技術、取引所・サービス、その他）
- 価格影響分析（ニュースと価格変動の関連性）

## セットアップ

1. リポジトリの Settings → Secrets and variables → Actions を開く
2. `OPENAI_API_KEY` を登録する

## ローカル実行

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-api-key"
python scripts/generate.py
```

`docs/index.html` と `docs/archive/YYYY-MM-DD.html` が生成されます。

## 出力ページ構成

1. ヘッダー（タイトル + 日付）
2. 天気（大井町 / 渋谷 - 横並びカード）
3. マーケットサマリー（LLM による全体俯瞰）
4. 株式市場（主要指数テーブル + 株式ニュース）
5. 暗号資産価格（主要通貨の価格テーブル + 価格影響分析）
6. 国内暗号資産ニュース（カテゴリ別）
7. 海外暗号資産ニュース（カテゴリ別）
8. アーカイブリンク
9. フッター
