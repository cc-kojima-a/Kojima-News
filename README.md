# Kojima News

暗号資産デイリーニュースの自動生成システム。

毎朝 JST 9:00 に GitHub Actions で自動実行し、RSS フィードからニュースを収集、Claude API で要約・カテゴリ分けを行い、HTML ページとして蓄積します。

## ニュースソース

- CoinPost
- NADA NEWS
- COINTELEGRAPH Japan
- Bitcoin.com News

## セットアップ

1. リポジトリの Settings → Secrets and variables → Actions を開く
2. `ANTHROPIC_API_KEY` を登録する

## ローカル実行

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-api-key"
python scripts/generate.py
```

`docs/index.html` と `docs/archive/YYYY-MM-DD.html` が生成されます。
