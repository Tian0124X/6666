"""CLI 命令行工具 — 索引管理、缓存操作"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cmd_index(args: list[str]):
    """索引管理命令"""
    from app.rag.indexer import index_file, index_directory, reindex_all, get_index_status

    if not args or args[0] == "status":
        print("📊 索引进度")
        print("=" * 50)
        s = get_index_status()
        print(f"  Chunks 总数: {s['chunks_total']}")
        print(f"  物理文件:   {s['files_physical']}")
        print(f"  已索引:     {s['files_indexed']}")
        if s['files_unindexed']:
            print(f"  未索引 ({len(s['files_unindexed'])}):")
            for f in s['files_unindexed']:
                print(f"    - {f}")
        return

    elif args[0] == "rebuild":
        directory = args[1] if len(args) > 1 else "data/documents"
        print(f"🔄 全量重建索引: {directory}")
        result = reindex_all(directory)
        print(f"  完成: ✅{result.indexed} ⏭{result.skipped} ❌{result.failed}")
        print(f"  Chunks: {result.total_chunks} | 耗时: {result.elapsed_ms:.0f}ms")
        return

    elif args[0] == "file":
        if len(args) < 2:
            print("用法: python -m app.cli index file <文件路径> [--force]")
            return
        file_path = args[1]
        force = "--force" in args
        print(f"📄 索引文件: {file_path}" + (" (强制)" if force else ""))
        r = index_file(file_path, force=force)
        print(f"  状态: {r.status} | Chunks: {r.chunks} | 耗时: {r.elapsed_ms:.0f}ms")
        if r.error:
            print(f"  错误: {r.error}")
        return

    elif args[0] == "dir":
        directory = args[1] if len(args) > 1 else "data/documents"
        force = "--force" in args
        print(f"📁 批量索引目录: {directory}" + (" (强制)" if force else ""))

        def progress(i, total, name):
            pct = i * 100 // total if total else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct:3d}% ({i}/{total}) {name}", end="", flush=True)

        result = index_directory(directory, force=force, progress_callback=progress)
        print()  # 换行
        print(f"  完成: ✅{result.indexed} ⏭{result.skipped} ❌{result.failed}")
        print(f"  Chunks: {result.total_chunks} | 耗时: {result.elapsed_ms:.0f}ms")
        return

    else:
        print("用法:")
        print("  python -m app.cli index status            查看索引进度")
        print("  python -m app.cli index file <path>       索引单文件")
        print("  python -m app.cli index dir  [dir]         批量索引目录")
        print("  python -m app.cli index rebuild [dir]      全量重建")


def cmd_cache(args: list[str]):
    """缓存管理命令"""
    from app.rag.cache import query_cache

    if not args or args[0] == "stats":
        print("📊 缓存统计")
        print("=" * 30)
        s = query_cache.stats
        for k, v in s.items():
            print(f"  {k}: {v}")
        return

    elif args[0] == "clear":
        query_cache.clear()
        print("✅ 缓存已清空")
        return

    else:
        print("用法:")
        print("  python -m app.cli cache stats    查看缓存统计")
        print("  python -m app.cli cache clear    清空缓存")


def main():
    if len(sys.argv) < 2:
        print("企业智能办公助手 CLI")
        print()
        print("用法: python -m app.cli <command> [args]")
        print()
        print("命令:")
        print("  index    索引管理 (status/file/dir/rebuild)")
        print("  cache    缓存管理 (stats/clear)")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "index":
        cmd_index(args)
    elif cmd == "build-graph":
        from app.rag.build_graph import main as build_graph_main
        import sys
        sys.argv = [sys.argv[0]] + args
        build_graph_main()
    elif cmd == "cache":
        cmd_cache(args)
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: index, cache")


if __name__ == "__main__":
    main()
