# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块4：RAG知识库
================================
职责：把课标、教材、题目向量化存入Chroma，支持自然语言检索

安装依赖：
  pip install langchain langchain-community chromadb sentence-transformers

输入：cleaned_data.json（由模块1生成）
输出：
  - 向量知识库（Chroma本地数据库，存在./chroma_db目录）
  - knowledge_base.json（知识库内容索引，供前端展示）

运行方式：
  python 04_rag_knowledge.py
"""

import json
import os
import sys

# ============================================================
# 配置区
# ============================================================

OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
CHROMA_DIR = os.path.join(OUTPUT_DIR, "chroma_db")

# ============================================================
# 安装检查
# ============================================================

def check_dependencies():
    """检查依赖是否安装"""
    missing = []
    try:
        import langchain
    except ImportError:
        missing.append("langchain")
    try:
        import langchain_community
    except ImportError:
        missing.append("langchain-community")
    try:
        import chromadb
    except ImportError:
        missing.append("chromadb")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        missing.append("sentence-transformers")

    if missing:
        print("缺少以下依赖，请先安装：")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)


# ============================================================
# 知识库文档构建
# ============================================================

def build_documents(data_model):
    """
    把课程要求、题目、学习卡、教材切片转换为文档对象
    每个文档包含：内容文本 + 元数据（类型、编号、主题、指标）
    """
    documents = []

    # --- 1. 课程要求文档 ---
    for t_id, theme in data_model['knowledge_structure'].items():
        for ind_id, ind in theme['indicators'].items():
            content = (
                f"【课程要求】\n"
                f"主题：{theme['theme_name']}\n"
                f"主题目标：{theme['theme_goal']}\n"
                f"观察指标：{ind_id} - {ind['indicator_name']}\n"
                f"课标编号：{theme['course_standard']}\n"
                f"课标位置：{ind.get('course_standard_ref', '')}\n"
                f"教材页码：{theme.get('textbook_pages', '')}\n"
            )
            documents.append({
                'content': content,
                'metadata': {
                    'type': 'course_requirement',
                    'theme_id': t_id,
                    'indicator_id': ind_id,
                    'source': '课程要求'
                }
            })

    # --- 2. 题目文档 ---
    for q_id, q in data_model['question_indicator_map'].items():
        content_parts = [
            f"【题目】\n",
            f"编号：{q_id}\n",
            f"题型：{q['type']}\n",
            f"指标：{q['indicator']}\n",
            f"题干：{q['question_text']}\n",
        ]
        if q.get('options'):
            content_parts.append(f"选项：\n{q['options']}\n")
        if q.get('reference_answer'):
            content_parts.append(f"参考答案：{q['reference_answer']}\n")
        if q.get('reference_solution'):
            content_parts.append(f"参考解析：{q['reference_solution']}\n")
        if q.get('scoring_points'):
            content_parts.append(f"评分点：\n{q['scoring_points']}\n")
        content_parts.append(f"满分：{q['full_score']}\n")

        documents.append({
            'content': ''.join(content_parts),
            'metadata': {
                'type': 'question',
                'question_id': q_id,
                'theme_id': q['theme'],
                'indicator_id': q['indicator'],
                'source': '题目与材料'
            }
        })

    # --- 3. 学习卡文档（从原始CSV读取） ---
    # 学习卡信息在question_indicator_map里没有（非题目），从knowledge_structure补充
    # 这里直接从data_model的records中提取学习卡信息
    # 注意：学习卡在原始题目与材料表中，material_type='学习卡'
    # 我们需要额外读取原始CSV
    import csv
    csv_path = "/data_agent/users/sessions/36527195/upload/题目与材料.csv"
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('材料类型') == '学习卡':
                content = (
                    f"【学习卡】\n"
                    f"编号：{row.get('材料编号', '')}\n"
                    f"主题：{row.get('主题编号', '')}\n"
                    f"内容：{row.get('题干或内容', '')}\n"
                    f"对应指标：{row.get('指标编号', '')}\n"
                )
                documents.append({
                    'content': content,
                    'metadata': {
                        'type': 'learning_card',
                        'card_id': row.get('材料编号', ''),
                        'theme_id': row.get('主题编号', ''),
                        'indicator_id': row.get('指标编号', ''),
                        'source': '题目与材料'
                    }
                })
            elif row.get('材料类型') == '教材':
                content = (
                    f"【教材切片】\n"
                    f"编号：{row.get('材料编号', '')}\n"
                    f"内容：{row.get('题干或内容', '')}\n"
                    f"来源文件：{row.get('来源或资料文件', '')}\n"
                )
                documents.append({
                    'content': content,
                    'metadata': {
                        'type': 'textbook',
                        'textbook_id': row.get('材料编号', ''),
                        'source': '教材切片'
                    }
                })

    return documents


# ============================================================
# 向量化与存储
# ============================================================

def build_vectorstore(documents):
    """
    使用开源中文Embedding模型构建Chroma向量库
    模型：BAAI/bge-small-zh-v1.5（1.2亿参数，普通电脑可跑，免费）
    """
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Chroma
    from langchain_core.documents import Document

    print("  加载Embedding模型 BAAI/bge-small-zh-v1.5...")
    print("  （首次运行会自动下载模型，约500MB，请耐心等待）")

    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        model_kwargs={'device': 'cpu'}
    )

    # 转换为LangChain Document对象
    lc_docs = [
        Document(page_content=d['content'], metadata=d['metadata'])
        for d in documents
    ]

    print(f"  开始向量化 {len(lc_docs)} 个文档...")

    # 构建Chroma向量库
    vectorstore = Chroma.from_documents(
        documents=lc_docs,
        embedding=embeddings,
        persist_directory=CHROMA_DIR
    )

    return vectorstore


# ============================================================
# 检索测试
# ============================================================

def test_retrieval(vectorstore):
    """测试几个典型查询，验证检索效果"""
    test_queries = [
        "不等式与不等式组涉及哪些知识点？",
        "除以负数时不等号方向怎么变？",
        "二元一次方程组怎么解？",
        "代数式代入求值的题目有哪些？",
        "学习卡总结了什么内容？"
    ]

    print("\n  检索测试:")
    for query in test_queries:
        print(f"\n  问题: {query}")
        results = vectorstore.similarity_search(query, k=3)
        for i, doc in enumerate(results):
            # 只打印前100字
            preview = doc.page_content[:100].replace('\n', ' ')
            print(f"    [{i+1}] ({doc.metadata.get('type', '?')}) {preview}...")


# ============================================================
# 输出知识库索引
# ============================================================

def save_knowledge_index(documents):
    """输出知识库内容索引，供前端展示"""
    index = []
    for d in documents:
        index.append({
            'content_preview': d['content'][:200],
            'metadata': d['metadata']
        })

    index_path = os.path.join(OUTPUT_DIR, 'knowledge_base.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  -> {index_path}")


# ============================================================
# 主函数
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("  智慧学伴 - 模块4：RAG知识库构建")
    print("=" * 60)

    check_dependencies()

    # 加载数据
    cleaned_path = os.path.join(OUTPUT_DIR, 'cleaned_data.json')
    print(f"\n加载模块1的输出数据...")
    with open(cleaned_path, 'r', encoding='utf-8') as f:
        data_model = json.load(f)
    print(f"  加载完成")

    # 构建文档
    print(f"\n构建知识库文档...")
    documents = build_documents(data_model)
    print(f"  文档总数: {len(documents)}")
    type_count = {}
    for d in documents:
        t = d['metadata']['type']
        type_count[t] = type_count.get(t, 0) + 1
    for t, c in type_count.items():
        print(f"    {t}: {c} 个")

    # 构建向量库
    print(f"\n构建向量知识库...")
    vectorstore = build_vectorstore(documents)
    print(f"  向量库已保存到: {CHROMA_DIR}")

    # 检索测试
    test_retrieval(vectorstore)

    # 输出索引
    save_knowledge_index(documents)

    print("\n" + "=" * 60)
    print("  模块4 完成！")
    print("  后续使用：在对话Agent中导入Chroma向量库即可自然语言检索")
    print("=" * 60)


if __name__ == '__main__':
    main()
