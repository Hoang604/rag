import asyncio

import asyncpg

from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import ASTNode
from tests.legal.fixtures.laws_data import ALL_STATUTORY_CHUNKS
from tests.legal.fixtures.signs_data import ALL_SIGN_CATALOG


async def main():
    pool = await asyncpg.create_pool("postgresql://postgres:postgres@localhost:54329/rag_legal")
    assert pool is not None
    loader = PostgresBulkLoader(pool, compute_embeddings=True, embedding_model="intfloat/multilingual-e5-small")

    docs_chunks: dict[str, list] = {}
    for chunk in ALL_STATUTORY_CHUNKS:
        docs_chunks.setdefault(chunk.document_code, []).append(chunk)

    for doc_code, chunks in docs_chunks.items():
        doc_type = (
            "NGHI_DINH"
            if "ND-CP" in doc_code
            else ("THONG_TU" if "TT" in doc_code else "QUY_CHUAN_KY_THUAT")
        )
        title = f"Văn bản {doc_code}"
        if doc_code == "100/2019/ND-CP":
            title = "Nghị định 100/2019/NĐ-CP xử phạt VPHC GTĐB & ĐS"
        elif doc_code == "31/2019/TT-BGTVT":
            title = "Thông tư 31/2019/TT-BGTVT quy định tốc độ xe cơ giới"

        doc_id = await loader.load_document(
            doc_code=doc_code,
            title=title,
            doc_type=doc_type,
            promulgation_date="2019-12-30" if "2019" in doc_code else "2020-01-01",
            effective_date="2020-01-15" if "100" in doc_code else "2019-10-15",
            status="EFFECTIVE",
        )

        ast_nodes = []
        node_paths_seen = set()
        for c in chunks:
            parts = c.hierarchy_path.split(".")
            running = ""
            for idx, p in enumerate(parts):
                running_parent = running
                running = f"{running}.{p}" if running else p
                if running not in node_paths_seen:
                    node_paths_seen.add(running)
                    if idx == 0:
                        lvl = "DOCUMENT"
                        label = p
                    elif p.startswith("p_"):
                        lvl = "POINT"
                        label = f"Điểm {p[2:]}"
                    elif p.startswith("c") and not p.startswith("c_"):
                        lvl = "CLAUSE"
                        label = f"Khoản {p[1:]}"
                    elif p.startswith("a"):
                        lvl = "ARTICLE"
                        label = f"Điều {p[1:]}"
                    else:
                        lvl = "CHAPTER"
                        label = p

                    node = ASTNode(
                        level=lvl,
                        index_label=label,
                        title=c.article_index if lvl == "ARTICLE" else label,
                        raw_text=c.verbatim_text if idx == len(parts) - 1 else "",
                        lead_sentence=c.lead_sentence if idx == len(parts) - 1 else None,
                        parent_path=running_parent,
                        depth=idx + 1,
                        display_order=idx + 1,
                    )
                    ast_nodes.append(node)
        node_map = await loader.load_hierarchy_nodes(ast_nodes, doc_id)
        await loader.load_chunks(chunks, doc_id, node_map)
        print(f"Loaded {len(chunks)} chunks for {doc_code}")

    async with pool.acquire() as conn:
        for s in ALL_SIGN_CATALOG:
            c_row = await conn.fetchrow("SELECT id FROM legal_chunks LIMIT 1;")
            chunk_uuid = c_row["id"] if c_row else None
            await conn.execute(
                """
                INSERT INTO sign_catalog (
                    sign_code, sign_name, sign_category, shape, primary_color, meaning, placement_rules, chunk_id
                ) VALUES ($1, $2, $3::sign_category_enum, $4, $5, $6, $7, $8)
                ON CONFLICT (sign_code) DO UPDATE SET
                    sign_name = EXCLUDED.sign_name,
                    sign_category = EXCLUDED.sign_category,
                    shape = EXCLUDED.shape,
                    primary_color = EXCLUDED.primary_color,
                    meaning = EXCLUDED.meaning,
                    placement_rules = EXCLUDED.placement_rules,
                    chunk_id = COALESCE(EXCLUDED.chunk_id, sign_catalog.chunk_id);
                """,
                s.sign_code,
                s.sign_name,
                s.category,
                s.shape,
                s.primary_color,
                s.meaning,
                s.placement_rules,
                chunk_uuid,
            )
        print(f"Loaded {len(ALL_SIGN_CATALOG)} signs into sign_catalog")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
