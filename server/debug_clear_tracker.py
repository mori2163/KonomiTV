#!/usr/bin/env python3
"""
エンコードファイルトラッカーをクリアするデバッグスクリプト
"""

import asyncio
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))

async def main():
    try:
        from app.utils.EncodingFileTracker import EncodingFileTracker

        # エンコードファイルトラッカーのインスタンスを取得
        encoding_tracker = await EncodingFileTracker.getInstance()

        # 現在追跡中のファイル一覧を表示
        print("Current tracked files:")
        await encoding_tracker.debugPrintTrackedFiles()

        # 特定のファイルを削除（問題のファイル）
        problem_file = r"C:\Users\mori\dev\KonomiTV\TV-Record\202508041507010102-ニュース・気象情報（東北） - コピー (10)_h264.ts"
        print(f"\nRemoving problem file: {problem_file}")
        await encoding_tracker.forceRemoveEncodingFile(problem_file)

        # すべてのファイルをクリア
        print("\nClearing all tracked files...")
        await encoding_tracker.clearAll()

        # 結果を確認
        print("\nAfter cleanup:")
        await encoding_tracker.debugPrintTrackedFiles()

        print("\nCleanup completed successfully!")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
